import sqlite3
from datetime import date

import pytest

from emporio.tools.orders import get_order_status

TODAY = date(2026, 11, 2)


def test_order_found_with_matching_email(conn):
    result = get_order_status(conn, 1, " Pedro.Oliveira@jmail.com ", TODAY)
    assert result["found"] is True
    assert result["status"] == "delivered"
    assert result["customer_first_name"] == "Pedro"
    assert "email" not in result and "phone_digits" not in result


@pytest.mark.parametrize("phone", ["(67) 98432-1098", "67984321098", "98432-1098"])
def test_order_found_with_matching_phone_formats(conn, phone):
    assert get_order_status(conn, 1, phone, TODAY)["found"] is True


def test_wrong_contact_and_missing_order_look_the_same(conn):
    wrong_contact = get_order_status(conn, 1, "lucas.mendes@jmail.com", TODAY)
    missing_order = get_order_status(conn, 999, "pedro.oliveira@jmail.com", TODAY)
    assert wrong_contact == missing_order
    assert wrong_contact["found"] is False


def test_too_short_phone_is_rejected(conn):
    assert get_order_status(conn, 1, "1098", TODAY)["found"] is False


def test_return_window_expired(conn):
    result = get_order_status(conn, 7, "leticia.rocha@jmail.com", TODAY)
    windows = result["return_windows"]
    assert windows["regret_return_7_days"] == {"deadline": "2026-02-24", "within_deadline": False}


def test_return_window_open_on_a_simulated_date(conn):
    result = get_order_status(conn, 7, "leticia.rocha@jmail.com", date(2026, 2, 20))
    assert result["return_windows"]["regret_return_7_days"]["within_deadline"] is True


def test_cancelled_order_shows_reason(conn):
    result = get_order_status(conn, 18, "gustavo.nunes@inlook.com", TODAY)
    assert result["status"] == "cancelled"
    assert "fora de estoque" in result["notes"]


def test_tools_connection_is_read_only(conn):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("UPDATE products SET price_brl = 1")
