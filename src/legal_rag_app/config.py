from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_deployment: str
    azure_openai_embeddings_deployment: str
    knowledge_base_dir: Path
    index_path: Path
    storage_connection_string: str | None
    storage_container_docs: str
    storage_container_index: str
    index_blob_name: str


def _get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _get_env_optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load_config() -> AppConfig:
    project_root = Path(__file__).resolve().parents[2]
    knowledge_base_dir = project_root / "data" / "knowledge_base"
    index_path = project_root / "data" / "index.json"

    storage_connection_string = _get_env_optional("AZURE_STORAGE_CONNECTION_STRING")
    storage_container_docs = os.getenv("AZURE_STORAGE_CONTAINER_DOCS", "legalrag-docs")
    storage_container_index = os.getenv("AZURE_STORAGE_CONTAINER_INDEX", "legalrag-index")
    index_blob_name = os.getenv("AZURE_STORAGE_INDEX_BLOB", "index.json")

    return AppConfig(
        azure_openai_api_key=_get_env("AZURE_OPENAI_API_KEY"),
        azure_openai_endpoint=_get_env("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_version=_get_env("AZURE_OPENAI_API_VERSION"),
        azure_openai_deployment=_get_env("AZURE_OPENAI_DEPLOYMENT"),
        azure_openai_embeddings_deployment=_get_env("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT"),
        knowledge_base_dir=knowledge_base_dir,
        index_path=index_path,
        storage_connection_string=storage_connection_string,
        storage_container_docs=storage_container_docs,
        storage_container_index=storage_container_index,
        index_blob_name=index_blob_name,
    )


def build_model_client(cfg: AppConfig):
    """Return an AzureOpenAIChatCompletionClient for autogen_agentchat 0.7.x."""
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient  # lazy import

    return AzureOpenAIChatCompletionClient(
        model=cfg.azure_openai_deployment,
        azure_deployment=cfg.azure_openai_deployment,
        azure_endpoint=cfg.azure_openai_endpoint,
        api_key=cfg.azure_openai_api_key,
        api_version=cfg.azure_openai_api_version,
    )
