# Legal RAG Application — Complete Explanation

---

## What the Application Does (30-second pitch)

This is a **multi-agent legal question-answering system**. You give it a legal question in plain English. It:
1. Searches your legal document library to find the most relevant passages (**RAG** — Retrieval Augmented Generation)
2. Sends those passages to a **chain of 4 AI agents** who each analyse the question from a different angle
3. Returns a structured final answer with citations and a legal disclaimer

You can use it via **CLI** (terminal) or via a **REST HTTP endpoint** (Azure Function).

---

## Project Structure

```
Legal_Rag_Application/
│
├── src/legal_rag_app/       ← The actual Python package (core logic)
│   ├── config.py            ← Environment config + Azure OpenAI client factory
│   ├── rag.py               ← Document loading, chunking, embedding, retrieval
│   ├── agents.py            ← 4 AutoGen agents + orchestration
│   ├── main.py              ← CLI entrypoint
│   ├── __init__.py          ← Makes it a package
│   └── __main__.py          ← Enables `python -m legal_rag_app`
│
├── function_app.py          ← Azure Function HTTP trigger (REST API)
├── host.json                ← Azure Functions runtime config
├── local.settings.json      ← Azure keys for local func start
├── requirements.txt         ← All Python dependencies
├── pyproject.toml           ← Python package build config
├── data/
│   ├── knowledge_base/      ← Your legal documents (.md / .txt files)
│   │   ├── nda_summary.md
│   │   ├── employment_terms.md
│   │   └── privacy_policy.md
│   └── index.json           ← Auto-generated vector index cache
└── .env                     ← Your Azure credentials (gitignored)
```

---

## File 1 — `config.py` (The Configuration Layer)

**Purpose:** Reads environment variables, validates them, and builds the Azure OpenAI connection.

```python
from dotenv import load_dotenv
load_dotenv()
```
This line runs **at import time**. It reads your `.env` file from disk and injects every key=value pair into `os.environ`. So when any other file calls `os.getenv("AZURE_OPENAI_API_KEY")`, it finds the value.

```python
@dataclass(frozen=True)
class AppConfig:
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_deployment: str
    azure_openai_embeddings_deployment: str
    knowledge_base_dir: Path
    index_path: Path
```
This is a **frozen dataclass** — basically an immutable configuration object. `frozen=True` means once created you can't accidentally change a value. It holds 5 Azure credentials + 2 file paths.

```python
def _get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value
```
A private helper. If any required env variable is missing or empty, it raises a clear error immediately — fail fast before wasting an API call.

```python
def load_config() -> AppConfig:
    project_root = Path(__file__).resolve().parents[2]
    knowledge_base_dir = project_root / "data" / "knowledge_base"
    index_path = project_root / "data" / "index.json"
```
`Path(__file__).resolve().parents[2]` — `__file__` is `config.py` inside `src/legal_rag_app/`. `.parents[2]` goes 2 levels up: `legal_rag_app` → `src` → project root. This makes paths work regardless of where you run the app from.

```python
def build_model_client(cfg: AppConfig):
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
    return AzureOpenAIChatCompletionClient(
        model=cfg.azure_openai_deployment,       # "gpt-4.1-mini"
        azure_deployment=cfg.azure_openai_deployment,
        azure_endpoint=cfg.azure_openai_endpoint,
        api_key=cfg.azure_openai_api_key,
        api_version=cfg.azure_openai_api_version,
    )
```
This returns an **AutoGen-compatible Azure OpenAI client**. This is what all 4 agents call when they want to generate text. The lazy import (import inside function) avoids circular import issues at startup.

---

## File 2 — `rag.py` (The Brain of Retrieval)

**Purpose:** Load documents → split into chunks → embed as vectors → cache → retrieve most relevant chunks for a question.

### The `Chunk` dataclass

```python
@dataclass
class Chunk:
    chunk_id: str    # e.g. "nda_summary.md-0"
    source: str      # e.g. "nda_summary.md"
    text: str        # the actual text passage
    embedding: List[float]  # 1536-dimensional vector from Azure
```
Each document gets split into multiple chunks. Each chunk is stored as this object.

### `create_azure_client()`

