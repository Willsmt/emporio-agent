import sqlite3

import pytest

from emporio.config import RAW_DIR
from emporio.data.etl import build_database


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    db_path = build_database(RAW_DIR, tmp_path_factory.mktemp("db") / "test.db")
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_all_tables_loaded(db):
    assert count(db, "categories") == 9
    assert count(db, "products") == 65
    assert count(db, "orders") == 20
    assert count(db, "order_items") == 22
    assert count(db, "promotions") == 25


def test_duplicate_customer_removed_keeping_the_one_with_orders(db):
    rows = db.execute(
        "SELECT customer_id FROM customers WHERE email = 'bruno.martins@jmail.com'"
    ).fetchall()
    assert rows == [(11,)]
    assert count(db, "customers") == 49


def test_product_search_name_is_normalized(db):
    row = db.execute(
        "SELECT name_search FROM products WHERE name LIKE '%Barítono%'"
    ).fetchone()
    assert "baritono" in row[0]


def test_customer_phone_digits(db):
    row = db.execute("SELECT phone_digits FROM customers WHERE customer_id = 1").fetchone()
    assert row[0] == "67998123456"


def test_order_total_is_kept_as_historical_value(db):
    total = db.execute("SELECT total_brl FROM orders WHERE order_id = 3").fetchone()[0]
    assert total == 3450


def test_at_most_one_active_promotion_per_product(db):
    rows = db.execute(
        "SELECT product_id FROM promotions WHERE is_active = 1 "
        "GROUP BY product_id HAVING COUNT(*) > 1"
    ).fetchall()
    assert rows == []
