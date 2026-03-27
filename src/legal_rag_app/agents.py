"""Multi-agent legal RAG chat using AutoGen 0.4+ (autogen_agentchat 0.7.x)."""
from __future__ import annotations

import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient


def _make_agent(name: str, system_message: str, model_client: AzureOpenAIChatCompletionClient) -> AssistantAgent:
    return AssistantAgent(
        name=name,
        model_client=model_client,
        system_message=system_message,
    )


def build_team(model_client: AzureOpenAIChatCompletionClient) -> RoundRobinGroupChat:
    """Create the four-agent analysis team with a round-robin chat strategy."""
    retriever = _make_agent(
        "Retriever",
        (
            "You are a Retrieval Specialist. Read the provided context chunks carefully "
            "and summarise the most relevant facts that directly help answer the user's question. "
            "Do not answer the question yourself — extract and highlight the key information from the context. "
            "Adapt to the document domain (legal, technical, HR, financial, etc.)."
        ),
        model_client,
    )

    analyst = _make_agent(
        "Analyst",
        (
            "You are a Document Analyst. Using the context and the Retriever's summary, provide a structured "
            "analysis relevant to the user's question. Identify key points, obligations, definitions, "
            "requirements, or findings from the documents — adapting your analysis to the document domain. "
            "Cite context chunks using [1], [2], etc. Flag any ambiguities or assumptions."
        ),
        model_client,
    )

    reviewer = _make_agent(
        "Reviewer",
        (
            "You are a Critical Reviewer. Review the Analyst's findings and identify any risks, gaps, "
            "edge cases, caveats, or important considerations the user should be aware of. "
            "Adapt your review to the document domain — for legal docs highlight compliance risks, "
            "for technical docs highlight implementation concerns, etc. "
            "Be specific and reference the source chunks."
        ),
        model_client,
    )

    summarizer = _make_agent(
        "Summarizer",
        (
            "You are a Summarizer. Consolidate all previous agent outputs into a clear, concise final "
            "answer for the user. Be direct and helpful. Cite the relevant context chunk numbers in brackets. "
            "If the question cannot be answered from the provided documents, clearly state that and suggest "
            "what additional information would be needed."
        ),
        model_client,
    )

    # 4 agents × 1 message each + 1 initial user message = 5 total
    termination = MaxMessageTermination(max_messages=5)

    return RoundRobinGroupChat(
        participants=[retriever, analyst, reviewer, summarizer],
        termination_condition=termination,
    )


async def _run_chat(model_client: AzureOpenAIChatCompletionClient, question: str, context: str) -> None:
    team = build_team(model_client)
    task = (
        "You are a team of specialised legal agents. Work together to answer the question below.\n"
        "Use the retrieved context and cite chunk numbers like [1], [2].\n\n"
        f"QUESTION: {question}\n\n"
        f"RETRIEVED CONTEXT:\n{context}"
    )
    await Console(team.run_stream(task=task))


def run_agentic_chat(
    model_client: AzureOpenAIChatCompletionClient,
    question: str,
    context: str,
) -> None:
    """Synchronous entry point — runs the async chat loop (CLI)."""
    asyncio.run(_run_chat(model_client, question, context))


async def run_agentic_chat_api(
    model_client: AzureOpenAIChatCompletionClient,
    question: str,
    context: str,
) -> dict:
    """Async entry point for the Azure Function — returns structured dict."""
    team = build_team(model_client)
    task = (
        "You are a team of document analysis agents. Work together to answer the question below "
        "based solely on the provided context. The documents may cover any domain — legal, technical, "
        "HR, financial, engineering, etc. Adapt your analysis to the document content.\n"
        "Use the retrieved context and cite chunk numbers like [1], [2].\n\n"
        f"QUESTION: {question}\n\n"
        f"RETRIEVED CONTEXT:\n{context}"
    )
    result = await team.run(task=task)

    agent_responses = []
    final_answer = ""
    for msg in result.messages:
        source = getattr(msg, "source", None)
        content = getattr(msg, "content", "")
        if source and source not in ("user", "User"):
            agent_responses.append({"agent": source, "message": content})
            if source == "Summarizer":
                final_answer = content

    return {
        "question": question,
        "agent_responses": agent_responses,
        "final_answer": final_answer,
    }
