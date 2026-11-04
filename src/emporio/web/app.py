"""FastAPI app: session-based chat API plus a static chat page.

Run locally with: python -m emporio.web
"""
import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
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
MAX_MESSAGES_PER_DAY = 500  # global spend cap across all clients

# Strict CSP for the store and chat pages (ADR-018): every script and style is a same-origin file, so no
# 'unsafe-inline'. Only "/", "/chat" and "/static/*" get it; Swagger UI at /api/docs (DEMO_MODE) loads a CDN
# script and inline code, so a global policy would break it.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'; object-src 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatResponse(BaseModel):
    reply: str
    tool_trace: list[dict] | None = None  # only in demo mode
    messages_left: int


async def add_security_headers(request: Request, call_next: Callable) -> Response:
    """HTTP middleware: security headers on the web pages and their static files only."""
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/chat") or path.startswith("/static/"):
        response.headers.update(SECURITY_HEADERS)
    return response


def create_app(agent: Agent, transcripts: TranscriptStore, info: dict | None = None,
               sessions: SessionStore | None = None, limiter: SlidingWindowLimiter | None = None,
               demo_mode: bool = False, daily_limiter: SlidingWindowLimiter | None = None,
               storefront: Callable[[], dict] | None = None) -> FastAPI:
    """In demo mode the API also exposes the model, the tool trace and the Swagger docs, for technical review.

    Off by default: in production those are internal details (stack fingerprinting, tool map for prompt injection).
    """
    app = FastAPI(title="Empório da Música — customer service agent",
                  docs_url="/api/docs" if demo_mode else None, redoc_url=None, openapi_url="/api/openapi.json" if demo_mode else None)
    # "is None", not "or": an empty store or limiter defines __len__ == 0 and would be falsy
    sessions = SessionStore() if sessions is None else sessions
    limiter = SlidingWindowLimiter(REQUESTS_PER_MINUTE_PER_CLIENT, 60) if limiter is None else limiter
    daily_limiter = SlidingWindowLimiter(MAX_MESSAGES_PER_DAY, 24 * 60 * 60) if daily_limiter is None else daily_limiter
    info = info or {}
    if demo_mode:
        logger.warning("DEMO_MODE is on: model, tool trace and API docs are exposed. Do not use in production.")

    def check_rate_limit(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(status_code=429, detail="Muitas mensagens em pouco tempo. Aguarde um minuto.")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "demo_mode": demo_mode, **(info if demo_mode else {})}

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
            if not daily_limiter.allow("global"):
                raise HTTPException(status_code=429, detail="O assistente atingiu o limite diário de atendimentos. Volte amanhã.")
            try:
                reply = agent.run(session.history, text)
            except ProviderError:
                logger.exception("Provider failure")
                raise HTTPException(status_code=503, detail="O assistente está indisponível agora. Tente de novo em instantes.")
            session.message_count += 1
            messages_left = MAX_MESSAGES_PER_SESSION - session.message_count

        transcripts.append(session.id, "customer", text)
        transcripts.append(session.id, "assistant", reply.text)
        return ChatResponse(reply=reply.text, tool_trace=reply.tool_trace if demo_mode else None,
                            messages_left=messages_left)

    @app.get("/api/storefront")
    def storefront_data(request: Request) -> dict:
        """Read-only store front data (contact, hours, categories, promotions); never touches the agent."""
        check_rate_limit(request)
        if storefront is None:
            raise HTTPException(status_code=404, detail="Vitrine indisponível.")
        return storefront()

    @app.get("/", include_in_schema=False)
    def store_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "store.html")

    @app.get("/chat", include_in_schema=False)
    def chat_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.middleware("http")(add_security_headers)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
