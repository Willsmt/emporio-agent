"""Order lookup with identity verification (LGPD, policy section 9)."""
import sqlite3
from datetime import date, timedelta

from emporio.text import digits_only

MIN_PHONE_DIGITS = 8
REGRET_DAYS = 7          # policy 4.1, counted from receipt
DEFECT_EXCHANGE_DAYS = 30  # policy 4.2, counted from purchase
LEGAL_WARRANTY_DAYS = 90   # policy 8.1, counted from receipt

NOT_VERIFIED = {
    "found": False,
    "message": "No order matches this order number and contact. Both must belong to the same customer.",
}


def contact_matches(contact: str, email: str, phone_digits: str) -> bool:
    contact = contact.strip().lower()
    if "@" in contact:
        return contact == email
    digits = digits_only(contact)
    return len(digits) >= MIN_PHONE_DIGITS and phone_digits.endswith(digits)


def deadline(start: date, days: int, today: date) -> dict:
    end = start + timedelta(days=days)
    return {"deadline": end.isoformat(), "within_deadline": today <= end}


def return_windows(order_date: date, received_date: date, today: date) -> dict:
    return {
        "received_date_assumption": "estimated_delivery is used as the receipt date (no actual delivery date in the system)",
        "regret_return_7_days": deadline(received_date, REGRET_DAYS, today),
        "defect_exchange_30_days": deadline(order_date, DEFECT_EXCHANGE_DAYS, today),
        "legal_warranty_90_days": deadline(received_date, LEGAL_WARRANTY_DAYS, today),
    }


def get_order_status(conn: sqlite3.Connection, order_id: int, contact: str, today: date) -> dict:
    """Return order details only if the contact (email or phone) belongs to the order's customer.

    The same message is returned for a missing order and a wrong contact, so the tool cannot be
    used to discover which order numbers exist.
    """
    order = conn.execute(
        """SELECT o.*, c.name AS customer_name, c.email, c.phone_digits
           FROM orders o JOIN customers c ON c.customer_id = o.customer_id
           WHERE o.order_id = ?""",
        (order_id,),
    ).fetchone()
    if order is None or not contact_matches(contact, order["email"], order["phone_digits"]):
        return NOT_VERIFIED

    items = conn.execute(
        """SELECT p.name, oi.quantity FROM order_items oi
           JOIN products p ON p.product_id = oi.product_id WHERE oi.order_id = ?""",
        (order_id,),
    ).fetchall()

    result = {
        "found": True,
        "order_id": order["order_id"],
        "customer_first_name": order["customer_name"].split()[0],
        "status": order["status"],
        "order_date": order["order_date"],
        "total_paid": order["total_brl"],
        "payment_method": order["payment_method"],
        "items": [{"name": item["name"], "quantity": item["quantity"]} for item in items],
        "tracking_code": order["tracking_code"],
        "estimated_delivery": order["estimated_delivery"],
        "notes": order["notes"],
        "today": today.isoformat(),
    }
    if order["status"] == "delivered" and order["estimated_delivery"]:
        result["return_windows"] = return_windows(
            date.fromisoformat(order["order_date"]), date.fromisoformat(order["estimated_delivery"]), today
        )
    return result
