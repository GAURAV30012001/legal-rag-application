"""Azure Function App — Legal RAG HTTP endpoint."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import uuid

# Ensure the src/ package is importable without `pip install -e .`
_src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import azure.functions as func

from legal_rag_app.agents import run_agentic_chat_api
from legal_rag_app.config import build_model_client, load_config
from legal_rag_app.rag import create_azure_client, format_context, retrieve_context
from legal_rag_app.storage import StorageBackend

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
    "Hello! I'm the **RAG Document Assistant**. I can help you query and analyse any "
    "documents you upload — legal contracts, technical specs, HR policies, compliance documents, and more.\n\n"
    "Try asking something like:\n"
    "- *\"What are the key obligations in this contract?\"*\n"
    "- *\"Summarise the main points of this policy.\"*\n"
    "- *\"What are the technical requirements mentioned?\"*\n\n"
    "Upload your documents via **📄 Manage Docs** and then ask away!"
)


def _is_smalltalk(text: str) -> bool:
    return bool(_SMALLTALK_PATTERNS.match(text))

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logger = logging.getLogger(__name__)

# Only these extensions are accepted for document uploads (prevents arbitrary file writes)
_ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


def _get_storage(cfg, user_prefix: str = ""):
    return StorageBackend(
        connection_string=cfg.storage_connection_string,
        kb_dir=cfg.knowledge_base_dir,
        index_path=cfg.index_path,
        docs_container=cfg.storage_container_docs,
        index_container=cfg.storage_container_index,
        index_blob_name=cfg.index_blob_name,
        allowed_extensions=_ALLOWED_EXTENSIONS,
        user_prefix=user_prefix,
    )


def _extract_user_id(req: func.HttpRequest) -> str:
    """Extract the caller's user ID from X-User-Id header.

    Validates it is a proper UUID to prevent path-traversal attacks.
    Falls back to 'shared' when the header is absent or invalid.
    """
    raw = req.headers.get("X-User-Id", "").strip()
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError):
        return "shared"


# ---------------------------------------------------------------------------
# CORS helpers — required for cross-origin calls from the deployed Web App
# ---------------------------------------------------------------------------
def _cors_headers() -> dict:
    origin = os.getenv("CORS_ALLOWED_ORIGIN", "*")
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, x-functions-key, X-User-Id",
        "Access-Control-Max-Age": "86400",
    }


def _preflight() -> func.HttpResponse:
    return func.HttpResponse("", status_code=200, headers=_cors_headers())


def _json_resp(body: str, status_code: int = 200) -> func.HttpResponse:
    """Return a JSON HttpResponse with CORS headers pre-attached."""
    return func.HttpResponse(
        body, status_code=status_code, mimetype="application/json", headers=_cors_headers()
    )


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

@app.route(route="documents", methods=["GET", "OPTIONS"])
def list_documents(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/documents
    Returns a list of all documents currently in the knowledge base.
    """
    if req.method == "OPTIONS":
        return _preflight()
    try:
        user_id = _extract_user_id(req)
        cfg = load_config()
        storage = _get_storage(cfg, user_id)
        files = storage.list_documents()
        return _json_resp(json.dumps({"documents": files, "count": len(files)}, indent=2))
    except Exception as exc:
        logger.exception("Error listing documents")
        return _json_resp(
            json.dumps({"error": "Could not list documents.", "detail": str(exc)}),
            status_code=500,
        )


