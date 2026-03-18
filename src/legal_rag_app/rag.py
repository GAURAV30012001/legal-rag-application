from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Dict

import numpy as np
from openai import AzureOpenAI

from .config import AppConfig
from .storage import StorageBackend


@dataclass
class Chunk:
    chunk_id: str
    source: str
    text: str
    embedding: List[float]


def create_azure_client(cfg: AppConfig) -> AzureOpenAI:
    return AzureOpenAI(
        api_key=cfg.azure_openai_api_key,
        azure_endpoint=cfg.azure_openai_endpoint,
        api_version=cfg.azure_openai_api_version,
    )


_SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


def _extract_text_from_bytes(filename: str, data: bytes) -> str:
    """Return plain text from .md/.txt/.pdf/.docx bytes."""
    ext = Path(filename).suffix.lower()
    if ext in (".md", ".txt"):
        return data.decode("utf-8", errors="ignore")
    if ext == ".pdf":
        import pypdf  # lazy import — only needed when a PDF is present
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == ".docx":
        import docx  # lazy import — python-docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(para.text for para in doc.paragraphs)
    return ""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    text = " ".join(text.split())
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def get_embedding(client: AzureOpenAI, model: str, text: str) -> List[float]:
    response = client.embeddings.create(model=model, input=text)
    return response.data[0].embedding


def _index_needs_rebuild(saved_meta: Dict, current_meta: Dict) -> bool:
    return saved_meta != current_meta


def build_or_load_index(cfg: AppConfig, client: AzureOpenAI) -> List[Chunk]:
    storage = StorageBackend(
        connection_string=cfg.storage_connection_string,
        kb_dir=cfg.knowledge_base_dir,
        index_path=cfg.index_path,
        docs_container=cfg.storage_container_docs,
        index_container=cfg.storage_container_index,
        index_blob_name=cfg.index_blob_name,
        allowed_extensions=_SUPPORTED_EXTENSIONS,
    )

    docs_meta = storage.list_documents()
    if not docs_meta:
        raise ValueError("No documents found in knowledge base")

    current_meta = {item["filename"]: item.get("last_modified", 0) for item in docs_meta}
    payload = storage.load_index()
    saved_meta = payload.get("meta", {}).get("files", {}) if payload else {}

    if payload is None or _index_needs_rebuild(saved_meta, current_meta):
        chunks: List[Chunk] = []
        for doc in docs_meta:
            name = doc["filename"]
            data = storage.download_document(name)
            content = _extract_text_from_bytes(name, data)
            for idx, chunk in enumerate(chunk_text(content)):
                embedding = get_embedding(client, cfg.azure_openai_embeddings_deployment, chunk)
                chunks.append(Chunk(chunk_id=f"{name}-{idx}", source=name, text=chunk, embedding=embedding))

        payload = {
            "meta": {"files": current_meta},
            "chunks": [chunk.__dict__ for chunk in chunks],
        }
        storage.save_index(payload)
        return chunks

    return [Chunk(**item) for item in payload.get("chunks", [])]


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    denominator = (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    if denominator == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denominator)


def retrieve_top_k(chunks: List[Chunk], query_embedding: List[float], top_k: int = 3) -> List[Chunk]:
    query_vec = np.array(query_embedding, dtype=float)
    scored = []
    for chunk in chunks:
        score = cosine_similarity(query_vec, np.array(chunk.embedding, dtype=float))
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def retrieve_context(cfg: AppConfig, client: AzureOpenAI, question: str, top_k: int = 3) -> List[Chunk]:
    chunks = build_or_load_index(cfg, client)
    query_embedding = get_embedding(client, cfg.azure_openai_embeddings_deployment, question)
    return retrieve_top_k(chunks, query_embedding, top_k=top_k)


def format_context(chunks: List[Chunk]) -> str:
    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        lines.append(f"[{idx}] Source: {chunk.source}\n{chunk.text}")
    return "\n\n".join(lines)
