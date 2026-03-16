/* ========= DOM refs (use these IDs in your HTML) ========= */
const sessionContainer = document.getElementById("session-container"); // LEFT list (sessions)
const chatContainer = document.getElementById("chat-container");    // RIGHT chat panel
const userInput1 = document.getElementById("user-input1");

// Optional
const activeSessionTitleEl = document.getElementById("active-session-title") || { textContent: "" };
const sendBtnEl = document.getElementById("send-btn");
const newSessionBtnEl = document.getElementById("new-session-btn");
const deleteSessionBtnEl = document.getElementById("delete-session-btn");

/* ========= Utilities ========= */
const LS_SESSIONS_KEY = "chat.sessions.v1";
const LS_ACTIVE_KEY = "chat.activeSessionId.v1";

function nowTs() { return Date.now(); }
function formatTime(ts) {
  if (!ts && ts !== 0) return "";
  const d = new Date(ts || Date.now());
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function uid(prefix = "s") { return `${prefix}-${Math.random().toString(36).slice(2, 9)}`; }
function safeParseJSON(json, fallback) { try { return JSON.parse(json); } catch { return fallback; } }
function escapeHTML(str) {
  // Keep simple; avoids over-encoding bugs
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };
  return String(str).replace(/[&<>]/g, ch => map[ch]);
}

/* ========= Backend config ========= */
const BACKEND_URL = "http://localhost:7071/api";

/* ========= Default welcome message ========= */
const WELCOME_MSG = `Hello! I'm the **Legal RAG Assistant** 👋

I can help you query and analyse your uploaded legal documents — contracts, NDAs, compliance policies, SLAs, and more.

**To get started:**
1. Click **📄 Manage Docs** in the sidebar to upload your legal documents (**.md, .txt, .pdf, .docx**)
2. Once uploaded, ask me any question about the documents

**Example questions you can ask:**
- *"What are the confidentiality obligations in the NDA?"*
- *"What is the notice period in the employment contract?"*
- *"What GDPR rights does a data subject have?"*
- *"What compliance risks exist in the SLA?"*

How can I help you today?`;

/* ========= Format agent API response as readable markdown ========= */
function agentIcon(name) {
  const icons = { Retriever: "📋", LegalAnalyst: "⚖️", ComplianceOfficer: "🛡️", Summarizer: "📝" };
  return icons[name] || "🤖";
}

function formatAgentResponse(data) {
  const finalAnswer = data.final_answer || "No answer returned.";
  const steps = (data.agent_responses || [])
    .filter(r => r.agent !== "Summarizer")
    .map(r => `**${agentIcon(r.agent)} ${r.agent}**\n\n${r.message}`)
    .join("\n\n---\n\n");

  let output = finalAnswer;
  if (steps) {
    output += `\n\n<details>\n<summary>🔍 View Agent Analysis Steps</summary>\n\n${steps}\n\n</details>`;
  }
  return output;
}

/* ========= Storage ========= */
// function loadSessions() {
//   const raw = localStorage.getItem(LS_SESSIONS_KEY);
//   const sessions = safeParseJSON(raw, null);
//   if (!sessions || !Array.isArray(sessions)) {
//     const bootstrap = [{
//       id: uid("s"),
//       title: "Welcome",
//       createdAt: nowTs(),
//       messages: [
//         { sender: "bot", content: "Hi! Select or create a session to begin.", time: nowTs(), md: false, status: "final" }
//       ]
//     }];
//     localStorage.setItem(LS_SESSIONS_KEY, JSON.stringify(bootstrap));
//     return bootstrap;
//   }
//   return sessions;
// }

