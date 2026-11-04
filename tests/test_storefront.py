from datetime import datetime

from emporio.settings import STORE_TIMEZONE
from emporio.web.storefront import build_storefront

WEDNESDAY_10AM = datetime(2026, 11, 4, 10, 0, tzinfo=STORE_TIMEZONE)
SUNDAY_10AM = datetime(2026, 11, 8, 10, 0, tzinfo=STORE_TIMEZONE)


def test_contact_comes_from_the_curated_policy(conn):
    store = build_storefront(conn, WEDNESDAY_10AM)["store"]
    assert store["address"] == "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333"
    assert store["phone"] == "(67) 3341-4444"  # the official number (clarification A1), not the WhatsApp one


def test_hours_are_grouped_from_the_table_the_agent_uses(conn):
    assert build_storefront(conn, WEDNESDAY_10AM)["store"]["hours"] == [
        {"days": "Segunda a Sexta", "time": "09:00 às 18:00"},
        {"days": "Sábado", "time": "09:00 às 13:00"},
        {"days": "Domingo", "time": "Fechado"},
    ]


def test_open_status_uses_store_time(conn):
    assert build_storefront(conn, WEDNESDAY_10AM)["store"]["status"] == {"open_now": True, "label": "Aberto agora · até 18:00"}
    closed = build_storefront(conn, SUNDAY_10AM)["store"]["status"]
    assert closed == {"open_now": False, "label": "Fechado · abre amanhã, segunda-feira (09/11), às 09:00"}


def test_categories_list_only_what_is_available(conn):
    categories = {c["name"]: c["available"] for c in build_storefront(conn, WEDNESDAY_10AM)["categories"]}
    assert categories["Violões"] == 33
    assert "Cordas Orquestrais" not in categories  # no products: the page must not suggest stock (clarification A3)


def test_promotions_are_available_discounted_and_sorted(conn):
    promotions = build_storefront(conn, WEDNESDAY_10AM)["promotions"]
    assert [p["product_id"] for p in promotions] == [121, 90, 127, 94]
    assert all(p["price"] < p["list_price"] for p in promotions)