```python
def create_azure_client(cfg: AppConfig) -> AzureOpenAI:
    return AzureOpenAI(
        api_key=cfg.azure_openai_api_key,
        azure_endpoint=cfg.azure_openai_endpoint,
        api_version=cfg.azure_openai_api_version,
    )
```
This creates a **raw OpenAI SDK client** (not AutoGen). It is used **only for generating embeddings** — the vector representations of text. It's separate from the AutoGen client which is used for chat.

### `load_documents()`

```python
for path in sorted(doc_dir.glob("**/*")):
    if path.suffix.lower() not in {".md", ".txt"}:
        continue
    content = path.read_text(encoding="utf-8")
    documents.append((path.name, content))
```
Scans the `data/knowledge_base/` folder recursively. Only picks up `.md` and `.txt` files. Returns a list of `(filename, content)` tuples.

### `chunk_text()`

```python
def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    text = " ".join(text.split())   # normalize whitespace
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)   # slide window back by 120 chars
```
Splits a long document into 800-character sliding windows with 120-character **overlap**. The overlap is crucial — it prevents a clause from being split across two chunks where neither has enough context to be meaningful. For example: if a sentence ends at char 800, the next chunk starts at char 680 so it sees the end of the previous sentence.

### `get_embedding()`

```python
def get_embedding(client: AzureOpenAI, model: str, text: str) -> List[float]:
    response = client.embeddings.create(model=model, input=text)
    return response.data[0].embedding
```
Calls Azure OpenAI's `text-embedding-ada-002` model. Sends text, gets back a list of 1536 floating-point numbers — a **semantic fingerprint** of the text. Similar texts produce similar vectors.

### `_index_needs_rebuild()` — the Smart Cache

```python
def _index_needs_rebuild(index_path: Path, files: List[Path]) -> bool:
    if not index_path.exists():
        return True
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    meta = payload.get("meta", {}).get("files", {})
    current = _file_mtimes(files)
    return meta != current
```
This compares the **last-modified timestamps** of your document files against what was recorded when the index was last built. If any file changed (or was added/deleted), it rebuilds the index. This saves money — embedding calls cost money, so you only pay when documents actually change.

### `build_or_load_index()` — the Core Indexing Function

```python
if _index_needs_rebuild(cfg.index_path, doc_paths):
    # For each document → split into chunks → embed each chunk → save to JSON
    for name, content in documents:
        for idx, chunk in enumerate(chunk_text(content)):
            embedding = get_embedding(client, cfg.azure_openai_embeddings_deployment, chunk)
            chunks.append(Chunk(...))
    payload = {
        "meta": {"files": _file_mtimes(doc_paths)},   # save timestamps
        "chunks": [chunk.__dict__ for chunk in chunks],
    }
    cfg.index_path.write_text(json.dumps(payload, ...))
```
On first run (or after document changes): reads all docs, chunks them, calls Azure to embed each chunk, serialises everything to `data/index.json`. On subsequent runs: just loads `index.json` from disk — instant, no API calls.

### `cosine_similarity()`

```python
def cosine_similarity(vec_a, vec_b) -> float:
    return float(np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b)))
```
The mathematical heart of semantic search. Dot product divided by product of magnitudes gives a value between -1 and 1. **1.0 = identical meaning. 0.0 = unrelated.** This is faster and more accurate than keyword matching.

### `retrieve_context()`

```python
def retrieve_context(cfg, client, question, top_k=3) -> List[Chunk]:
    chunks = build_or_load_index(cfg, client)               # load all chunks
    query_embedding = get_embedding(client, ..., question)  # embed the question
    return retrieve_top_k(chunks, query_embedding, top_k)   # compare & rank
```
This is what turns your plain English question into retrieved passages. It embeds the question using the same model as the documents, then finds the `top_k` chunks whose embeddings are most similar to the question's embedding.

### `format_context()`

```python
def format_context(chunks: List[Chunk]) -> str:
    for idx, chunk in enumerate(chunks, start=1):
        lines.append(f"[{idx}] Source: {chunk.source}\n{chunk.text}")
    return "\n\n".join(lines)
```
Formats the retrieved chunks into a numbered list like:
```
[1] Source: nda_summary.md
The NDA requires the Recipient to keep Confidential Information...

[2] Source: employment_terms.md
The employee agrees to a 12-month non-compete...
```
The `[1]`, `[2]` numbers are what agents cite in their responses.

---

## File 3 — `agents.py` (The Multi-Agent Brain)

