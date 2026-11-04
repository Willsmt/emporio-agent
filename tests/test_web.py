import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from emporio.agent.agent import Agent
from emporio.agent.providers.base import ProviderError
from emporio.agent.tool_registry import build_tools
from emporio.agent.types import ModelTurn
from emporio.web import app as web_app
from emporio.web.app import MAX_MESSAGES_PER_SESSION, create_app
from emporio.web.rate_limit import SlidingWindowLimiter
from emporio.web.sessions import SessionStore
from emporio.web.transcripts import TranscriptStore, mask_contacts
from fakes import ScriptedProvider, tool_call


class ReplyingProvider(ScriptedProvider):
    """Looks up the Takamine once per message, then answers; fails when the message says 'falha'."""

    def __init__(self):
        super().__init__([])

    def generate(self, system_prompt, history, tools):
        last = history[-1]
        if last["role"] == "user" and "falha" in last["text"]:
            raise ProviderError("503")
        if last["role"] == "user":
            return ModelTurn(text="", tool_calls=[tool_call("get_product", product_id=95)])
        return ModelTurn(text="O Takamine GD20 custa **R$ 2.199,00**.", tool_calls=[])


def make_client(conn, tmp_path, demo_mode=True):
    agent = Agent(ReplyingProvider(), build_tools(conn, today=lambda: date(2026, 11, 3)), system_prompt=lambda: "p")
    transcripts = TranscriptStore(tmp_path / "transcripts.db")
    app = create_app(agent, transcripts, info={"provider": "fake", "model": "scripted"},
                     limiter=SlidingWindowLimiter(1000, 60), demo_mode=demo_mode)
    test_client = TestClient(app)
    test_client.transcripts = transcripts
    return test_client


@pytest.fixture
def client(conn, tmp_path):
    return make_client(conn, tmp_path, demo_mode=True)


def new_session(client):
    return client.post("/api/sessions").json()["session_id"]


def test_health_in_demo_mode_shows_model(client):
    assert client.get("/health").json() == {"status": "ok", "demo_mode": True, "provider": "fake", "model": "scripted"}
    assert client.get("/api/docs").status_code == 200


def test_production_mode_hides_internals(conn, tmp_path):
    client = make_client(conn, tmp_path, demo_mode=False)
    assert client.get("/health").json() == {"status": "ok", "demo_mode": False}
    assert client.get("/api/docs").status_code == 404
    session_id = new_session(client)
    body = client.post("/api/chat", json={"session_id": session_id, "message": "Quanto custa?"}).json()
    assert body["reply"].startswith("O Takamine")
    assert body["tool_trace"] is None


def test_store_page_and_chat_page_are_served(client):
    store, chat = client.get("/"), client.get("/chat")
    assert store.status_code == chat.status_code == 200
    assert 'id="fab"' in store.text and '<script src="/static/js/store.js">' in store.text
    assert 'id="log"' in chat.text and '<script src="/static/js/chat.js">' in chat.text
    store_js, chat_js = client.get("/static/js/store.js"), client.get("/static/js/chat.js")
    assert store_js.status_code == chat_js.status_code == 200
    assert "/api/storefront" in store_js.text and "postMessage" in chat_js.text
    for css in ("/static/css/store.css", "/static/css/chat.css"):
        assert client.get(css).status_code == 200


@pytest.mark.parametrize("path", ["/", "/chat"])
def test_pages_have_no_inline_scripts_styles_or_handlers(client, path):
    html = client.get(path).text
    assert "<style" not in html and "<script>" not in html and "style=" not in html
    assert not re.search(r"\son[a-z]+\s*=", html)


@pytest.mark.parametrize("path", ["/", "/chat", "/static/js/store.js", "/static/css/chat.css"])
def test_pages_and_static_files_send_strict_csp(client, path):
    headers = client.get(path).headers
    csp = headers["content-security-policy"]
    assert "script-src 'self'" in csp and "style-src 'self'" in csp and "frame-ancestors 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_api_docs_still_work_in_demo_mode_without_page_csp(client):
    for path in ("/api/docs", "/api/openapi.json"):
        response = client.get(path)
        assert response.status_code == 200
        assert "content-security-policy" not in response.headers


def test_storefront_endpoint_returns_injected_data(conn, tmp_path):
    agent = Agent(ReplyingProvider(), build_tools(conn, today=lambda: date(2026, 11, 3)), system_prompt=lambda: "p")
    app = create_app(agent, TranscriptStore(tmp_path / "t.db"), storefront=lambda: {"categories": [{"name": "Violões"}]})
    assert TestClient(app).get("/api/storefront").json() == {"categories": [{"name": "Violões"}]}


def test_storefront_endpoint_is_404_when_not_configured(client):
    assert client.get("/api/storefront").status_code == 404


