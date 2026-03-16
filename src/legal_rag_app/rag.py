from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import numpy as np
from openai import AzureOpenAI

from .config import AppConfig


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


def _extract_text(path: Path) -> str:
    """Return plain text from .md/.txt/.pdf/.docx files."""
    ext = path.suffix.lower()
    if ext in (".md", ".txt"):
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        import pypdf  # lazy import — only needed when a PDF is present
        reader = pypdf.PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == ".docx":
        import docx  # lazy import — python-docx
        doc = docx.Document(str(path))
        return "\n".join(para.text for para in doc.paragraphs)
    return ""


def load_documents(doc_dir: Path) -> List[tuple[str, str]]:
    documents: List[tuple[str, str]] = []
    for path in sorted(doc_dir.glob("**/*")):
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            continue
        content = _extract_text(path)
        documents.append((path.name, content))
    return documents


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


def _file_mtimes(files: Iterable[Path]) -> dict:
    return {str(path): path.stat().st_mtime for path in files}


def _index_needs_rebuild(index_path: Path, files: List[Path]) -> bool:
    if not index_path.exists():
        return True
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    meta = payload.get("meta", {}).get("files", {})
    current = _file_mtimes(files)
    return meta != current


def build_or_load_index(cfg: AppConfig, client: AzureOpenAI) -> List[Chunk]:
    doc_paths = [p for p in cfg.knowledge_base_dir.glob("**/*") if p.suffix.lower() in _SUPPORTED_EXTENSIONS]
    if not doc_paths:
        raise ValueError("No documents found in data/knowledge_base")

    if _index_needs_rebuild(cfg.index_path, doc_paths):
        documents = load_documents(cfg.knowledge_base_dir)
        chunks: List[Chunk] = []
        for name, content in documents:
            for idx, chunk in enumerate(chunk_text(content)):
                embedding = get_embedding(client, cfg.azure_openai_embeddings_deployment, chunk)
                chunks.append(Chunk(chunk_id=f"{name}-{idx}", source=name, text=chunk, embedding=embedding))

        payload = {
            "meta": {"files": _file_mtimes(doc_paths)},
            "chunks": [chunk.__dict__ for chunk in chunks],
        }
        cfg.index_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return chunks

    payload = json.loads(cfg.index_path.read_text(encoding="utf-8"))
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
