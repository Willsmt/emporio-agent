"""Product search and details, applying availability rules (policy 7.3)."""
import sqlite3

from emporio.text import normalize
from emporio.tools.pricing import apply_discount, payment_summary, to_money

MAX_RESULTS = 15
MAX_ALTERNATIVES = 3

PRODUCT_QUERY = """
    SELECT p.product_id, p.name, p.name_search, p.price_brl, p.stock_quantity, p.status,
           p.description, p.specs, c.name AS category,
           pr.discount_percent AS promotion_percent, pr.description AS promotion_name
    FROM products p
    JOIN categories c ON c.category_id = p.category_id
    LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
"""


def availability(status: str, stock: int) -> str:
    if status == "discontinued":
        return "discontinued"
    if status == "coming_soon":
        return "coming_soon"
    return "available" if stock > 0 else "out_of_stock"


def summarize(row: sqlite3.Row) -> dict:
    list_price = to_money(row["price_brl"])
    promo = row["promotion_percent"]
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "category": row["category"],
        "availability": availability(row["status"], row["stock_quantity"]),
        "list_price": float(list_price),
        "promotion": {"name": row["promotion_name"], "percent": promo} if promo else None,
        "price": float(apply_discount(list_price, promo)) if promo else float(list_price),
    }


def list_categories(conn: sqlite3.Connection) -> list[str]:
    return [row["name"] for row in conn.execute("SELECT name FROM categories ORDER BY category_id")]


def search_products(
    conn: sqlite3.Connection,
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    available_only: bool = False,
) -> dict:
    rows = conn.execute(PRODUCT_QUERY + " ORDER BY p.price_brl").fetchall()
    terms = normalize(query).split() if query else []
    category_key = normalize(category) if category else None

    results = []
    for row in rows:
        haystack = f"{row['name_search']} {normalize(row['category'])}"
        if any(term not in haystack for term in terms):
            continue
        if category_key and normalize(row["category"]) != category_key:
            continue
        product = summarize(row)
        if max_price is not None and product["price"] > max_price:
            continue
        if available_only and product["availability"] != "available":
            continue
        results.append(product)

    results.sort(key=lambda p: p["availability"] != "available")  # stable: available first, then by price
    response = {"count": len(results), "products": results[:MAX_RESULTS]}
    if len(results) > MAX_RESULTS:
        response["note"] = (
            f"Showing {MAX_RESULTS} of {len(results)} matches (available first, then by price). "
            "Tell the customer more options exist and offer to narrow the search."
        )
    if category_key and not any(normalize(c) == category_key for c in list_categories(conn)):
        response["error"] = "Unknown category"
        response["valid_categories"] = list_categories(conn)
    return response


def find_alternatives(conn: sqlite3.Connection, row: sqlite3.Row) -> list[dict]:
    candidates = conn.execute(
        PRODUCT_QUERY + " WHERE p.category_id = (SELECT category_id FROM products WHERE product_id = ?)"
        " AND p.product_id != ?",
        (row["product_id"], row["product_id"]),
    ).fetchall()
    available = [summarize(c) for c in candidates if availability(c["status"], c["stock_quantity"]) == "available"]
    available.sort(key=lambda p: abs(p["price"] - row["price_brl"]))
    return available[:MAX_ALTERNATIVES]


def get_product(conn: sqlite3.Connection, product_id: int) -> dict:
    row = conn.execute(PRODUCT_QUERY + " WHERE p.product_id = ?", (product_id,)).fetchone()
    if row is None:
        return {"error": f"Product {product_id} not found"}

    product = summarize(row)
    product["description"] = row["description"]
    product["specs"] = row["specs"]
    if product["availability"] == "available":
        product["stock_quantity"] = row["stock_quantity"]
        product["payment"] = payment_summary(row["price_brl"], row["promotion_percent"])
    else:
        product["alternatives"] = find_alternatives(conn, row)
    return product
