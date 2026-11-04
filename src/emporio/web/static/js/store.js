// Data is inserted with textContent only: nothing from the API ever becomes HTML.
const brl = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

const panel = document.getElementById("panel");
const fab = document.getElementById("fab");
let frame = null, ready = false, pending = [];

function openChat(ask) {
  panel.hidden = false;
  fab.setAttribute("aria-expanded", "true");
  document.getElementById("fab-hint").hidden = true;
  if (!frame) {
    frame = el("iframe");
    frame.src = "/chat?embed=1";
    frame.title = "Chat com a Mel";
    panel.appendChild(frame);
  }
  if (ask) ready ? frame.contentWindow.postMessage({ ask }, location.origin) : pending.push(ask);
}
function closeChat() { panel.hidden = true; fab.setAttribute("aria-expanded", "false"); }

// The chat iframe signals when its session is ready; questions clicked before that are queued.
// Only messages from our own iframe count (frame is null until the widget is first opened).
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || !frame || e.source !== frame.contentWindow) return;
  if (!e.data || e.data.ready !== true) return;
  ready = true;
  for (const ask of pending.splice(0)) frame.contentWindow.postMessage({ ask }, location.origin);
});
fab.onclick = () => (panel.hidden ? openChat() : closeChat());
document.getElementById("close").onclick = closeChat;
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) closeChat(); });
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ask]");
  if (b) openChat(b.dataset.ask);
});

function askButton(text, ask) { const b = el("button", "ask", text); b.type = "button"; b.dataset.ask = ask; return b; }

function render(data) {
  const s = data.store;
  const status = document.getElementById("status");
  status.textContent = s.status.label;
  status.className = "status " + (s.status.open_now ? "open" : "closed");
  status.hidden = false;
  document.getElementById("address").textContent = s.address || "";
  document.getElementById("phone").textContent = s.phone ? "Telefone e WhatsApp: " + s.phone : "";
  const hours = document.getElementById("hours");
  for (const h of s.hours) { const tr = el("tr"); tr.append(el("td", null, h.days), el("td", null, h.time)); hours.append(tr); }
  document.getElementById("hours-note").textContent = s.hours_note;

  const cats = document.getElementById("categories");
  for (const c of data.categories) {
    const card = el("div", "card");
    card.append(el("h3", null, c.name), el("div", "meta", `${c.available} ${c.available === 1 ? "disponível" : "disponíveis"}`),
      askButton("Perguntar à Mel →", `Quais ${c.name.toLowerCase()} vocês têm disponíveis?`));
    cats.append(card);
  }
  const promos = document.getElementById("promotions");
  for (const p of data.promotions) {
    const card = el("div", "card promo");
    card.append(el("span", "tag", `-${Math.round(p.percent)}%`), el("h3", null, p.name), el("div", "meta", `${p.category} · ${p.label}`),
      el("div", "from", brl(p.list_price)), el("div", "price", brl(p.price)),
      askButton("Parcelas e PIX com a Mel →", `Quais as condições de pagamento do ${p.name}?`));
    promos.append(card);
  }
  if (!data.promotions.length) promos.append(el("p", "sub", "Nenhuma promoção ativa no momento."));
}

fetch("/api/storefront").then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then(render)
  .catch(() => document.getElementById("categories").append(el("p", "sub", "Não foi possível carregar o catálogo agora.")));
fetch("/health").then((r) => r.json()).then((h) => { if (h.demo_mode) document.getElementById("demo-note").style.display = "block"; }).catch(() => {});
