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


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Empório da Música" in response.text


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
    ("pedido 7", "pedido 7"),
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