@app.route(route="upload", methods=["POST", "OPTIONS"])
def upload_document(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/upload
    Upload a new document to the knowledge base.
    """
    if req.method == "OPTIONS":
        return _preflight()

    content_type = req.headers.get("Content-Type", "")

    # ── Binary upload (PDF / DOCX) via multipart/form-data ──────────────────
    if "multipart/form-data" in content_type:
        file_bytes = req.files.get("file") if req.files else None
        if file_bytes is None:
            return _json_resp(json.dumps({"error": "Missing 'file' field in form data."}), status_code=400)
        raw_filename = file_bytes.filename or ""
        safe_name = _safe_filename(raw_filename)
        if safe_name is None:
            return _json_resp(
                json.dumps({"error": f"Invalid or disallowed filename '{raw_filename}'. Allowed: .md .txt .pdf .docx"}),
                status_code=400,
            )
        try:
            user_id = _extract_user_id(req)
            cfg = load_config()
            storage = _get_storage(cfg, user_id)
            size = storage.upload_document(safe_name, file_bytes.read())
            logger.info("Uploaded binary document: %s (%d bytes)", safe_name, size)
        except Exception as exc:
            logger.exception("Error saving binary document %s", safe_name)
            return _json_resp(json.dumps({"error": "Could not save document.", "detail": str(exc)}), status_code=500)
        return _json_resp(
            json.dumps({"message": f"Document '{safe_name}' uploaded successfully. Index rebuilds on next query.",
                        "filename": safe_name, "size_bytes": size}, indent=2),
            status_code=201,
        )

    # ── JSON upload (.md / .txt text content) ───────────────────────────────
    try:
        body = req.get_json()
    except ValueError:
        return _json_resp(json.dumps({"error": "Request body must be valid JSON."}), status_code=400)

    raw_filename = body.get("filename", "").strip()
    content: str = body.get("content", "").strip()

    if not raw_filename:
        return _json_resp(json.dumps({"error": "Missing 'filename' field."}), status_code=400)
    if not content:
        return _json_resp(json.dumps({"error": "Missing 'content' field."}), status_code=400)

    safe_name = _safe_filename(raw_filename)
    if safe_name is None:
        return _json_resp(
            json.dumps({
                "error": f"Invalid filename '{raw_filename}'. "
                         "Allowed extensions: .md .txt .pdf .docx. "
                         "Filename must contain only letters, numbers, spaces, hyphens, and underscores."
            }),
            status_code=400,
        )

    try:
        user_id = _extract_user_id(req)
        cfg = load_config()
        storage = _get_storage(cfg, user_id)
        size_bytes = storage.upload_document(safe_name, content.encode("utf-8"), content_type="text/plain")
        logger.info("Uploaded document: %s (%d bytes)", safe_name, size_bytes)
    except Exception as exc:
        logger.exception("Error saving document %s", safe_name)
        return _json_resp(json.dumps({"error": "Could not save document.", "detail": str(exc)}), status_code=500)

    return _json_resp(
        json.dumps({
            "message": f"Document '{safe_name}' uploaded successfully. "
                       "The index will be rebuilt automatically on the next query.",
            "filename": safe_name,
            "size_bytes": size_bytes,
        }, indent=2),
        status_code=201,
    )


@app.route(route="documents/delete", methods=["POST", "OPTIONS"])
def delete_document(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/documents/delete
    Delete a document from the knowledge base.

    JSON body:
      { "filename": "my_contract.md" }

    The vector index is automatically rebuilt on the next /api/query call.
    """
    if req.method == "OPTIONS":
        return _preflight()

    try:
        body = req.get_json()
    except ValueError:
        return _json_resp(json.dumps({"error": "Request body must be valid JSON."}), status_code=400)

    raw_filename = body.get("filename", "").strip()
    if not raw_filename:
        return _json_resp(json.dumps({"error": "Missing 'filename' field."}), status_code=400)

    safe_name = _safe_filename(raw_filename)
    if safe_name is None:
        return _json_resp(
            json.dumps({"error": f"Invalid or disallowed filename '{raw_filename}'."}), status_code=400
        )

    try:
        user_id = _extract_user_id(req)
        cfg = load_config()
        storage = _get_storage(cfg, user_id)
        storage.delete_document(safe_name)
        storage.delete_index()  # immediately invalidate cached embeddings for this user
        logger.info("Deleted document: %s", safe_name)
    except Exception as exc:
        logger.exception("Error deleting document %s", safe_name)
        return _json_resp(
            json.dumps({"error": "Could not delete document.", "detail": str(exc)}), status_code=500
        )

    return _json_resp(
        json.dumps({
            "message": f"Document '{safe_name}' deleted successfully. "
                       "The index will be rebuilt automatically on the next query.",
            "filename": safe_name,
        }, indent=2)
    )


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------

@app.route(route="query", methods=["GET", "POST", "OPTIONS"])
async def legal_query(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger — accepts a legal question and returns multi-agent analysis.

    GET  /api/query?question=What+are+the+NDA+obligations
    POST /api/query  body: {"question": "...", "top_k": 3}
    """
    if req.method == "OPTIONS":
        return _preflight()

    # --- Parse input ---
    question: str = req.params.get("question", "").strip()
    top_k: int = int(req.params.get("top_k", 3))

    if req.method == "POST":
        try:
            body = req.get_json()
            question = body.get("question", question).strip()
            top_k = int(body.get("top_k", top_k))
        except ValueError:
            return _json_resp(json.dumps({"error": "Invalid JSON body."}), status_code=400)

    if not question:
        return _json_resp(json.dumps({"error": "Missing 'question' parameter."}), status_code=400)

    # --- Short-circuit: return a friendly reply for greetings / small talk ---
    if _is_smalltalk(question):
        return _json_resp(
            json.dumps({
                "question": question,
                "context_chunks": [],
                "agent_responses": [],
                "final_answer": _SMALLTALK_REPLY,
            }, ensure_ascii=False, indent=2)
        )

    # --- Load config & run pipeline ---
    try:
        user_id = _extract_user_id(req)
        cfg = load_config()
        openai_client = create_azure_client(cfg)
        chunks = retrieve_context(cfg, openai_client, question, top_k=top_k, user_prefix=user_id)
        context = format_context(chunks)
        model_client = build_model_client(cfg)
        result = await run_agentic_chat_api(model_client, question, context)
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return _json_resp(json.dumps({"error": str(exc)}), status_code=500)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error processing question: %s", question)
        return _json_resp(
            json.dumps({"error": "Internal server error.", "detail": str(exc)}), status_code=500
        )

    # --- Return response ---
    context_sources = [{"chunk_id": c.chunk_id, "source": c.source, "text": c.text} for c in chunks]
    response_body = {
        "question": question,
        "context_chunks": context_sources,
        **result,
    }
    return _json_resp(json.dumps(response_body, ensure_ascii=False, indent=2))
