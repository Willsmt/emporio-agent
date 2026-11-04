"""Read-only data for the store front page: contact, hours, open status, categories and active promotions.

Everything comes from the same sources the agent uses (database, curated policy, OPENING_HOURS), so the page and
the assistant can never disagree.
"""
import re
import sqlite3
from datetime import datetime

from emporio.agent.prompts import OPENING_HOURS, format_opening_pt, next_opening
from emporio.tools.catalog import PRODUCT_QUERY, availability, list_categories, summarize

DAY_NAMES = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MAX_PROMOTIONS = 6
CONTACT_FIELDS = {"address": "Endereço", "phone": "Telefone / WhatsApp"}


def _policy_field(conn: sqlite3.Connection, label: str) -> str | None:
    row = conn.execute("SELECT content FROM policy_sections WHERE slug = 'about_store'").fetchone()
    match = re.search(rf"^\| {re.escape(label)} \| (.+?) \|$", row[0] if row else "", flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _format_hours(hours: tuple[int, int] | None) -> str:
    return f"{hours[0]:02d}:00 às {hours[1]:02d}:00" if hours else "Fechado"


def opening_hours() -> list[dict]:
    """Group consecutive days with the same hours: Segunda a Sexta, Sábado, Domingo."""
    groups: list[list[int]] = []
    for day in range(7):
        if groups and OPENING_HOURS.get(groups[-1][-1]) == OPENING_HOURS.get(day):
            groups[-1].append(day)
        else:
            groups.append([day])
    return [
        {"days": DAY_NAMES[g[0]] if len(g) == 1 else f"{DAY_NAMES[g[0]]} a {DAY_NAMES[g[-1]]}",
         "time": _format_hours(OPENING_HOURS.get(g[0]))}
        for g in groups
    ]


def open_status(now: datetime) -> dict:
    hours = OPENING_HOURS.get(now.weekday())
    if hours and hours[0] <= now.hour < hours[1]:
        return {"open_now": True, "label": f"Aberto agora · até {hours[1]:02d}:00"}
    return {"open_now": False, "label": f"Fechado · abre {format_opening_pt(now, next_opening(now))}"}


def _available_products(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(PRODUCT_QUERY + " ORDER BY p.price_brl").fetchall()
    return [summarize(r) for r in rows if availability(r["status"], r["stock_quantity"]) == "available"]


def build_storefront(conn: sqlite3.Connection, now: datetime) -> dict:
    products = _available_products(conn)
    counts = {name: sum(p["category"] == name for p in products) for name in list_categories(conn)}
    promotions = sorted((p for p in products if p["promotion"]), key=lambda p: (-p["promotion"]["percent"], p["price"]))
    return {
        "store": {
            "name": "Empório da Música",
            **{key: _policy_field(conn, label) for key, label in CONTACT_FIELDS.items()},
            "hours": opening_hours(),
            "hours_note": "Feriados: fechado. Em datas especiais o horário pode ser estendido.",
            "status": open_status(now),
        },
        # Categories with nothing available are left out: the page must not suggest stock the system doesn't have.
        "categories": [{"name": name, "available": n} for name, n in counts.items() if n],
        "promotions": [
            {"product_id": p["product_id"], "name": p["name"], "category": p["category"], "label": p["promotion"]["name"],
             "percent": p["promotion"]["percent"], "list_price": p["list_price"], "price": p["price"]}
            for p in promotions[:MAX_PROMOTIONS]
        ],
    }