**Purpose:** Define 4 specialised AI agents, form them into a team, run them in sequence.

### Why AutoGen 0.7.5?

This uses the **new 0.4+ async API** of AutoGen. Key classes:
- `AssistantAgent` — an AI agent with a name + system prompt + model client
- `RoundRobinGroupChat` — a team strategy that calls each agent in order, one after another
- `MaxMessageTermination` — stops the chat after N messages
- `Console` — streams output to terminal in real time

### `_make_agent()`

```python
def _make_agent(name, system_message, model_client) -> AssistantAgent:
    return AssistantAgent(
        name=name,
        model_client=model_client,
        system_message=system_message,
    )
```
A factory helper. Each agent gets a **unique name** and a **unique system prompt** that defines its personality/role. They all share the same `model_client` (same Azure OpenAI connection) but behave differently because of their system prompts.

### `build_team()` — The 4 Agents

**Agent 1 — Retriever:**
> *"Read the context chunks and summarise the most relevant facts. Do not give legal advice; just highlight key facts."*

**Role:** Reads the RAG context and distills what's relevant. Acts like a paralegal pulling the right passages.

**Agent 2 — LegalAnalyst:**
> *"Provide a structured legal analysis: identify applicable clauses, obligations, and interpretations. Cite [1], [2]. Flag ambiguities."*

**Role:** Takes the Retriever's summary + original context and gives a professional legal reading.

**Agent 3 — ComplianceOfficer:**
> *"Review the LegalAnalyst's findings. Identify compliance risks, regulatory obligations, and red flags."*

**Role:** Looks at the analysis through a risk/compliance lens — what could go wrong? What must the organisation do?

**Agent 4 — Summarizer:**
> *"Consolidate all previous agent outputs into a clear final answer. End with: 'DISCLAIMER: This output is for informational purposes only...'"*

**Role:** The final output layer. Reads everything the other 3 agents said and produces the clean answer for the user.

### `MaxMessageTermination(max_messages=5)`

```python
termination = MaxMessageTermination(max_messages=5)
```
AutoGen counts messages. The initial task message = 1. Then each of the 4 agents responds = 4 more. Total = 5. So the chat stops exactly after the Summarizer speaks. If this were set to 4, the Summarizer would never fire.

### `RoundRobinGroupChat`

```python
return RoundRobinGroupChat(
    participants=[retriever, analyst, compliance, summarizer],
    termination_condition=termination,
)
```
`RoundRobin` means they go in strict order: Retriever → LegalAnalyst → ComplianceOfficer → Summarizer. Each agent sees the **entire conversation history** so far, so the Summarizer sees everything the previous 3 said.

### CLI path — `run_agentic_chat()`

```python
def run_agentic_chat(model_client, question, context) -> None:
    asyncio.run(_run_chat(model_client, question, context))
```
Wraps the async function in `asyncio.run()` so it can be called from synchronous CLI code.

```python
async def _run_chat(...):
    await Console(team.run_stream(task=task))
```
`run_stream` gives token-by-token streaming. `Console` prints each token to terminal as it arrives — that's why you see the agents typing out their responses in real time.

### API path — `run_agentic_chat_api()`

```python
async def run_agentic_chat_api(...) -> dict:
    result = await team.run(task=task)   # non-streaming, waits for full result
    for msg in result.messages:
        source = getattr(msg, "source", None)
        content = getattr(msg, "content", "")
        if source and source != "user":
            agent_responses.append({"agent": source, "message": content})
            if source == "Summarizer":
                final_answer = content
    return {"question": ..., "agent_responses": [...], "final_answer": ...}
```
Instead of printing to console, this collects every agent's message into a list and returns a structured Python dictionary. The Azure Function then serialises this to JSON.

---

## File 4 — `main.py` (The CLI Entry Point)

```python
def main() -> None:
    args = parse_args()
    question = args.question or input("Enter your legal question: ").strip()
```
Accepts question via `--question` flag or interactive prompt.

```python
cfg = load_config()                                     # read .env
client = create_azure_client(cfg)                       # raw OpenAI for embeddings
chunks = retrieve_context(cfg, client, question, ...)   # RAG retrieval
context = format_context(chunks)                        # format as [1][2][3]
model_client = build_model_client(cfg)                  # AutoGen client for chat
run_agentic_chat(model_client, question, context)       # launch 4 agents
```
These 5 lines are the **entire pipeline** end to end. Each line corresponds to a stage.