function loadSessions() {
  const raw = localStorage.getItem(LS_SESSIONS_KEY);

  // Use [] as fallback to guarantee an Array
  let sessions = safeParseJSON(raw, []);

  // If it's not an array (null, object, string), reset to []
  if (!Array.isArray(sessions)) {
    sessions = [];
  }


  // If empty, seed with ONE bootstrap session (an object), inside an array
  if (sessions.length === 0) {
    const bootstrapSession = {
      id: uid("s"),
      title: "Welcome",
      createdAt: nowTs(),
      messages: [
        { sender: "bot", content: WELCOME_MSG, time: nowTs(), md: true, status: "final" }
      ]
    };
    sessions = [bootstrapSession]; // <-- assign a flat array, do NOT .push([]) or nest arrays
    localStorage.setItem(LS_SESSIONS_KEY, JSON.stringify(sessions));

    return sessions;
  }



  const navEntry = performance.getEntriesByType('navigation')[0];
  const isReload = navEntry && navEntry.type === 'reload';

  if (isReload) {
    saveSessions(sessions);
  }

  if (!isReload) {
    if (!window.name) {
      console.log("New tab or window detected");
      window.name = "initialized";

      const bootstrap = {
        id: uid("s"),
        title: "Welcome",
        createdAt: nowTs(),
        messages: [
        ]
      };
      saveSessions(sessions);
      sessions.unshift(bootstrap);
      console.log(JSON.stringify(bootstrap));
      let activeSessionId = bootstrap.id;
      saveActiveSessionId(activeSessionId);

      // chatContainer.innerHTML = "";
      // activeSessionTitleEl.textContent = bootstrap.title;
      localStorage.setItem(LS_SESSIONS_KEY, JSON.stringify(sessions));

      buildSessionListItem(sessions);
      // return bootstrap;
      return sessions;
    }
  }

  return sessions;
}


function saveSessions(sessions) { localStorage.setItem(LS_SESSIONS_KEY, JSON.stringify(sessions)); }
function loadActiveSessionId() { return localStorage.getItem(LS_ACTIVE_KEY); }
function saveActiveSessionId(id) { id ? localStorage.setItem(LS_ACTIVE_KEY, String(id)) : localStorage.removeItem(LS_ACTIVE_KEY); }

/* ========= App State ========= */
let sessions = loadSessions();
let activeSessionId = loadActiveSessionId() || (sessions[0] ? sessions[0].id : uid("s"));
if (!loadActiveSessionId() && sessions[0]) saveActiveSessionId(activeSessionId);

/* ========= Message status flags ========= */
const MSG_STATUS = {
  PENDING: "pending", // interim / streaming
  FINAL: "final"    // completed
};

/* ========= RIGHT panel bubbles ========= */
function createUserBubble(content, time, isMarkdown = false) {
  const msgDiv = document.createElement("div");
  msgDiv.classList.add("message", "user");

  const contentDiv = document.createElement("div");
  contentDiv.style.whiteSpace = "normal";
  contentDiv.style.overflowWrap = "break-word";
  if (isMarkdown && window.marked && typeof marked.parse === "function") {
    contentDiv.innerHTML = marked.parse(content || "");
  } else {
    contentDiv.textContent = content || "";
  }
  msgDiv.appendChild(contentDiv);

  const timeSpan = document.createElement("div");
  timeSpan.style.fontSize = "0.75em";
  timeSpan.style.color = "#666";
  timeSpan.style.marginTop = "8px";
  timeSpan.textContent = formatTime(time);
  msgDiv.appendChild(timeSpan);

  return msgDiv;
}

function createBotBubble(content, time, isMarkdown = true) {
  const botWrapper = document.createElement("div");
  botWrapper.classList.add("message", "bot");

  const icon = document.createElement("div");
  icon.className = "bot-icon";
  botWrapper.appendChild(icon);

  const thinkingContent = document.createElement("div");
  thinkingContent.className = "thinking-content";

  const responseArea = document.createElement("div");
  responseArea.className = "response-area";
  if (isMarkdown && window.marked && typeof marked.parse === "function") {
    responseArea.innerHTML = marked.parse(content || "");
  } else {
    responseArea.textContent = content || "";
  }
  thinkingContent.appendChild(responseArea);
  botWrapper.appendChild(thinkingContent);

  const timeSpan = document.createElement("div");
  timeSpan.style.fontSize = "0.75em";
  timeSpan.style.color = "#666";
  timeSpan.style.marginTop = "6px";
  timeSpan.textContent = formatTime(time);
  botWrapper.appendChild(timeSpan);

  return botWrapper;
}

function appendMessage(content, sender, isMarkdown = false, timeOverride) {
  const node = sender === "bot"
    ? createBotBubble(content, timeOverride, isMarkdown)
    : createUserBubble(content, timeOverride, isMarkdown);
  chatContainer.appendChild(node);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return node;
}

