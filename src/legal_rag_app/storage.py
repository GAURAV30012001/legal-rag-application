from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from azure.storage.blob import BlobServiceClient, ContentSettings


class StorageBackend:
    """Abstraction over local disk vs Azure Blob Storage for docs + index."""

    def __init__(self, *, connection_string: str | None, kb_dir: Path, index_path: Path,
                 docs_container: str = "legalrag-docs", index_container: str = "legalrag-index",
                 index_blob_name: str = "index.json", allowed_extensions: Iterable[str] = ()) -> None:
        self.allowed_ext = {ext.lower() for ext in allowed_extensions}
        self.use_blob = bool(connection_string)

        if self.use_blob:
            self.blob_service = BlobServiceClient.from_connection_string(connection_string)
            self.docs_container = docs_container
            self.index_container = index_container
            self.index_blob_name = index_blob_name
            self.docs_client = self.blob_service.get_container_client(self.docs_container)
            self.index_client = self.blob_service.get_container_client(self.index_container)
            # Ensure containers exist (idempotent)
            try:
                self.docs_client.create_container()
            except Exception:
                pass
            try:
                self.index_client.create_container()
            except Exception:
                pass
        else:
            self.docs_dir = kb_dir
            self.index_path = index_path
            self.docs_dir.mkdir(parents=True, exist_ok=True)
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Document helpers
    # ------------------------------------------------------------------
    def list_documents(self) -> List[Dict]:
        if self.use_blob:
            docs = []
            for blob in self.docs_client.list_blobs():
                ext = Path(blob.name).suffix.lower()
                if self.allowed_ext and ext not in self.allowed_ext:
                    continue
                docs.append({
                    "filename": Path(blob.name).name,
                    "size_bytes": blob.size or 0,
                    "last_modified": blob.last_modified.timestamp() if blob.last_modified else 0,
                })
            return docs

        docs = []
        for path in sorted(self.docs_dir.glob("**/*")):
            if self.allowed_ext and path.suffix.lower() not in self.allowed_ext:
                continue
            docs.append({
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "last_modified": path.stat().st_mtime,
            })
        return docs

    def download_document(self, filename: str) -> bytes:
        if self.use_blob:
            blob_client = self.docs_client.get_blob_client(filename)
            return blob_client.download_blob().readall()
        return (self.docs_dir / filename).read_bytes()

    def upload_document(self, filename: str, data: bytes, content_type: Optional[str] = None) -> int:
        if self.use_blob:
            ct = content_type or self._guess_content_type(filename)
            blob_client = self.docs_client.get_blob_client(filename)
            blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type=ct))
            props = blob_client.get_blob_properties()
            return props.size or len(data)
        dest = self.docs_dir / filename
        dest.write_bytes(data)
        return dest.stat().st_size

    def delete_document(self, filename: str) -> None:
        if self.use_blob:
            blob_client = self.docs_client.get_blob_client(filename)
            try:
                blob_client.delete_blob()
            except Exception:
                pass
            return
        target = self.docs_dir / filename
        if target.exists():
            target.unlink()

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------
    def load_index(self) -> Optional[Dict]:
        if self.use_blob:
            blob_client = self.index_client.get_blob_client(self.index_blob_name)
            if not blob_client.exists():
                return None
            data = blob_client.download_blob().readall()
            return json.loads(data.decode("utf-8"))
        if not self.index_path.exists():
            return None
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def save_index(self, payload: Dict) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if self.use_blob:
            blob_client = self.index_client.get_blob_client(self.index_blob_name)
            blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type="application/json"))
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_bytes(data)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _guess_content_type(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return "application/pdf"
        if ext == ".docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if ext == ".md":
            return "text/markdown"
        if ext == ".txt":
            return "text/plain"
        return "application/octet-stream"