**Run command:**
```powershell
python -m legal_rag_app --question "What are the key obligations in the NDA?"
```
`python -m legal_rag_app` works because `__main__.py` exists which calls `main()`.

---

## File 5 — `function_app.py` (The REST API Layer)

**Purpose:** Wrap the entire pipeline in an HTTP endpoint so any client (Postman, browser, mobile app) can call it.

```python
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
```
Creates the Azure Functions app. `ANONYMOUS` means no API key required to call it — good for local testing. In production you'd use `FUNCTION` level with a key.

```python
@app.route(route="query", methods=["GET", "POST"])
async def legal_query(req: func.HttpRequest) -> func.HttpResponse:
```
Registers this function to handle `GET` and `POST` requests at `/api/query`. The `async def` means Azure Functions runs this in an async event loop — required because the AutoGen agents are async.

### Input parsing

```python
question = req.params.get("question", "").strip()   # from URL ?question=...
top_k = int(req.params.get("top_k", 3))

if req.method == "POST":
    body = req.get_json()
    question = body.get("question", question).strip()
    top_k = int(body.get("top_k", top_k))
```
Supports both GET (query string) and POST (JSON body). POST values **override** GET values if both are present.

### The Pipeline (same 5 steps as CLI)

```python
cfg = load_config()
openai_client = create_azure_client(cfg)
chunks = retrieve_context(cfg, openai_client, question, top_k=top_k)
context = format_context(chunks)
model_client = build_model_client(cfg)
result = await run_agentic_chat_api(model_client, question, context)
```
Identical logic to CLI, but uses `await` and calls `run_agentic_chat_api` instead of `run_agentic_chat`.

### Response building

```python
context_sources = [{"chunk_id": c.chunk_id, "source": c.source, "text": c.text} for c in chunks]
response_body = {
    "question": question,
    "context_chunks": context_sources,   # what RAG retrieved
    **result,                            # agent_responses + final_answer
}
return func.HttpResponse(json.dumps(response_body, ...), status_code=200, mimetype="application/json")
```
The `**result` spreads the dict keys from `run_agentic_chat_api` directly into the response. Final JSON shape:
```json
{
  "question": "...",
  "context_chunks": [...],
  "agent_responses": [
    {"agent": "Retriever", "message": "..."},
    {"agent": "LegalAnalyst", "message": "..."},
    {"agent": "ComplianceOfficer", "message": "..."},
    {"agent": "Summarizer", "message": "..."}
  ],
  "final_answer": "... DISCLAIMER: ..."
}
```

---

## File 6 — `host.json` (Azure Functions Runtime Config)

```json
"healthMonitor": { "enabled": false }
```
Disables the health monitor that normally checks for a live Azure Storage account. Without this, `func start` throws errors locally because `local.settings.json` has `AzureWebJobsStorage: ""`.

```json
"extensionBundle": { "id": "Microsoft.Azure.Functions.ExtensionBundle", "version": "[4.*, 5.0.0)" }
```
Tells Azure Functions to use **v4 extension bundle** — this includes the HTTP trigger bindings. Without this the route decorator wouldn't work.

```json
"extensions": { "http": { "routePrefix": "api" } }
```
All HTTP routes are prefixed with `/api/`. That's why the URL is `/api/query` not just `/query`.

---

## File 7 — `pyproject.toml` (Package Config)

```toml
[tool.setuptools]
package-dir = {"" = "src"}
```
This tells Python's packaging tools that the actual packages live inside the `src/` folder. When you run `pip install -e .`, it adds `src/` to `sys.path`, making `import legal_rag_app` work from anywhere.

---

## The Complete Request Lifecycle (End to End)

Here is exactly what happens when you send:
```
GET http://localhost:7071/api/query?question=What+are+the+NDA+obligations
```

