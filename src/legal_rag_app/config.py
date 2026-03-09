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


def _get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_config() -> AppConfig:
    project_root = Path(__file__).resolve().parents[2]
    knowledge_base_dir = project_root / "data" / "knowledge_base"
    index_path = project_root / "data" / "index.json"

    return AppConfig(
        azure_openai_api_key=_get_env("AZURE_OPENAI_API_KEY"),
        azure_openai_endpoint=_get_env("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_version=_get_env("AZURE_OPENAI_API_VERSION"),
        azure_openai_deployment=_get_env("AZURE_OPENAI_DEPLOYMENT"),
        azure_openai_embeddings_deployment=_get_env("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT"),
        knowledge_base_dir=knowledge_base_dir,
        index_path=index_path,
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
