# Legal RAG Application — User Manual

**Version:** 1.0  
**Last Updated:** March 2026  
**Prepared by:** LTIMindTree

---

## Table of Contents

1. [What Is This Application?](#1-what-is-this-application)
2. [How It Works — Architecture Overview](#2-how-it-works--architecture-overview)
3. [The Four AI Agents](#3-the-four-ai-agents)
4. [System Requirements](#4-system-requirements)
5. [Project Structure](#5-project-structure)
6. [Setup and Installation](#6-setup-and-installation)
7. [Running the Application](#7-running-the-application)
8. [Using the Web Interface](#8-using-the-web-interface)
9. [Document Management](#9-document-management)
10. [Asking Legal Questions](#10-asking-legal-questions)
11. [Understanding the Response](#11-understanding-the-response)
12. [REST API Reference](#12-rest-api-reference)
13. [Configuration Reference](#13-configuration-reference)
14. [Troubleshooting](#14-troubleshooting)
15. [Security Notes](#15-security-notes)

---

## 1. What Is This Application?

The **Legal RAG Application** is an AI-powered legal question-answering system built for legal teams, compliance officers, and engineers who need to query a private library of legal documents using plain English.

### Core Capabilities

| Feature                   | Description                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| **Document Upload**       | Upload `.md`, `.txt`, `.pdf`, or `.docx` legal documents into a private knowledge base     |
| **Semantic Search (RAG)** | Automatically finds the most relevant passages from your documents using vector similarity |
| **Multi-Agent Analysis**  | A chain of 4 specialised AI agents analyses your question from multiple legal perspectives |
| **Plain English Q&A**     | Ask questions in natural language — no need to know which document or clause to look at    |
| **Session Management**    | Maintain separate conversation sessions for different matters or clients                   |
| **Chat Interface**        | Clean web UI accessible from any browser — no installation required for end users          |

### What "RAG" Means

**RAG = Retrieval-Augmented Generation.** Instead of asking a general AI that only knows public information, this system:

1. Searches _your_ uploaded documents to find the most relevant text passages
2. Gives those passages as context to the AI agents
3. The agents reason and answer _based on your documents_, not general knowledge

This means the answers are grounded in your actual contracts, policies, and legal documents — not generic legal advice.

---

## 2. How It Works — Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    USER (Browser)                        │
│              http://localhost:8080                       │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (JSON / FormData)
                       ▼
┌─────────────────────────────────────────────────────────┐
│           FRONTEND  (Express.js — Port 8080)             │
│   index.html  •  script.js  •  style.css                 │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API calls
                       ▼
┌─────────────────────────────────────────────────────────┐
│         BACKEND  (Azure Functions — Port 7071)           │
│                   function_app.py                        │
│                                                         │
│   GET  /api/documents      → list uploaded files        │
│   POST /api/upload         → upload a new document      │
│   POST /api/documents/delete → delete a document        │
│   POST /api/query          → ask a legal question       │
└──────┬─────────────────────────────────┬────────────────┘
       │                                 │
       ▼                                 ▼
┌─────────────┐               ┌─────────────────────────┐
│  RAG Engine │               │  Multi-Agent Chain       │
│  (rag.py)   │               │  (agents.py)             │
│             │               │                         │
│ • Load docs │               │  Agent 1: Retriever     │
│ • Chunk text│               │  Agent 2: LegalAnalyst  │
│ • Embed     │──context──────│  Agent 3: Compliance    │
│ • Retrieve  │               │  Agent 4: Summarizer    │
│ • Cache     │               │                         │
└─────┬───────┘               └──────────┬──────────────┘
      │                                  │
      ▼                                  ▼
┌─────────────────┐          ┌───────────────────────────┐
│  Knowledge Base │          │  Azure OpenAI              │
│  data/          │          │  gpt-4.1-mini (chat)       │
│  knowledge_base/│          │  text-embedding-ada-002   │
│  *.md *.txt     │          │  (embeddings)              │
│  *.pdf *.docx   │          └───────────────────────────┘
│  index.json     │
└─────────────────┘
```

### Step-by-Step Flow of a Query

1. User types a question in the browser and clicks **Send**
2. Frontend POSTs the question to `http://localhost:7071/api/query`
3. Backend's RAG engine converts the question into a vector embedding (via Azure OpenAI `text-embedding-ada-002`)
4. The embedding is compared against all document chunks using cosine similarity to find the top-5 most relevant passages
5. The question + retrieved passages are passed to the 4-agent chain
6. Each agent processes in sequence (round-robin) up to 5 total messages
7. The final answer, agent reasoning steps, and source chunks are returned to the browser
8. The frontend renders the answer with collapsible "Agent Steps" section

---

## 3. The Four AI Agents

The application uses **AutoGen AgentChat** to run a pipeline of 4 specialised AI agents. Each has a distinct role:

### Agent 1 — Retriever

> _"Read the context chunks carefully and summarise the most relevant facts."_

- Reads the raw retrieved passages from your documents
- Identifies the key facts that are relevant to the question
- Does **not** give legal advice — purely extracts and summarises facts
- Acts as the foundation for all downstream agents

### Agent 2 — LegalAnalyst

> _"Provide a structured legal analysis: identify applicable clauses, obligations, and interpretations."_

- Builds on the Retriever's summary
- Identifies which clauses, sections, or obligations are relevant
- Flags ambiguities or differing interpretations
- Cites source chunks using `[1]`, `[2]`, etc.

### Agent 3 — ComplianceOfficer

> _"Identify compliance risks, regulatory obligations, and red flags."_

- Reviews the Legal Analyst's findings
- Looks for compliance gaps, regulatory exposure, or action items
- Highlights what the organisation **must do** vs. what is recommended
- Flags anything that needs escalation

### Agent 4 — Summarizer

> _"Produce one clear, structured final answer with a legal disclaimer."_

- Synthesises all prior agents' outputs into a single coherent answer
- Formats the answer in a logical, readable structure
- Always appends a professional disclaimer:
  _"This is AI-generated analysis for informational purposes only and does not constitute legal advice."_

---

## 4. System Requirements

### For Running the Application Locally

| Component                      | Requirement                                                                   |
| ------------------------------ | ----------------------------------------------------------------------------- |
| **OS**                         | Windows 10/11 (tested), macOS, or Linux                                       |
| **Python**                     | 3.10 or higher                                                                |
| **Node.js**                    | 16 or higher                                                                  |
| **npm**                        | Bundled with Node.js                                                          |
| **Azure Functions Core Tools** | v4 (`npm install -g azure-functions-core-tools@4`)                            |
| **Azure OpenAI resource**      | With `gpt-4.1-mini` (chat) and `text-embedding-ada-002` (embeddings) deployed |
| **Git**                        | For cloning and version control                                               |

### Azure OpenAI — Required Deployments

| Deployment Name          | Model                  | Purpose                                         |
| ------------------------ | ---------------------- | ----------------------------------------------- |
| `gpt-4.1-mini`           | GPT-4.1 Mini           | Agent reasoning and answer generation           |
| `text-embedding-ada-002` | text-embedding-ada-002 | Turning text into vectors for similarity search |

---

## 5. Project Structure

```
Legal_Rag_Application/
│
├── src/
│   └── legal_rag_app/                ← Core Python package
│       ├── __init__.py
│       ├── __main__.py               ← Enables: python -m legal_rag_app
│       ├── config.py                 ← Reads env vars, builds Azure OpenAI client
│       ├── rag.py                    ← Document loading, chunking, embedding, retrieval
│       ├── agents.py                 ← 4 AutoGen agents + orchestration
│       └── main.py                   ← CLI entrypoint
│
├── Front_End_Application/            ← Web UI
│   ├── index.html                    ← Main page layout
│   ├── script.js                     ← API calls, session management, chat logic
│   ├── style.css                     ← UI styling
│   ├── server.js                     ← Express.js server (serves static files)
│   ├── package.json                  ← Node dependencies
│   ├── LTIMINDTREE.svg               ← Header logo
│   └── botimage.png                  ← Chatbot avatar
│
├── data/
│   └── knowledge_base/               ← YOUR uploaded legal documents live here
│       └── index.json                ← Auto-generated vector cache (do not edit)
│
├── test_documents/                   ← Sample documents for testing
│   ├── nda_agreement.md
│   ├── employment_contract.md
│   ├── gdpr_compliance_policy.md
│   ├── service_level_agreement.md
│   └── ip_assignment_agreement.md
│
├── function_app.py                   ← Azure Function HTTP API (4 endpoints)
├── host.json                         ← Azure Functions runtime configuration
├── local.settings.json               ← Local secrets — Azure keys (NEVER commit)
├── requirements.txt                  ← Python dependencies
├── pyproject.toml                    ← Python package metadata
├── .env                              ← Alternative local secrets file
├── .gitignore                        ← Excludes secrets and node_modules
├── EXPLANATION.md                    ← Technical deep-dive for developers
└── USER_MANUAL.md                    ← This file
```

---

## 6. Setup and Installation

### Step 1 — Clone the Repository

```bash
git clone https://github.com/GAURAV30012001/legal-rag-application.git
cd legal-rag-application
```

### Step 2 — Create and Activate Virtual Environment

```powershell
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:

- `autogen-agentchat==0.7.5` + `autogen-ext[openai]==0.7.5` — multi-agent framework
- `azure-functions>=1.21.0` — Azure Functions runtime
- `openai>=2.0.0` — Azure OpenAI SDK
- `numpy>=1.26.0` — vector math for cosine similarity
- `python-dotenv>=1.0.1` — loads `.env` file
- `pypdf>=4.0.0` — PDF text extraction
- `python-docx>=1.1.0` — DOCX text extraction

### Step 4 — Install Frontend Dependencies

```powershell
cd Front_End_Application
npm install
cd ..
```

### Step 5 — Configure Azure OpenAI Credentials

Create the file `local.settings.json` in the project root with your Azure OpenAI details:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_OPENAI_API_KEY": "your-azure-openai-key-here",
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
    "AZURE_OPENAI_CHAT_DEPLOYMENT": "gpt-4.1-mini",
    "AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT": "text-embedding-ada-002"
  },
  "Host": {
    "CORS": "http://localhost:8080"
  }
}
```

> **Important:** `local.settings.json` is in `.gitignore` and will never be committed. Keep this file secure.

---

## 7. Running the Application

You need **two terminal windows** running simultaneously.

### Terminal 1 — Start the Backend (Azure Functions)

```powershell
# From the project root: Legal_Rag_Application/
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="C:\path\to\Legal_Rag_Application\src"
func start
```

Wait for the output:

```
Http Functions:
    delete_document: [POST] http://localhost:7071/api/documents/delete
    list_documents:  [GET]  http://localhost:7071/api/documents
    query:           [GET,POST] http://localhost:7071/api/query
    upload_document: [POST] http://localhost:7071/api/upload

Host lock lease acquired by instance ID ...
```

The backend is now running at **http://localhost:7071**.

### Terminal 2 — Start the Frontend (Express Server)

```powershell
# From: Legal_Rag_Application/Front_End_Application/
npm start
```

You should see:

```
Server running at http://localhost:8080
```

### Open the Application

Open your browser and navigate to:

```
http://localhost:8080
```

> **Note:** Always start the backend (Terminal 1) before the frontend (Terminal 2). The frontend will still load without the backend, but API calls will fail.

---

## 8. Using the Web Interface

### Layout Overview

```
┌──────────────────────────────────────────────────────────┐
│  [LTIMindTree Logo]     Legal RAG Application             │  ← Header
├────────────┬─────────────────────────────────────────────┤
│            │                                             │
│  + New     │                                             │
│  Session   │       Chat Messages Appear Here            │
│            │                                             │
│  📄 Manage │                                             │
│  Docs      │                                             │
│            │                                             │
│  Session 1 │  ┌──────────────────────────────────────┐  │
│  Session 2 │  │  Type a message...         [Send]    │  │  ← Input
│            │  └──────────────────────────────────────┘  │
└────────────┴─────────────────────────────────────────────┘
  ↑ Sidebar                    ↑ Chat Area
```

### Sidebar Controls

| Button             | Action                                                            |
| ------------------ | ----------------------------------------------------------------- |
| **+ New Session**  | Starts a fresh conversation (clears chat history from the screen) |
| **📄 Manage Docs** | Opens the document upload/management modal                        |
| **Session tiles**  | Switch between previously active sessions                         |

### Chat Input

- Type your legal question in the text box
- Press **Enter** or click **Send**
- The system will show a loading indicator while the agents process
- The response appears as a formatted message from the bot

---

## 9. Document Management

Documents are the foundation of the system. The AI agents can only answer questions based on the documents you have uploaded.

### Opening the Document Manager

Click **📄 Manage Docs** in the sidebar. A modal dialog will appear with two sections:

```
┌─────────────────────────────────────┐
│  📄 Manage Knowledge Base       [✕] │
├─────────────────────────────────────┤
│  Upload Document                    │
│  ┌────────────────────────────┐     │
│  │  Choose File    [⬆ Upload] │     │
│  └────────────────────────────┘     │
│  Accepted: .md .txt .pdf .docx      │
├─────────────────────────────────────┤
│  Documents in Knowledge Base        │
│  ┌────────────────────────────┐     │
│  │  nda_agreement.md  [Delete]│     │
│  │  employment.pdf    [Delete]│     │
│  └────────────────────────────┘     │
│                    [🔄 Refresh List] │
└─────────────────────────────────────┘
```

### Uploading a Document

1. Click **Choose File** and select a document from your computer
2. Supported formats: `.md`, `.txt`, `.pdf`, `.docx`
3. Click **⬆ Upload**
4. A green confirmation message confirms the upload: _"✅ 'filename' uploaded. Index will rebuild on next query."_

> **How upload works by format:**
>
> - `.pdf` / `.docx` — sent as binary via multipart form upload; text is extracted on the server using `pypdf` / `python-docx`
> - `.md` / `.txt` — sent as JSON (text content); stored directly

### Viewing Uploaded Documents

Click **🔄 Refresh List** to see all documents currently in the knowledge base. Each entry shows the filename and a **Delete** button.

### Deleting a Document

1. Click **Delete** next to the document you want to remove
2. Confirm in the prompt dialog
3. The document is permanently removed from the knowledge base
4. The vector index will automatically rebuild on the next query

### Index Rebuild

The system caches a vector index (`data/index.json`) to avoid re-embedding all documents on every query. The cache is **automatically invalidated** whenever:

- A new document is uploaded
- A document is deleted
- A document file is modified (detected via file modification timestamp)

The first query after an upload will take slightly longer as the index rebuilds. Subsequent queries use the cached index.

---

## 10. Asking Legal Questions

### Good Questions to Ask

The system is optimised for questions that are directly answerable from the uploaded documents. Examples:

| Question Type                 | Example                                                                          |
| ----------------------------- | -------------------------------------------------------------------------------- |
| **Clause lookup**             | "What is the notice period for termination in the employment contract?"          |
| **Obligation identification** | "What are the confidentiality obligations of the recipient in the NDA?"          |
| **Compliance check**          | "Does our GDPR policy cover the right to data portability?"                      |
| **Risk identification**       | "What compliance risks exist in our SLA?"                                        |
| **Comparison**                | "What are the differences in termination clauses across the uploaded contracts?" |
| **Deadline/timeline**         | "How many days does the employee have to serve notice after confirmation?"       |
| **Definition**                | "How is 'Confidential Information' defined in the NDA?"                          |

### Tips for Better Results

- **Be specific:** "What is the termination notice period?" is better than "Tell me about termination."
- **Name the document:** "In the NDA, what..." helps the retrieval agent focus.
- **Ask one question at a time:** Multi-part questions may get partial answers.
- **Use legal terms when you know them:** The system understands legal vocabulary.

### What the System Cannot Do

- Answer questions about documents that have **not been uploaded**
- Provide real-time information (case law, new legislation)
- Replace advice from a qualified legal professional
- Perform calculations or compare numbers across documents reliably

---

## 11. Understanding the Response

A typical response has two parts:

### Part 1 — Final Answer

The primary response, written by the **Summarizer agent**, appears directly in the chat. It is formatted in markdown with:

- Clear numbered/bulleted points
- **Bold text** for key obligations or risks
- Source references like `[1]`, `[2]` pointing to retrieved document chunks
- A legal disclaimer at the end

**Example:**

> **Termination Notice Period**
>
> Based on the uploaded employment contract:
>
> 1. **During probation (first 6 months):** Either party may terminate with **14 days' notice**.
> 2. **After confirmation:** Either party must give **3 calendar months' written notice**.
> 3. The employer may also elect to **pay salary in lieu of notice** instead of requiring the employee to serve the notice period.
>
> ---
>
> _This is AI-generated analysis for informational purposes only and does not constitute legal advice._

### Part 2 — Agent Steps (Collapsible)

Below the final answer, a collapsible section labelled **"▶ Agent Steps (4)"** shows the individual contributions of each agent. Click it to expand and see:

- **Retriever:** The raw facts extracted from the documents
- **LegalAnalyst:** The structured legal analysis with clause references
- **ComplianceOfficer:** Compliance risks and recommended actions
- **Summarizer:** The final synthesised answer (same as Part 1)

This section is valuable for engineers and legal reviewers who want to audit the reasoning chain.

---

## 12. REST API Reference

The backend exposes 4 REST API endpoints at `http://localhost:7071/api/`.

### GET `/api/documents`

Returns all documents currently in the knowledge base.

**Response:**

```json
{
  "documents": [
    {
      "filename": "nda_agreement.md",
      "size_bytes": 4521,
      "last_modified": 1742120000.0
    }
  ],
  "count": 1
}
```

---

### POST `/api/upload`

Upload a new document to the knowledge base.

**For `.md` / `.txt` files — JSON body:**

```json
{
  "filename": "my_contract.md",
  "content": "# Contract\n\nFull text of the document..."
}
```

**For `.pdf` / `.docx` files — multipart/form-data:**

```
POST /api/upload
Content-Type: multipart/form-data

file=<binary file data>
```

**Response (201 Created):**

```json
{
  "message": "Document 'my_contract.md' uploaded successfully. Index rebuilds on next query.",
  "filename": "my_contract.md",
  "size_bytes": 4521
}
```

---

### POST `/api/documents/delete`

Delete a document from the knowledge base.

**Request body:**

```json
{
  "filename": "my_contract.md"
}
```

**Response (200 OK):**

```json
{
  "message": "Document 'my_contract.md' deleted successfully."
}
```

---

### POST `/api/query`

Ask a legal question. This is the main endpoint.

**Request body:**

```json
{
  "question": "What is the notice period for termination?"
}
```

**Response (200 OK):**

```json
{
  "question": "What is the notice period for termination?",
  "context_chunks": [
    {
      "chunk_id": "employment_contract.md-3",
      "source": "employment_contract.md",
      "text": "...either party may terminate with three (3) calendar months written notice...",
      "score": 0.91
    }
  ],
  "agent_responses": [
    { "agent": "Retriever", "content": "..." },
    { "agent": "LegalAnalyst", "content": "..." },
    { "agent": "ComplianceOfficer", "content": "..." },
    { "agent": "Summarizer", "content": "..." }
  ],
  "final_answer": "Based on the uploaded employment contract..."
}
```

---

## 13. Configuration Reference

### `local.settings.json` (Backend — never commit)

| Key                                  | Description                                                    |
| ------------------------------------ | -------------------------------------------------------------- |
| `AZURE_OPENAI_API_KEY`               | Your Azure OpenAI resource API key                             |
| `AZURE_OPENAI_ENDPOINT`              | Your resource endpoint URL                                     |
| `AZURE_OPENAI_API_VERSION`           | API version (e.g. `2024-12-01-preview`)                        |
| `AZURE_OPENAI_CHAT_DEPLOYMENT`       | Deployment name for chat model (e.g. `gpt-4.1-mini`)           |
| `AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT` | Deployment name for embeddings (e.g. `text-embedding-ada-002`) |
| `Host.CORS`                          | Allowed frontend origin (e.g. `http://localhost:8080`)         |

### `host.json` (Azure Functions runtime)

| Setting           | Value                | Meaning                    |
| ----------------- | -------------------- | -------------------------- |
| `version`         | `"2.0"`              | Azure Functions v2 runtime |
| `extensionBundle` | Python worker config | Handles HTTP triggers      |

### RAG Parameters (in `rag.py`)

| Parameter    | Default          | Description                          |
| ------------ | ---------------- | ------------------------------------ |
| `chunk_size` | `800` characters | Size of each text chunk              |
| `overlap`    | `120` characters | Overlap between consecutive chunks   |
| `top_k`      | `5`              | Number of chunks retrieved per query |

### Agent Parameters (in `agents.py`)

| Parameter               | Value                 | Description                                                                            |
| ----------------------- | --------------------- | -------------------------------------------------------------------------------------- |
| `MaxMessageTermination` | `5`                   | Maximum total messages across all agents before stopping                               |
| Team strategy           | `RoundRobinGroupChat` | Agents speak in fixed order: Retriever → LegalAnalyst → ComplianceOfficer → Summarizer |

---

## 14. Troubleshooting

### "Failed to fetch" or CORS Error in Browser

**Cause:** CORS not configured, or the backend is not running.  
**Fix:**

1. Ensure the backend (`func start`) is running at port 7071
2. Verify `local.settings.json` has `"Host": { "CORS": "http://localhost:8080" }`
3. Restart the backend after any change to `local.settings.json`

---

### "No documents found in data/knowledge_base"

**Cause:** The knowledge base directory is empty.  
**Fix:** Upload at least one document via the "Manage Docs" modal before running a query.

---

### Upload fails for PDF/DOCX

**Cause:** `pypdf` or `python-docx` not installed.  
**Fix:**

```powershell
.\.venv\Scripts\python.exe -m pip install "pypdf>=4.0.0" "python-docx>=1.1.0"
```

---

### First query after upload is very slow

**Cause:** The vector index is rebuilding — all document chunks are being re-embedded via Azure OpenAI. This is normal.  
**Note:** Subsequent queries use the cached `index.json` and are much faster.

---

### `func start` command not found

**Cause:** Azure Functions Core Tools not installed or not on PATH.  
**Fix:**

```powershell
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

---

### Python import errors when running `func start`

**Cause:** `PYTHONPATH` not set, so the `src/` folder is not found.  
**Fix:** Always set PYTHONPATH before starting:

```powershell
$env:PYTHONPATH="C:\Users\DELL\Documents\Legal_Rag_Application\src"
func start
```

---

### Port 7071 already in use

**Cause:** A previous `func start` process is still running.  
**Fix:**

```powershell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 7071 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique) -Force -ErrorAction SilentlyContinue
```

---

## 15. Security Notes

These are important points for engineers deploying or maintaining this application.

| Topic                       | Details                                                                                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Secrets management**      | `local.settings.json` and `.env` are in `.gitignore` and must never be committed. Use Azure Key Vault or environment variables for cloud deployment.          |
| **File upload validation**  | Only `.md`, `.txt`, `.pdf`, `.docx` files are accepted. Filenames are sanitised against path traversal attacks (e.g. `../../etc/passwd` is rejected).         |
| **Authentication**          | The local dev setup uses `AuthLevel.ANONYMOUS`. For production, implement Azure AD authentication or API key validation.                                      |
| **CORS**                    | Restricted to `http://localhost:8080` in local settings. Update for production domain.                                                                        |
| **Data stays private**      | Documents are stored locally in `data/knowledge_base/`. They are never sent to any external service except Azure OpenAI (which processes them for embedding). |
| **No SQL / injection risk** | There is no database. Document storage is plain file I/O.                                                                                                     |

---

## Appendix A — Sample Documents for Testing

Five sample legal documents are provided in the `test_documents/` folder:

| File                         | Legal Domain               | Good Test Questions                                      |
| ---------------------------- | -------------------------- | -------------------------------------------------------- |
| `nda_agreement.md`           | Contract / Confidentiality | "What are the exclusions from confidential information?" |
| `employment_contract.md`     | Employment Law             | "What is the non-compete clause duration?"               |
| `gdpr_compliance_policy.md`  | Data Privacy / GDPR        | "What must we do if there is a data breach?"             |
| `service_level_agreement.md` | IT / Commercial            | "What service credits apply if uptime falls below 95%?"  |
| `ip_assignment_agreement.md` | Intellectual Property      | "How is the royalty calculated in the IP agreement?"     |

To use them: convert any of these `.md` files to PDF or DOCX if you want to test PDF/DOCX upload, then upload them via **Manage Docs**.

---

## Appendix B — Technology Stack Summary

| Layer              | Technology                            | Version |
| ------------------ | ------------------------------------- | ------- |
| AI Framework       | AutoGen AgentChat                     | 0.7.5   |
| LLM Provider       | Azure OpenAI (gpt-4.1-mini)           | —       |
| Embeddings         | Azure OpenAI (text-embedding-ada-002) | —       |
| Backend Runtime    | Azure Functions (Python v2)           | v4      |
| Backend Language   | Python                                | 3.10+   |
| PDF Extraction     | pypdf                                 | 6.x     |
| DOCX Extraction    | python-docx                           | 1.x     |
| Frontend Server    | Express.js                            | 4.x     |
| Frontend Language  | Vanilla JavaScript + HTML5            | —       |
| Markdown Rendering | marked.js                             | CDN     |
| Vector Similarity  | NumPy cosine similarity               | —       |
| Index Cache        | JSON file on disk                     | —       |

---

_For technical architecture deep-dive, see [EXPLANATION.md](EXPLANATION.md)._  
_For source code, see [github.com/GAURAV30012001/legal-rag-application](https://github.com/GAURAV30012001/legal-rag-application)._
