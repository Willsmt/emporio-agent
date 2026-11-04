import sqlite3
from pathlib import Path


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the store database in read-only mode: tools can query, never modify."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}. Run: python -m emporio.data.etl")
    # check_same_thread=False: the web server runs requests in a thread pool. Safe because the connection is
    # read-only and Python's sqlite3 is built in serialized mode (sqlite3.threadsafety == 3).
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