/* ========= Preview selection (LEFT list) =========
   Rule:
   - While streaming / with provisional entries: ignore them.
   - Prefer last FINAL bot message; else last FINAL user message; else None.
*/
function isFinalMsg(m) {
  // finalized if not provisional AND status !== pending AND has content
  const notProvisional = !m._provisional;
  const notPending = (m.status || MSG_STATUS.FINAL) !== MSG_STATUS.PENDING;
  const hasText = !!String(m.content || "").trim();
  return notProvisional && notPending && hasText;
}

function pickPreviewMessagePreferBot(session) {
  if (!Array.isArray(session.messages) || session.messages.length === 0) return null;

  // Prefer last FINAL bot
  for (let i = session.messages.length - 1; i >= 0; i--) {
    const m = session.messages[i];
    if (m?.sender === "bot" && isFinalMsg(m)) return m;
  }
  // Else last FINAL user
  for (let i = session.messages.length - 1; i >= 0; i--) {
    const m = session.messages[i];
    if (m?.sender === "user" && isFinalMsg(m)) return m;
  }
  return null;
}


/* ========= LEFT sessions list ========= */
function buildSessionListItem(session) {
  let sessions = loadSessions();
  let activeSessionId = loadActiveSessionId() || (sessions[0] ? sessions[0].id : uid("s"));
  const item = document.createElement("div");
  item.className = "session-item";
  item.dataset.sessionId = String(session.id);

  // 1) manual override, 2) computed finalized preview, 3) fallback
  const pm = pickPreviewMessagePreferBot(session);
  const previewRaw = (pm ? String(pm.content) : "No messages yet ");
  const preview = escapeHTML(previewRaw).slice(0, 60);

  item.innerHTML = `
    <div class="session-preview" contenteditable="true" spellcheck="false" style="font-size:16px;">${preview}</div>
    <small>${formatTime(session.createdAt)}</small>
  `;

  console.log("inner html" + item.innerHTML);

  if (String(session.id) === String(activeSessionId)) {
    item.classList.add("active");
  }

  // Activate session on item click (ignore clicks while editing preview)
  item.addEventListener("click", function (e) {
    if (e.target && e.target.classList.contains("session-preview")) return;

    const id = this.dataset.sessionId;
    if (!id) return;

    activeSessionId = id;
    saveActiveSessionId(activeSessionId);

    chatContainer.innerHTML = "";
    renderMessages(id);

    [...sessionContainer.children].forEach(el => el.classList?.remove("active"));
    this.classList.add("active");
  });

  // Editable preview behavior (independent field; does NOT touch messages)
  const previewEl = item.querySelector(".session-preview");
  let originalText = previewRaw;

  previewEl.addEventListener("mousedown", (e) => e.stopPropagation());
  // previewEl.addEventListener("click", (e) => {

  //   // if (e.target && e.target.classList.contains("session-preview")) return;
  //   // item.dataset.sessionId = String(session.id);
  //   const id = String(session.id);
  //   if (!id) return;

  //   activeSessionId = id;
  //   saveActiveSessionId(activeSessionId);

  //   chatContainer.innerHTML = "";
  //   renderMessages(id);

  //   [...sessionContainer.children].forEach(el => el.classList?.remove("active"));
  //   item.innerHTML = `
  //   <div class="session-preview" contenteditable="true" spellcheck="false" style="font-size:16px;">${preview}</div>
  //   <small>${formatTime(session.createdAt)}</small>
  // `;
  //   item.classList.add("active");
  // }
  // );

  previewEl.addEventListener("click", (e) => {

    const item = e.target.closest(".session-item");
    if (!item) return;

    const id = item.dataset.sessionId;
    if (!id) return;

    activeSessionId = id;
    saveActiveSessionId(activeSessionId);

    chatContainer.innerHTML = "";
    renderMessages(id);

    [...sessionContainer.children].forEach((el) => el.classList.remove("active"));
    item.classList.add("active");

  }
  );

  previewEl.addEventListener("focus", () => {
    originalText = session.previewText ?? (pm ? String(pm.content) : "No messages yet 2");
  });

  previewEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); previewEl.blur(); }
    else if (e.key === "Escape") { e.preventDefault(); previewEl.innerText = originalText; previewEl.blur(); }
  });

  previewEl.addEventListener("paste", (e) => {
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData)?.getData?.("text") || "";
    document.execCommand("insertText", false, text);
  });

  previewEl.addEventListener("blur", () => {
    const id = item.dataset.sessionId;
    if (!id) return;

    const editedText = previewEl.innerText.trim();
    const sess = sessions.find(s => String(s.id) === String(id));
    if (!sess) return;

    // Keep preview independent
    sess.previewText = editedText;
    saveSessions(sessions);

    const safeTrunc = escapeHTML(editedText || (pm ? String(pm.content) : "No messages yet 3")).slice(0, 60);
    previewEl.innerHTML = safeTrunc;
  });

  return item;
}

