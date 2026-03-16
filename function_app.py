"""Azure Function App — Legal RAG HTTP endpoint."""
from __future__ import annotations

import json
import logging
import os
import re
import sys

# Ensure the src/ package is importable without `pip install -e .`
_src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import azure.functions as func

from legal_rag_app.agents import run_agentic_chat_api
from legal_rag_app.config import build_model_client, load_config
from legal_rag_app.rag import create_azure_client, format_context, retrieve_context

# ---------------------------------------------------------------------------
# Small-talk / greeting detection
# ---------------------------------------------------------------------------
_SMALLTALK_PATTERNS = re.compile(
    r"^\s*("
    r"hi+|hello+|hey+|howdy|greetings|good\s*(morning|afternoon|evening|day)|"
    r"what'?s?\s*up|sup|yo|hiya|"
    r"thanks?(\s+you)?|thank\s*you|cheers|ty|"
    r"ok(ay)?|sure|got\s*it|sounds?\s*good|great|cool|nice|awesome|"
    r"bye|goodbye|see\s*you|cya|"
    r"who\s*are\s*you|what\s*(are|can)\s*you\s*do|help|what\s*is\s*this"
    r")\s*[!?.]*\s*$",
    re.IGNORECASE,
)

_SMALLTALK_REPLY = (
    "Hello! I'm the **Legal RAG Assistant**. I can help you query and analyse your "
    "uploaded legal documents — contracts, NDAs, compliance policies, SLAs, and more.\n\n"
    "Try asking something like:\n"
    "- *\"What are the confidentiality obligations in the NDA?\"*\n"
    "- *\"What is the notice period in the employment contract?\"*\n"
    "- *\"What GDPR rights does a data subject have?\"*\n\n"
    "Upload your documents via **📄 Manage Docs** and then ask away!"
)


def _is_smalltalk(text: str) -> bool:
    return bool(_SMALLTALK_PATTERNS.match(text))

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logger = logging.getLogger(__name__)

# Only these extensions are accepted for document uploads (prevents arbitrary file writes)
_ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


def _safe_filename(name: str) -> str | None:
    """Return a sanitised filename, or None if the name is unsafe/disallowed.

    Guards against path-traversal attacks (e.g. '../../etc/passwd').
    """
    name = os.path.basename(name).strip()
    if not name:
        return None
    # Allow alphanumeric, spaces, hyphens, underscores and a single dot for the extension
    if not re.match(r'^[\w\- .]+$', name):
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return None
    return name


# ---------------------------------------------------------------------------
# Document management endpoints
# ---------------------------------------------------------------------------

