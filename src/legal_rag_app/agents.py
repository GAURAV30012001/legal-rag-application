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
            "You are a Retrieval Specialist with two modes:\n"
            "MODE 1 — DOCUMENT QUERY: When the user is asking about uploaded document content, "
            "extract and summarise the most relevant facts from the provided context chunks. "
            "Adapt to the domain (legal, technical, HR, financial, etc.).\n"
            "MODE 2 — OFF-TOPIC / CONVERSATIONAL: When the user's message is a greeting, personal "
            "question, small talk, or general knowledge question unrelated to the documents, "
            "output exactly the single token: OFF_TOPIC"
        ),
        model_client,
    )

    analyst = _make_agent(
        "Analyst",
        (
            "You are a Document Analyst with two modes:\n"
            "MODE 1 — DOCUMENT QUERY: If the Retriever provided document facts (not OFF_TOPIC), "
            "give structured analysis — key points, obligations, definitions, findings from the documents. "
            "Cite chunks as [1], [2], etc. Adapt to the document domain.\n"
            "MODE 2 — OFF-TOPIC: If the Retriever output OFF_TOPIC, output only: OFF_TOPIC"
        ),
        model_client,
    )

    reviewer = _make_agent(
        "Reviewer",
        (
            "You are a Critical Reviewer with two modes:\n"
            "MODE 1 — DOCUMENT QUERY: If prior agents provided document analysis (not OFF_TOPIC), "
            "identify risks, gaps, caveats, or important considerations. Reference source chunks. "
            "Adapt to the domain — legal: compliance risks; technical: implementation concerns, etc.\n"
            "MODE 2 — OFF-TOPIC: If prior agents output OFF_TOPIC, output only: OFF_TOPIC"
        ),
        model_client,
    )

    summarizer = _make_agent(
        "Summarizer",
        (
            "You are a Summarizer with two modes:\n"
            "MODE 1 — DOCUMENT QUERY: If prior agents provided document analysis, consolidate their "
            "findings into a clear, direct final answer. Cite relevant chunk numbers in brackets. "
            "If the question cannot be answered from the documents, say so honestly.\n"
            "MODE 2 — OFF-TOPIC: If prior agents output OFF_TOPIC, IGNORE the documents entirely. "
            "Respond naturally and helpfully as a friendly AI assistant, directly answering what the "
            "user actually asked. Do NOT cite documents, do NOT mention context chunks, "
            "do NOT reference any uploaded files."
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


async def run_direct_response_api(
    model_client: AzureOpenAIChatCompletionClient,
    question: str,
) -> dict:
    """Single-agent direct response — used when no documents are uploaded."""
    agent = AssistantAgent(
        name="Assistant",
        model_client=model_client,
        system_message=(
            "You are a helpful, friendly AI document assistant. "
            "You help users analyse their uploaded documents. "
            "When no documents are available, respond naturally and helpfully, "
            "and guide the user to upload documents when relevant to their question."
        ),
    )
    result = await agent.run(task=question)
    content = ""
    for msg in result.messages:
        if getattr(msg, "source", None) == "Assistant":
            content = getattr(msg, "content", "")
    return {
        "question": question,
        "agent_responses": [{"agent": "Assistant", "message": content}],
        "final_answer": content,
    }


async def run_agentic_chat_api(
    model_client: AzureOpenAIChatCompletionClient,
    question: str,
    context: str,
) -> dict:
    """Async entry point for the Azure Function — returns structured dict."""
    team = build_team(model_client)
    task = (
        "You are a team of intelligent assistant agents.\n\n"
        "STEP 1 — CLASSIFY the question before doing anything else:\n"
        "  • DOCUMENT QUERY: The user is asking about the content, details, analysis, or information "
        "in the uploaded documents.\n"
        "  • OFF-TOPIC / CONVERSATIONAL: The user is greeting, making small talk, asking a personal "
        "question, or asking about something completely unrelated to the documents.\n\n"
        "STEP 2 — RESPOND based on classification:\n"
        "  • DOCUMENT QUERY → Retriever extracts relevant facts; Analyst analyses; Reviewer reviews; "
        "Summarizer delivers a document-based answer with chunk citations [1], [2], etc.\n"
        "  • OFF-TOPIC → Retriever outputs OFF_TOPIC; all agents pass it through; "
        "Summarizer responds naturally as a friendly assistant WITHOUT any document references.\n\n"
        f"QUESTION: {question}\n\n"
        f"RETRIEVED CONTEXT (only use if this is a document query):\n{context}"
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
