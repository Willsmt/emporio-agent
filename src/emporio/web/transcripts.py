"""Text-only transcript log in a separate, writable SQLite database (the store database stays read-only).

Contact data typed by customers is masked before storage (LGPD data minimization).
"""
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# Brazilian phones in any common format: +55, area code with or without parentheses, spaces, dots or dashes
PHONE = re.compile(r"(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('customer', 'assistant')),
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_session ON messages(session_id, id);
"""


def mask_contacts(text: str) -> str:
    return PHONE.sub("***", EMAIL.sub("***", text))


class TranscriptStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def append(self, session_id: str, role: str, content: str) -> None:
        """Best effort: a logging failure must never break the conversation."""
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, role, mask_contacts(content), datetime.now(timezone.utc).isoformat()),
                )
        except sqlite3.Error:
            logger.exception("Could not store transcript message")

    def messages(self, session_id: str) -> list[tuple[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [(role, content) for role, content in rows]