@app.route(route="documents", methods=["GET"])
def list_documents(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/documents
    Returns a list of all documents currently in the knowledge base.
    """
    try:
        cfg = load_config()
        kb_dir = cfg.knowledge_base_dir
        files = []
        for path in sorted(kb_dir.glob("**/*")):
            if path.suffix.lower() in _ALLOWED_EXTENSIONS:
                files.append({
                    "filename": path.name,
                    "size_bytes": path.stat().st_size,
                    "last_modified": path.stat().st_mtime,
                })
        return func.HttpResponse(
            json.dumps({"documents": files, "count": len(files)}, indent=2),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as exc:
        logger.exception("Error listing documents")
        return func.HttpResponse(
            json.dumps({"error": "Could not list documents.", "detail": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )


@app.route(route="upload", methods=["POST"])
def upload_document(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/upload
    Upload a new document to the knowledge base.

    JSON body:
      {
        "filename": "my_contract.md",   // must end in .md or .txt
        "content":  "Full text of the document..."
      }

    The vector index is automatically rebuilt on the next /api/query call
    because the index cache checks file modification timestamps.
    """
    content_type = req.headers.get("Content-Type", "")

    # ── Binary upload (PDF / DOCX) via multipart/form-data ──────────────────
    if "multipart/form-data" in content_type:
        file_bytes = req.files.get("file") if req.files else None
        if file_bytes is None:
            return func.HttpResponse(
                json.dumps({"error": "Missing 'file' field in form data."}),
                status_code=400, mimetype="application/json",
            )
        raw_filename = file_bytes.filename or ""
        safe_name = _safe_filename(raw_filename)
        if safe_name is None:
            return func.HttpResponse(
                json.dumps({"error": f"Invalid or disallowed filename '{raw_filename}'. Allowed: .md .txt .pdf .docx"}),
                status_code=400, mimetype="application/json",
            )
        try:
            cfg = load_config()
            dest = cfg.knowledge_base_dir / safe_name
            dest.write_bytes(file_bytes.read())
            size = dest.stat().st_size
            logger.info("Uploaded binary document: %s (%d bytes)", safe_name, size)
        except Exception as exc:
            logger.exception("Error saving binary document %s", safe_name)
            return func.HttpResponse(
                json.dumps({"error": "Could not save document.", "detail": str(exc)}),
                status_code=500, mimetype="application/json",
            )
        return func.HttpResponse(
            json.dumps({"message": f"Document '{safe_name}' uploaded successfully. Index rebuilds on next query.",
                        "filename": safe_name, "size_bytes": size}, indent=2),
            status_code=201, mimetype="application/json",
        )

    # ── JSON upload (.md / .txt text content) ───────────────────────────────
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON."}),
            status_code=400,
            mimetype="application/json",
        )

    raw_filename = body.get("filename", "").strip()
    content: str = body.get("content", "").strip()

    if not raw_filename:
        return func.HttpResponse(
            json.dumps({"error": "Missing 'filename' field."}),
            status_code=400,
            mimetype="application/json",
        )
    if not content:
        return func.HttpResponse(
            json.dumps({"error": "Missing 'content' field."}),
            status_code=400,
            mimetype="application/json",
        )

    safe_name = _safe_filename(raw_filename)
    if safe_name is None:
        return func.HttpResponse(
            json.dumps({
                "error": f"Invalid filename '{raw_filename}'. "
                         "Allowed extensions: .md .txt .pdf .docx. "
                         "Filename must contain only letters, numbers, spaces, hyphens, and underscores."
            }),
            status_code=400,
            mimetype="application/json",
        )

    try:
        cfg = load_config()
        dest = cfg.knowledge_base_dir / safe_name
        dest.write_text(content, encoding="utf-8")
        logger.info("Uploaded document: %s (%d bytes)", safe_name, len(content.encode("utf-8")))
    except Exception as exc:
        logger.exception("Error saving document %s", safe_name)
        return func.HttpResponse(
            json.dumps({"error": "Could not save document.", "detail": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({
            "message": f"Document '{safe_name}' uploaded successfully. "
                       "The index will be rebuilt automatically on the next query.",
            "filename": safe_name,
            "size_bytes": len(content.encode("utf-8")),
        }, indent=2),
        status_code=201,
        mimetype="application/json",
    )


@app.route(route="documents/delete", methods=["POST"])
def delete_document(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/documents/delete
    Delete a document from the knowledge base.

    JSON body:
      { "filename": "my_contract.md" }

    The vector index is automatically rebuilt on the next /api/query call.
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON."}),
            status_code=400,
            mimetype="application/json",
        )

    raw_filename = body.get("filename", "").strip()
    if not raw_filename:
        return func.HttpResponse(
            json.dumps({"error": "Missing 'filename' field."}),
            status_code=400,
            mimetype="application/json",
        )

    safe_name = _safe_filename(raw_filename)
    if safe_name is None:
        return func.HttpResponse(
            json.dumps({"error": f"Invalid or disallowed filename '{raw_filename}'."}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        cfg = load_config()
        target = cfg.knowledge_base_dir / safe_name
        if not target.exists():
            return func.HttpResponse(
                json.dumps({"error": f"Document '{safe_name}' not found."}),
                status_code=404,
                mimetype="application/json",
            )
        target.unlink()
        logger.info("Deleted document: %s", safe_name)
    except Exception as exc:
        logger.exception("Error deleting document %s", safe_name)
        return func.HttpResponse(
            json.dumps({"error": "Could not delete document.", "detail": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({
            "message": f"Document '{safe_name}' deleted successfully. "
                       "The index will be rebuilt automatically on the next query.",
            "filename": safe_name,
        }, indent=2),
        status_code=200,
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------

@app.route(route="query", methods=["GET", "POST"])
async def legal_query(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger — accepts a legal question and returns multi-agent analysis.

    GET  /api/query?question=What+are+the+NDA+obligations
    POST /api/query  body: {"question": "...", "top_k": 3}
    """
    # --- Parse input ---
    question: str = req.params.get("question", "").strip()
    top_k: int = int(req.params.get("top_k", 3))

    if req.method == "POST":
        try:
            body = req.get_json()
            question = body.get("question", question).strip()
            top_k = int(body.get("top_k", top_k))
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON body."}),
                status_code=400,
                mimetype="application/json",
            )

    if not question:
        return func.HttpResponse(
            json.dumps({"error": "Missing 'question' parameter."}),
            status_code=400,
            mimetype="application/json",
        )

    # --- Short-circuit: return a friendly reply for greetings / small talk ---
    if _is_smalltalk(question):
        return func.HttpResponse(
            json.dumps({
                "question": question,
                "context_chunks": [],
                "agent_responses": [],
                "final_answer": _SMALLTALK_REPLY,
            }, ensure_ascii=False, indent=2),
            status_code=200,
            mimetype="application/json",
        )

    # --- Load config & run pipeline ---
    try:
        cfg = load_config()
        openai_client = create_azure_client(cfg)
        chunks = retrieve_context(cfg, openai_client, question, top_k=top_k)
        context = format_context(chunks)
        model_client = build_model_client(cfg)
        result = await run_agentic_chat_api(model_client, question, context)
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return func.HttpResponse(
            json.dumps({"error": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error processing question: %s", question)
        return func.HttpResponse(
            json.dumps({"error": "Internal server error.", "detail": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )

    # --- Return response ---
    context_sources = [{"chunk_id": c.chunk_id, "source": c.source, "text": c.text} for c in chunks]
    response_body = {
        "question": question,
        "context_chunks": context_sources,
        **result,
    }
    return func.HttpResponse(
        json.dumps(response_body, ensure_ascii=False, indent=2),
        status_code=200,
        mimetype="application/json",
    )
