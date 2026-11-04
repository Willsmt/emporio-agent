if (new URLSearchParams(location.search).has("embed")) document.body.classList.add("embed");
const SUGGESTIONS = [
  "Quais violões vocês têm até R$ 1000?",
  "Quanto custa o Takamine GD20?",
  "Qual o endereço da loja?",
  "Me arrependi da minha compra, posso devolver?",
];
const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const chips = document.getElementById("chips");
let sessionId = null;

// Escape first, then allow only **bold** and line breaks: model output never becomes raw HTML (no XSS).
function renderSafe(text) {
  const escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
}

function addMessage(role, text, trace) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  if (role === "mel") {
    div.innerHTML = '<div class="who">Mel</div>' + renderSafe(text);
    if (trace && trace.length) {
      const details = document.createElement("details");
      details.className = "trace";
      const summary = document.createElement("summary");
      summary.textContent = `🔧 consultas internas: ${trace.length} ${trace.length === 1 ? "tool" : "tools"} (modo demonstração)`;
      details.appendChild(summary);
      for (const step of trace) {
        const code = document.createElement("code");
        code.textContent = `${step.tool}(${JSON.stringify(step.arguments)})${step.ok ? "" : "  ✗ erro"}`;
        details.appendChild(code);
      }
      div.appendChild(details);
    }
  } else {
    div.textContent = text;
  }
  log.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
  return div;
}

async function api(path, body) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Não foi possível enviar a mensagem.";
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return data;
}

async function startSession() {
  log.innerHTML = "";
  const data = await api("/api/sessions");
  sessionId = data.session_id;
  addMessage("mel", "Oi! Eu sou a **Mel**, assistente virtual do Empório da Música. Posso ajudar com instrumentos, preços, pedidos e políticas da loja. 🎸");
  renderChips();
}

function renderChips() {
  chips.innerHTML = "";
  for (const text of SUGGESTIONS) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.onclick = () => submit(text);
    chips.appendChild(b);
  }
}

async function submit(text) {
  text = text.trim();
  if (!text || send.disabled) return;
  chips.innerHTML = "";
  addMessage("you", text);
  input.value = "";
  send.disabled = true;
  const typing = document.createElement("div");
  typing.className = "typing";
  typing.textContent = "Mel está digitando…";
  log.appendChild(typing);
  try {
    const data = await api("/api/chat", { session_id: sessionId, message: text });
    addMessage("mel", data.reply, data.tool_trace);
    document.getElementById("footnote").textContent = `Protótipo · ${data.messages_left} mensagens restantes nesta conversa`;
  } catch (err) {
    addMessage("error", err.message);
    if (err.status === 404) await startSession();
  } finally {
    typing.remove();
    send.disabled = false;
    input.focus();
  }
}

// Embedded in the store page: accept questions only from the parent store page on the same origin
// (the "Perguntar à Mel" buttons).
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || e.source !== window.parent || window.parent === window) return;
  if (!e.data || typeof e.data.ask !== "string") return;
  submit(e.data.ask.slice(0, 1000));
});
form.addEventListener("submit", (e) => { e.preventDefault(); submit(input.value); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(input.value); }
});
document.getElementById("reset").onclick = () => startSession().catch((e) => addMessage("error", e.message));

fetch("/health").then((r) => r.json()).then((h) => {
  if (h.demo_mode) {
    document.getElementById("demo-banner").style.display = "block";
    if (h.model) document.getElementById("model").textContent = ` · ${h.provider}/${h.model}`;
  }
}).catch(() => {});
startSession().then(() => {
  if (window.parent !== window) window.parent.postMessage({ ready: true }, location.origin);
}).catch((e) => addMessage("error", e.message));
