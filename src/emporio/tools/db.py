import sqlite3
from pathlib import Path


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the store database in read-only mode: tools can query, never modify."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}. Run: python -m emporio.data.etl")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
