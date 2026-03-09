from __future__ import annotations

import argparse
import sys

from .agents import run_agentic_chat
from .config import build_model_client, load_config
from .rag import create_azure_client, format_context, retrieve_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Legal RAG Multi-Agent Demo")
    parser.add_argument("--question", type=str, help="Question to ask the agents")
    parser.add_argument("--top-k", type=int, default=3, help="Number of context chunks to retrieve")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    question = args.question or input("Enter your legal question: ").strip()
    if not question:
        print("No question provided.")
        sys.exit(1)

    try:
        cfg = load_config()
    except ValueError as exc:
        print(str(exc))
        print("Please update your .env file using .env.example as a reference.")
        sys.exit(1)

    client = create_azure_client(cfg)
    chunks = retrieve_context(cfg, client, question, top_k=args.top_k)
    context = format_context(chunks)

    model_client = build_model_client(cfg)
    run_agentic_chat(model_client, question, context)


if __name__ == "__main__":
    main()