function renderSessionList() {
  if (!sessionContainer) return;
  sessionContainer.innerHTML = "";
  sessions.forEach(s => sessionContainer.appendChild(buildSessionListItem(s)));
}

/* ========= RIGHT messages ========= */
function renderMessages(id) {
  const session = sessions.find(s => String(s.id) === String(id));
  if (!session) return;

  activeSessionTitleEl.textContent = session.title || "Session";
  chatContainer.innerHTML = "";

  session.messages.forEach((m, idx) => {
    // Render provisional bubble with loader while streaming
    if (m.sender === "bot" && m._provisional === true) {
      const botWrapper = document.createElement("div");
      botWrapper.classList.add("message", "bot");
      botWrapper.setAttribute("data-provisional-index", String(idx));

      const icon = document.createElement("div");
      icon.className = "bot-icon";
      botWrapper.appendChild(icon);

      const thinkingContent = document.createElement("div");
      thinkingContent.className = "thinking-content";

      const responseArea = document.createElement("div");
      responseArea.className = "response-area";
      if (m.md && window.marked && typeof marked.parse === "function") {
        responseArea.innerHTML = marked.parse(m.content || "");
      } else {
        responseArea.textContent = m.content || "";
      }
      thinkingContent.appendChild(responseArea);

      const loaderBlock = document.createElement("div");
      loaderBlock.style.display = "flex";
      loaderBlock.style.alignItems = "center";
      loaderBlock.style.marginTop = "2px";

      const thinkingText = document.createElement("span");
      thinkingText.className = "thinking-text";
      thinkingText.style.marginRight = "8px";
      loaderBlock.appendChild(thinkingText);

      const loadingDots = document.createElement("div");
      loadingDots.className = "loading-dots";
      loadingDots.style.display = "inline-block";
      for (let i = 0; i < 3; i++) {
        const sdot = document.createElement("span");
        sdot.style.display = "inline-block";
        sdot.style.width = "6px";
        sdot.style.height = "6px";
        sdot.style.margin = "0 1px";
        sdot.style.borderRadius = "50%";
        loadingDots.appendChild(sdot);
      }
      loaderBlock.appendChild(loadingDots);
      thinkingContent.appendChild(loaderBlock);

      botWrapper.appendChild(thinkingContent);

      const timeSpan = document.createElement("div");
      timeSpan.style.fontSize = "0.75em";
      timeSpan.style.color = "#666";
      timeSpan.style.marginTop = "6px";
      timeSpan.textContent = m.time ? formatTime(m.time) : "";
      botWrapper.appendChild(timeSpan);

      chatContainer.appendChild(botWrapper);
      chatContainer.scrollTop = chatContainer.scrollHeight;
    } else {
      const isMd = m.md === true || m.sender === "bot";
      appendMessage(m.content, m.sender, isMd, m.time);
    }
  });

  chatContainer.scrollTop = chatContainer.scrollHeight;
}

/* ========= CRUD ========= */
function createSession(title = " ") {
  const welcomeMsg = { sender: "bot", content: WELCOME_MSG, time: nowTs(), md: true, status: "final" };
  const s = { id: uid("s"), title, createdAt: nowTs(), messages: [welcomeMsg] };
  sessions.unshift(s);
  saveSessions(sessions);

  activeSessionId = s.id;
  saveActiveSessionId(activeSessionId);

  renderSessionList();
  chatContainer.innerHTML = "";
  activeSessionTitleEl.textContent = s.title;
  renderMessages(activeSessionId);
}

function deleteSession(id) {
  const idx = sessions.findIndex(s => String(s.id) === String(id));
  if (idx === -1) return;

  sessions.splice(idx, 1);
  saveSessions(sessions);

  if (sessions.length) {
    activeSessionId = sessions[0].id;
    saveActiveSessionId(activeSessionId);
    renderSessionList();
    chatContainer.innerHTML = "";
    renderMessages(activeSessionId);
  } else {
    activeSessionId = null;
    saveActiveSessionId(null);
    renderSessionList();
    chatContainer.innerHTML = "";
    activeSessionTitleEl.textContent = "Select a session";
  }
}

