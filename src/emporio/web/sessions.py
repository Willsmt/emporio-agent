"""In-memory conversation sessions with expiry and per-session limits.

Native provider histories (e.g. Gemini thought signatures) are not meant for stable serialization, so they
live in memory only: a server restart starts conversations over. Text transcripts are persisted separately.
"""
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

SESSION_TTL_SECONDS = 30 * 60
MAX_SESSIONS = 500


@dataclass
class Session:
    id: str
    last_used: float
    history: list[Any] = field(default_factory=list)
    message_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)  # one agent turn at a time per session


class SessionStore:
    def __init__(self, ttl_seconds: float = SESSION_TTL_SECONDS, max_sessions: int = MAX_SESSIONS,
                 clock: Callable[[], float] = time.monotonic):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._clock = clock

    def create(self) -> Session:
        with self._lock:
            self._evict_expired()
            if len(self._sessions) >= self._max:
                oldest = min(self._sessions.values(), key=lambda s: s.last_used)
                del self._sessions[oldest.id]
            session = Session(id=secrets.token_urlsafe(16), last_used=self._clock())
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            self._evict_expired()
            session = self._sessions.get(session_id)
            if session:
                session.last_used = self._clock()
            return session

    def __len__(self) -> int:
        return len(self._sessions)

    def _evict_expired(self) -> None:
        now = self._clock()
        for session_id in [s.id for s in self._sessions.values() if now - s.last_used > self._ttl]:
            del self._sessions[session_id]
