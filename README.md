# Legal RAG Multi-Agent Demo (AutoGen 0.7.5 + Azure OpenAI)

A fully agentic legal question-answering application powered by **AutoGen AgentChat 0.7.5** and **Azure OpenAI**.
Four specialised agents (**Retriever → Legal Analyst → Compliance Officer → Summarizer**) work together in a round-robin group chat, grounded by a local RAG knowledge base.

---

## Architecture

```
User Question
     │
     ▼
RAG Retrieval  ──► Embedding similarity search over data/knowledge_base/
     │
     ▼
 [Retriever Agent]       ← summarises retrieved chunks
     │
 [Legal Analyst Agent]   ← structured legal analysis with citations
     │
 [Compliance Officer]    ← risks, obligations, gaps
     │
 [Summarizer Agent]      ← final concise answer + disclaimer
```

---

## Quick Start (Windows PowerShell)

```powershell
# 1. Create & activate venv
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt
pip install -e .

# 3. Configure Azure OpenAI
copy .env.example .env
# Edit .env and fill in your values

# 4. Run
python -m legal_rag_app --question "What are the key obligations in the NDA?"
```

---

## Configuration (.env)

| Variable                             | Description                                           |
| ------------------------------------ | ----------------------------------------------------- |
| `AZURE_OPENAI_API_KEY`               | Your Azure OpenAI key                                 |
| `AZURE_OPENAI_ENDPOINT`              | e.g. `https://myresource.openai.azure.com/`           |
| `AZURE_OPENAI_API_VERSION`           | e.g. `2024-12-01-preview`                             |
| `AZURE_OPENAI_DEPLOYMENT`            | Chat model deployment name (e.g. `gpt-4.1-mini`)      |
| `AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT` | Embeddings deployment (e.g. `text-embedding-ada-002`) |

---

## Knowledge Base

Sample legal documents are in `data/knowledge_base/` (`.md` / `.txt`).
Add your own files and delete `data/index.json` to trigger a rebuild.

---

## Demo Notes

- First run builds `data/index.json` (local embedding index via Azure OpenAI).
- Subsequent runs load the cached index (fast).
- Use `--top-k N` to control how many context chunks are retrieved (default 3).
- Agent conversation is streamed live to the console.
