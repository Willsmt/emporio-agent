"""Product search and details, applying availability rules (policy 7.3)."""
import sqlite3
from dataclasses import dataclass

from emporio.text import normalize
from emporio.tools.pricing import apply_discount, payment_summary, to_money

MAX_RESULTS = 15
MAX_ALTERNATIVES = 3

# Words that do not identify a product: connectors and instrument types (the category filter covers those).
# Without this, "violão" (violao) never matches the category "Violões" (violoes) in an all-terms search.
IGNORED_TERMS = {
    "de", "da", "do", "com", "para", "o", "a", "e", "um", "uma",
    "violao", "violoes", "guitarra", "guitarras", "baixo", "baixos", "ukulele", "ukuleles",
    "teclado", "teclados", "piano", "pianos", "bateria", "baterias", "instrumento", "instrumentos",
}

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


@dataclass(frozen=True)
class SearchCriteria:
    terms: tuple[str, ...]
    category_key: str | None
    max_price: float | None
    available_only: bool

    @classmethod
    def build(cls, query: str | None, category: str | None, max_price: float | None,
              available_only: bool) -> "SearchCriteria":
        terms = tuple(t for t in normalize(query or "").split() if t not in IGNORED_TERMS)
        # Some models send 0 meaning "no limit" for optional numeric filters.
        budget = max_price if max_price is not None and max_price > 0 else None
        return cls(terms, normalize(category) if category else None, budget, available_only)


def _matches_text(row: sqlite3.Row, criteria: SearchCriteria) -> bool:
    haystack = f"{row['name_search']} {normalize(row['category'])}"
    return all(term in haystack for term in criteria.terms)


def _in_category(row: sqlite3.Row, criteria: SearchCriteria) -> bool:
    return criteria.category_key is None or normalize(row["category"]) == criteria.category_key


def _within_budget(product: dict, criteria: SearchCriteria) -> bool:
    # Compared with the final (promotional) price, which is computed in Python: this filter cannot move to SQL.
    return criteria.max_price is None or product["price"] <= criteria.max_price


def _collect(rows: list[sqlite3.Row], criteria: SearchCriteria) -> tuple[list[dict], list[dict]]:
    """Return (matching products, matches hidden only by the availability filter)."""
    results, hidden = [], []
    for row in rows:
        if not (_matches_text(row, criteria) and _in_category(row, criteria)):
            continue
        product = summarize(row)
        if not _within_budget(product, criteria):
            continue
        if criteria.available_only and product["availability"] != "available":
            if criteria.terms:
                hidden.append({k: product[k] for k in ("product_id", "name", "availability")})
            continue
        results.append(product)
    results.sort(key=lambda p: p["availability"] != "available")  # stable: available first, then by price
    return results, hidden


def _add_truncation_note(response: dict, results: list[dict]) -> None:
    if len(results) > MAX_RESULTS:
        response["note"] = (
            f"Showing {MAX_RESULTS} of {len(results)} matches (available first, then by price). "
            "Tell the customer more options exist and offer to narrow the search."
        )


def _add_unavailable_matches(response: dict, results: list[dict], hidden: list[dict]) -> None:
    if hidden and not results:  # only when the customer's product is not among the available ones
        response["unavailable_matches"] = hidden
        response["unavailable_note"] = (
            "These products match the query but cannot be bought now. Tell the customer their status and "
            "call get_product for similar available alternatives (policy 7.3)."
        )


def _add_empty_hint(response: dict, results: list[dict], hidden: list[dict], applied: dict) -> None:
    if not results and not hidden:
        filters = {k: v for k, v in applied.items() if v}
        response["hint"] = f"No products matched {filters}. Retry with fewer words in the query or without filters."


def _add_category_error(response: dict, conn: sqlite3.Connection, criteria: SearchCriteria) -> None:
    if criteria.category_key is None:
        return
    categories = list_categories(conn)
    if not any(normalize(c) == criteria.category_key for c in categories):
        response["error"] = "Unknown category"
        response["valid_categories"] = categories


def search_products(
    conn: sqlite3.Connection,
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    available_only: bool = False,
) -> dict:
    criteria = SearchCriteria.build(query, category, max_price, available_only)
    rows = conn.execute(PRODUCT_QUERY + " ORDER BY p.price_brl").fetchall()
    results, hidden = _collect(rows, criteria)

    response = {"count": len(results), "products": results[:MAX_RESULTS]}
    _add_truncation_note(response, results)
    _add_unavailable_matches(response, results, hidden)
    _add_empty_hint(response, results, hidden, {"query": query, "category": category, "max_price": criteria.max_price})
    _add_category_error(response, conn, criteria)
    return response


def find_alternatives(conn: sqlite3.Connection, row: sqlite3.Row) -> list[dict]:
    # Bandit B608 false positive: only constant SQL fragments are concatenated; values are bound parameters.
    candidates = conn.execute(
        PRODUCT_QUERY + " WHERE p.category_id = (SELECT category_id FROM products WHERE product_id = ?)"  # nosec B608
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