/* ========= Add message to a SPECIFIC session ========= */
function addMessageToSession(sessionId, content, sender = "user", md = false, opts = {}) {
  const { skipRender = false, status = MSG_STATUS.FINAL } = opts; // default: FINAL
  const s = sessions.find(x => String(x.id) === String(sessionId));
  if (!s) return;

  const last = s.messages[s.messages.length - 1];
  if (last && last.sender === sender && last.content === content && (last.status || MSG_STATUS.FINAL) === status) {
    return; // duplicate guard
  }

  const msg = { sender, content, time: nowTs(), md, status, _provisional: false };
  s.messages.push(msg);
  saveSessions(sessions);

  if (!skipRender && String(activeSessionId) === String(sessionId)) {
    appendMessage(content, sender, md, msg.time);
  }

  renderSessionList();
}

/* ========= Clean up empty sessions (no messages) ========= */
const setActiveId = (id) => localStorage.setItem(LS_ACTIVE_KEY, id);
const getActiveId = () => localStorage.getItem(LS_ACTIVE_KEY);

function removeEmptySessions() {
  const current = loadSessions();
  const cleaned = current.filter(s => Array.isArray(s.messages) && s.messages.length > 0);

  const activeId = getActiveId();
  if (activeId && !cleaned.some(s => s.id === activeId)) {
    localStorage.removeItem(LS_ACTIVE_KEY);
  }

  saveSessions(cleaned);
}

/* ========= Streaming sendMessage() with provisional storage ========= */
const streamingLocks = new Set();
let sending = false;

async function sendMessage(e) {
  if (sending) return;
  sending = true;
  try {
    const message = (userInput1?.value || "").trim();
    if (!message) return;

    // const targetSessionId = activeSessionId;
    const targetSessionId = loadActiveSessionId();
    const sessRef = sessions.find(s => String(s.id) === String(targetSessionId));
    if (!sessRef) { alert("Please select or create a session first."); return; }

    // 1) store user's message
    addMessageToSession(targetSessionId, message, "user", false);
    if (userInput1) userInput1.value = "";

    // 2) create provisional bot message IN STORAGE (so list ignores it) and IN UI
    const provisionalMsg = { sender: "bot", content: "", time: "", md: true, _provisional: true, status: MSG_STATUS.PENDING };
    sessRef.messages.push(provisionalMsg);
    saveSessions(sessions);
    renderSessionList();               // list will ignore pending/provisional entries
    if (String(loadActiveSessionId()) === String(targetSessionId)) renderMessages(targetSessionId);

    const provisionalIndex = sessRef.messages.length - 1;

    // 3) Call Legal RAG Azure Function endpoint
    try {
      const resp = await fetch(BACKEND_URL + "/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: message, top_k: 3 })
      });

      if (!resp.ok) {
        const errBody = await resp.json().catch(() => ({}));
        throw new Error(errBody.error || `Server error: ${resp.status}`);
      }

      const data = await resp.json();
      const formattedResponse = formatAgentResponse(data);

      // Finalize the provisional message with formatted response
      sessRef.messages[provisionalIndex].content = formattedResponse;
      sessRef.messages[provisionalIndex].time = nowTs();
      sessRef.messages[provisionalIndex]._provisional = false;
      sessRef.messages[provisionalIndex].status = MSG_STATUS.FINAL;
      saveSessions(sessions);
      renderSessionList();

      if (String(loadActiveSessionId()) === String(targetSessionId)) {
        renderMessages(targetSessionId);
      }
    } catch (err) {
      // error: finalize provisional with error text
      sessRef.messages[provisionalIndex].content = "⚠️ Error: " + err.message;
      sessRef.messages[provisionalIndex].time = nowTs();
      sessRef.messages[provisionalIndex]._provisional = false;
      sessRef.messages[provisionalIndex].status = MSG_STATUS.FINAL;
      saveSessions(sessions);
      renderSessionList();

      if (String(loadActiveSessionId()) === String(targetSessionId)) renderMessages(targetSessionId);
    }
  } finally {
    sending = false;
  }
}

