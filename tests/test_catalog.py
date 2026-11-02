import pytest

from emporio.tools.catalog import get_product, search_products


def test_search_ignores_accents_and_case(conn):
    result = search_products(conn, query="TAKAMINE gd20")
    assert [p["product_id"] for p in result["products"]] == [95]


def test_search_by_category_and_max_price_available_only(conn):
    result = search_products(conn, category="violões", max_price=1000, available_only=True)
    ids = {p["product_id"] for p in result["products"]}
    assert 96 not in ids and 113 not in ids  # out of stock / discontinued
    assert all(p["price"] <= 1000 and p["availability"] == "available" for p in result["products"])
    assert result["count"] == 12
    assert len(result["products"]) == 10
    assert "note" in result


def test_max_price_uses_promotional_price(conn):
    # Ohana CK-20 lists at 549.00 with an active 20% promotion -> 439.20
    result = search_products(conn, query="ohana ck-20", max_price=450)
    assert result["products"][0]["price"] == 439.2
    assert result["products"][0]["promotion"]["percent"] == 20


def test_unknown_category_returns_valid_options(conn):
    result = search_products(conn, category="amplificadores")
    assert result["count"] == 0
    assert "Ukuleles" in result["valid_categories"]


@pytest.mark.parametrize(
    "product_id, expected",
    [(95, "available"), (96, "out_of_stock"), (113, "discontinued"), (136, "discontinued"), (130, "coming_soon")],
)
def test_availability_rules(conn, product_id, expected):
    assert get_product(conn, product_id)["availability"] == expected


def test_unavailable_product_suggests_available_alternatives(conn):
    product = get_product(conn, 96)
    assert "payment" not in product
    assert product["alternatives"]
    assert all(alt["availability"] == "available" for alt in product["alternatives"])


def test_available_product_includes_payment_options(conn):
    product = get_product(conn, 95)
    assert product["payment"]["pix_price"] == 2089.05


def test_unknown_product(conn):
    assert "error" in get_product(conn, 9999)