```
1. Azure Functions Core Tools receives HTTP GET on port 7071
   └─ Routes to function_app.py → legal_query()

2. function_app.py parses "What are the NDA obligations" from query string

3. load_config() reads local.settings.json / .env → builds AppConfig

4. create_azure_client(cfg) → raw AzureOpenAI SDK client for embeddings

5. retrieve_context() is called:
   a. build_or_load_index():
      - Checks data/index.json timestamps vs knowledge_base/ files
      - If cache valid → loads from JSON (fast, no API call)
      - If stale → re-embeds all chunks via Azure text-embedding-ada-002
   b. get_embedding(question) → 1536-dim vector for "What are the NDA obligations"
   c. cosine_similarity(question_vec, each_chunk_vec) for all chunks
   d. Returns top 3 highest-scoring chunks

6. format_context(chunks) → formats as [1] Source:...\n[2] Source:...\n

7. build_model_client(cfg) → AzureOpenAIChatCompletionClient (AutoGen)

8. await run_agentic_chat_api(model_client, question, context):
   a. build_team() creates 4 AssistantAgents + RoundRobinGroupChat
   b. task = "QUESTION: ...\nRETRIEVED CONTEXT: [1]...[2]...[3]..."
   c. await team.run(task=task):
      - Retriever reads context → summarises key facts → adds to history
      - LegalAnalyst reads all history → gives legal analysis → adds to history
      - ComplianceOfficer reads all history → identifies risks → adds to history
      - Summarizer reads all history → writes final answer + DISCLAIMER → stops
   d. Iterates result.messages → builds agent_responses list

9. function_app.py builds JSON response body

10. Returns HTTP 200 with JSON to the caller
```

---

## Key Design Decisions (Good for Demo Q&A)

| Decision | Why |
|---|---|
| **RAG before agents** | Agents only see relevant evidence, not hallucinate from training data. Prevents fabricated legal citations. |
| **4 separate agents vs. 1** | Each agent focuses on one concern. Separation forces explicit reasoning steps. Compliance can challenge the analyst. |
| **Chunk overlap (120 chars)** | Prevents clauses being split mid-sentence. Context bleeds between chunks. |
| **JSON index cache** | Embedding costs money. Rebuilding chunks on every request would be expensive. Cache is invalidated only on file change. |
| **Async function_app** | AutoGen's `team.run()` is async. If the Azure Function were sync, it would deadlock trying to run the event loop. |
| **Two separate OpenAI clients** | `AzureOpenAI` (raw SDK) for embeddings — cheaper, lighter. `AzureOpenAIChatCompletionClient` (AutoGen) for chat — heavier, tracks message history. |
| **`src/` layout** | Industry standard. Prevents accidentally importing local files instead of the installed package. |

---

## Quick Reference — Run Commands

### CLI
```powershell
# Activate venv
.venv\Scripts\Activate.ps1

# Run a question
python -m legal_rag_app --question "What are the key obligations in the NDA?"

# With custom top-k retrieval
python -m legal_rag_app --question "What are the employment termination terms?" --top-k 5
```

### Azure Function (local)
```powershell
# Activate venv and set PYTHONPATH
.venv\Scripts\Activate.ps1
$env:PYTHONPATH="C:\Users\DELL\Documents\Legal_Rag_Application\src"

# Start the function host
func start
```

### Test with curl
```bash
# GET
curl "http://localhost:7071/api/query?question=What+are+the+key+obligations+in+the+NDA"

# POST
curl -X POST "http://localhost:7071/api/query" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What are the employment termination terms?\"}"
```

### Test with PowerShell
```powershell
# GET
Invoke-RestMethod "http://localhost:7071/api/query?question=What+are+the+key+obligations+in+the+NDA"

# POST
Invoke-RestMethod -Method POST -Uri "http://localhost:7071/api/query" `
  -ContentType "application/json" `
  -Body '{"question": "What data privacy rights does the user have?"}'
```

---

## Technology Stack Summary

| Layer | Technology | Version |
|---|---|---|
| Multi-agent framework | AutoGen AgentChat | 0.7.5 |
| AutoGen Azure extension | autogen-ext[openai] | 0.7.5 |
| LLM | Azure OpenAI — gpt-4.1-mini | API v2024-12-01-preview |
| Embeddings | Azure OpenAI — text-embedding-ada-002 | same endpoint |
| Vector math | NumPy cosine similarity | >=1.26.0 |
| REST API | Azure Functions Python v2 | azure-functions >=1.21.0 |
| Config management | python-dotenv | >=1.0.1 |
| Knowledge base | Markdown / text files | local `data/knowledge_base/` |
| Index cache | JSON file | `data/index.json` |