/* ========= Document Management ========= */
async function loadDocumentList() {
  const listEl = document.getElementById("doc-list");
  if (!listEl) return;
  listEl.innerHTML = "<em>Loading...</em>";
  try {
    const resp = await fetch(BACKEND_URL + "/documents");
    const data = await resp.json();
    if (!data.documents || data.documents.length === 0) {
      listEl.innerHTML = "<em>No documents in knowledge base.</em>";
      return;
    }
    listEl.innerHTML = data.documents.map(d =>
      `<div class="doc-item">
        <span class="doc-name">📄 ${escapeHTML(d.filename)}</span>
        <span class="doc-size">${(d.size_bytes / 1024).toFixed(1)} KB</span>
        <button class="doc-delete-btn" onclick="deleteDocument('${escapeHTML(d.filename)}')">🗑 Delete</button>
      </div>`
    ).join("");
  } catch (e) {
    listEl.innerHTML = `<em style="color:red">Error loading documents: ${e.message}</em>`;
  }
}

async function uploadDocument() {
  const fileInput = document.getElementById("doc-file-input");
  const statusEl = document.getElementById("upload-status");
  if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
    statusEl.textContent = "Please select a .md, .txt, .pdf, or .docx file.";
    statusEl.style.color = "red";
    return;
  }
  const file = fileInput.files[0];
  const ext = file.name.split(".").pop().toLowerCase();
  statusEl.textContent = "Uploading...";
  statusEl.style.color = "#555";
  try {
    let resp;
    if (ext === "pdf" || ext === "docx") {
      // Binary files — send as multipart/form-data
      const formData = new FormData();
      formData.append("file", file, file.name);
      resp = await fetch(BACKEND_URL + "/upload", {
        method: "POST",
        body: formData
      });
    } else {
      // Text files (.md / .txt) — send as JSON
      const content = await file.text();
      resp = await fetch(BACKEND_URL + "/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, content })
      });
    }
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `Error ${resp.status}`);
    statusEl.textContent = `✅ '${file.name}' uploaded. Index will rebuild on next query.`;
    statusEl.style.color = "green";
    fileInput.value = "";
    loadDocumentList();
  } catch (e) {
    statusEl.textContent = `❌ Upload failed: ${e.message}`;
    statusEl.style.color = "red";
  }
}

async function deleteDocument(filename) {
  if (!confirm(`Delete '${filename}' from the knowledge base?`)) return;
  try {
    const resp = await fetch(BACKEND_URL + "/documents/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `Error ${resp.status}`);
    loadDocumentList();
  } catch (e) {
    alert(`Delete failed: ${e.message}`);
  }
}

function openDocsModal() {
  document.getElementById("docs-modal").style.display = "flex";
  loadDocumentList();
}

function closeDocsModal() {
  document.getElementById("docs-modal").style.display = "none";
  document.getElementById("upload-status").textContent = "";
}

/* ========= Buttons / Keyboard ========= */
function newSession() { createSession(" "); }
function deleteActiveSession() {
  if (!activeSessionId) return;
  const ok = confirm("Delete this session? This cannot be undone.");
  if (ok) deleteSession(activeSessionId);
}

/* ========= Init ========= */
window.addEventListener("DOMContentLoaded", () => {
  // 1) clean BEFORE rendering so blanks vanish immediately
  // removeEmptySessions();
  const navEntry = performance.getEntriesByType('navigation')[0];
  const isReload = navEntry && navEntry.type === 'reload';

  if (!isReload) {
    if (!window.name) {
      removeEmptySessions();
    }
  }

  // removeEmptySessions();
  if (isReload) {
    removeEmptySessions();
  }

  // 2) refresh globals from storage
  sessions = loadSessions();
  activeSessionId = loadActiveSessionId() || (sessions[0] ? sessions[0].id : null);
  if (activeSessionId) saveActiveSessionId(activeSessionId);

  // 3) render
  renderSessionList();
  if (activeSessionId) { renderMessages(activeSessionId); } else { chatContainer.innerHTML = ""; }

  // 4) wire events
  sendBtnEl?.addEventListener("click", sendMessage);
  userInput1?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  newSessionBtnEl?.addEventListener("click", newSession);
  deleteSessionBtnEl?.addEventListener("click", deleteActiveSession);
});
