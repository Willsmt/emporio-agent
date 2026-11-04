"""FastAPI app: session-based chat API plus a static chat page.

Run locally with: python -m emporio.web
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from emporio.agent.agent import Agent
from emporio.agent.providers import ProviderError
from emporio.web.rate_limit import SlidingWindowLimiter
from emporio.web.sessions import SessionStore
from emporio.web.transcripts import TranscriptStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).with_name("static")
MAX_MESSAGE_CHARS = 1000
MAX_MESSAGES_PER_SESSION = 30
REQUESTS_PER_MINUTE_PER_CLIENT = 20


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatResponse(BaseModel):
    reply: str
    tool_trace: list[dict]
    messages_left: int


def create_app(agent: Agent, transcripts: TranscriptStore, info: dict | None = None,
               sessions: SessionStore | None = None, limiter: SlidingWindowLimiter | None = None) -> FastAPI:
    app = FastAPI(title="Empório da Música — customer service agent", docs_url="/api/docs", redoc_url=None)
    sessions = sessions or SessionStore()
    limiter = limiter or SlidingWindowLimiter(REQUESTS_PER_MINUTE_PER_CLIENT, 60)
    info = info or {}

    def check_rate_limit(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(status_code=429, detail="Muitas mensagens em pouco tempo. Aguarde um minuto.")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", **info}

    @app.post("/api/sessions", status_code=201)
    def create_session(request: Request) -> dict:
        check_rate_limit(request)
        return {"session_id": sessions.create().id, "max_messages": MAX_MESSAGES_PER_SESSION}

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(body: ChatRequest, request: Request) -> ChatResponse:
        check_rate_limit(request)
        session = sessions.get(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Sessão expirada. Recarregue a página para começar de novo.")
        text = body.message.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Mensagem vazia.")

        with session.lock:
            if session.message_count >= MAX_MESSAGES_PER_SESSION:
                raise HTTPException(status_code=429, detail="Limite de mensagens desta conversa atingido.")
            try:
                reply = agent.run(session.history, text)
            except ProviderError:
                logger.exception("Provider failure")
                raise HTTPException(status_code=503, detail="O assistente está indisponível agora. Tente de novo em instantes.")
            session.message_count += 1
            messages_left = MAX_MESSAGES_PER_SESSION - session.message_count

        transcripts.append(session.id, "customer", text)
        transcripts.append(session.id, "assistant", reply.text)
        return ChatResponse(reply=reply.text, tool_trace=reply.tool_trace, messages_left=messages_left)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
