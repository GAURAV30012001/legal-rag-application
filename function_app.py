"""Azure Function App — Legal RAG HTTP endpoint."""
from __future__ import annotations

import json
import logging
import os
import sys

# Ensure src/ is on sys.path so legal_rag_app is importable
# whether or not 'pip install -e .' was run (required for Azure Functions)
_src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import azure.functions as func

from legal_rag_app.agents import run_agentic_chat_api
from legal_rag_app.config import build_model_client, load_config
from legal_rag_app.rag import create_azure_client, format_context, retrieve_context

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logger = logging.getLogger(__name__)


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
