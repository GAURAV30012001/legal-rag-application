from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from azure.storage.blob import BlobServiceClient, ContentSettings


class StorageBackend:
    """Abstraction over local disk vs Azure Blob Storage for docs + index.

    When ``user_prefix`` is supplied (e.g. a UUID), every blob is stored under
    ``{user_prefix}/{filename}`` so different users have fully isolated namespaces.
    """

    def __init__(self, *, connection_string: str | None, kb_dir: Path, index_path: Path,
                 docs_container: str = "legalrag-docs", index_container: str = "legalrag-index",
                 index_blob_name: str = "index.json", allowed_extensions: Iterable[str] = (),
                 user_prefix: str = "") -> None:
        self.allowed_ext = {ext.lower() for ext in allowed_extensions}
        self.use_blob = bool(connection_string)
        self._user_prefix = user_prefix.strip("/") if user_prefix else ""
        self.index_blob_name = index_blob_name

        if self.use_blob:
            self.blob_service = BlobServiceClient.from_connection_string(connection_string)
            self.docs_container = docs_container
            self.index_container = index_container
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
    # Internal path helpers
    # ------------------------------------------------------------------
    def _doc_blob_path(self, filename: str) -> str:
        """Full blob name for a document (includes user prefix when set)."""
        return f"{self._user_prefix}/{filename}" if self._user_prefix else filename

    def _index_blob_path(self) -> str:
        """Full blob name for the index file (includes user prefix when set)."""
        return f"{self._user_prefix}/{self.index_blob_name}" if self._user_prefix else self.index_blob_name

    # ------------------------------------------------------------------
    # Document helpers
    # ------------------------------------------------------------------
    def list_documents(self) -> List[Dict]:
        if self.use_blob:
            prefix = f"{self._user_prefix}/" if self._user_prefix else ""
            docs = []
            for blob in self.docs_client.list_blobs(name_starts_with=prefix):
                # Strip the user prefix so callers only see the bare filename
                name = blob.name[len(prefix):] if prefix else blob.name
                ext = Path(name).suffix.lower()
                if self.allowed_ext and ext not in self.allowed_ext:
                    continue
                docs.append({
                    "filename": name,
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
            blob_client = self.docs_client.get_blob_client(self._doc_blob_path(filename))
            return blob_client.download_blob().readall()
        return (self.docs_dir / filename).read_bytes()

    def upload_document(self, filename: str, data: bytes, content_type: Optional[str] = None) -> int:
        if self.use_blob:
            ct = content_type or self._guess_content_type(filename)
            blob_client = self.docs_client.get_blob_client(self._doc_blob_path(filename))
            blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type=ct))
            props = blob_client.get_blob_properties()
            return props.size or len(data)
        dest = self.docs_dir / filename
        dest.write_bytes(data)
        return dest.stat().st_size

    def delete_document(self, filename: str) -> None:
        if self.use_blob:
            blob_client = self.docs_client.get_blob_client(self._doc_blob_path(filename))
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
            blob_client = self.index_client.get_blob_client(self._index_blob_path())
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
            blob_client = self.index_client.get_blob_client(self._index_blob_path())
            blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type="application/json"))
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_bytes(data)

    def delete_index(self) -> None:
        """Invalidate the cached index so it is rebuilt on the next query."""
        if self.use_blob:
            blob_client = self.index_client.get_blob_client(self._index_blob_path())
            try:
                blob_client.delete_blob()
            except Exception:
                pass
            return
        try:
            if self.index_path.exists():
                self.index_path.unlink()
        except Exception:
            pass

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
