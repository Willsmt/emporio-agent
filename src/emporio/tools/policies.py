import sqlite3

from emporio.data.policies import SECTION_SLUGS


def get_policy(conn: sqlite3.Connection, section: str) -> dict:
    row = conn.execute(
        "SELECT slug, title, content FROM policy_sections WHERE slug = ?", (section,)
    ).fetchone()
    if row is None:
        return {"error": f"Unknown section '{section}'", "valid_sections": list(SECTION_SLUGS.values())}
    return {"section": row["slug"], "title": row["title"], "content": row["content"]}