def test_chat_returns_reply_and_tool_trace(client):
    session_id = new_session(client)
    response = client.post("/api/chat", json={"session_id": session_id, "message": "Quanto custa o Takamine GD20?"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "O Takamine GD20 custa **R$ 2.199,00**."
    assert body["tool_trace"] == [{"tool": "get_product", "arguments": {"product_id": 95}, "ok": True}]
    assert body["messages_left"] == MAX_MESSAGES_PER_SESSION - 1


def test_unknown_session_is_404(client):
    response = client.post("/api/chat", json={"session_id": "nope", "message": "oi"})
    assert response.status_code == 404


@pytest.mark.parametrize("message", ["", "x" * 1001])
def test_invalid_message_length_is_rejected(client, message):
    response = client.post("/api/chat", json={"session_id": new_session(client), "message": message})
    assert response.status_code == 422


def test_blank_message_is_rejected(client):
    response = client.post("/api/chat", json={"session_id": new_session(client), "message": "   "})
    assert response.status_code == 422


def test_provider_failure_is_503_and_conversation_continues(client):
    session_id = new_session(client)
    failed = client.post("/api/chat", json={"session_id": session_id, "message": "falha"})
    assert failed.status_code == 503
    ok = client.post("/api/chat", json={"session_id": session_id, "message": "preço?"})
    assert ok.status_code == 200
    assert ok.json()["messages_left"] == MAX_MESSAGES_PER_SESSION - 1  # failed turn does not count


def test_message_limit_per_session(client, monkeypatch):
    monkeypatch.setattr(web_app, "MAX_MESSAGES_PER_SESSION", 2)
    session_id = new_session(client)
    for _ in range(2):
        assert client.post("/api/chat", json={"session_id": session_id, "message": "oi"}).status_code == 200
    assert client.post("/api/chat", json={"session_id": session_id, "message": "oi"}).status_code == 429


def test_transcript_is_stored_with_contacts_masked(client):
    session_id = new_session(client)
    client.post("/api/chat", json={"session_id": session_id, "message": "Pedido 7, leticia.rocha@jmail.com"})
    messages = client.transcripts.messages(session_id)
    assert messages[0] == ("customer", "Pedido 7, ***")
    assert messages[1][0] == "assistant"


def test_rate_limit_per_client(conn, tmp_path):
    agent = Agent(ReplyingProvider(), build_tools(conn, today=lambda: date(2026, 11, 3)), system_prompt=lambda: "p")
    app = create_app(agent, TranscriptStore(tmp_path / "t.db"), limiter=SlidingWindowLimiter(2, 60))
    client = TestClient(app)
    assert client.post("/api/sessions").status_code == 201
    assert client.post("/api/sessions").status_code == 201
    assert client.post("/api/sessions").status_code == 429


@pytest.mark.parametrize("text, expected", [
    ("meu email é Ana.Souza+loja@mail.com.br", "meu email é ***"),
    ("liga no (67) 99812-3456 ou 67998123456", "liga no *** ou ***"),
    ("meu cel +55 67 99812-3456", "meu cel ***"),
    ("tel 67 99812 3456 ou 67.99812.3456", "tel *** ou ***"),
    ("pedido 7, total R$ 2.199,00", "pedido 7, total R$ 2.199,00"),
])
def test_mask_contacts(text, expected):
    assert mask_contacts(text) == expected


def test_sessions_expire_and_are_capped():
    now = [0.0]
    store = SessionStore(ttl_seconds=10, max_sessions=2, clock=lambda: now[0])
    first = store.create()
    now[0] = 5
    second = store.create()
    now[0] = 6
    store.create()                       # cap reached: evicts the least recently used (first)
    assert store.get(first.id) is None
    now[0] = 20                          # second expired (last used at 5, ttl 10)
    assert store.get(second.id) is None


def test_sliding_window_limiter():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 60, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    now[0] = 61
    assert limiter.allow("a")


def test_limiter_memory_stays_bounded():
    now = [0.0]
    limiter = SlidingWindowLimiter(5, 60, clock=lambda: now[0], max_keys=3)
    for ip in ("a", "b", "c"):
        limiter.allow(ip)
    now[0] = 120                      # all three are outside the window now
    limiter.allow("d")                # tracking a new key at capacity prunes the stale ones
    assert len(limiter) == 1


def test_global_daily_cap(conn, tmp_path):
    agent = Agent(ReplyingProvider(), build_tools(conn, today=lambda: date(2026, 11, 3)), system_prompt=lambda: "p")
    app = create_app(agent, TranscriptStore(tmp_path / "t.db"), limiter=SlidingWindowLimiter(1000, 60),
                     daily_limiter=SlidingWindowLimiter(1, 86400))
    client = TestClient(app)
    first, second = new_session(client), new_session(client)
    assert client.post("/api/chat", json={"session_id": first, "message": "oi"}).status_code == 200
    blocked = client.post("/api/chat", json={"session_id": second, "message": "oi"})
    assert blocked.status_code == 429
    assert "limite diário" in blocked.json()["detail"]
