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
    assert len(result["products"]) == 12
    assert "note" not in result


def test_available_products_are_ranked_before_unavailable_ones(conn):
    products = search_products(conn, category="Violões")["products"]
    flags = [p["availability"] == "available" for p in products]
    assert flags == sorted(flags, reverse=True)


def test_note_when_results_are_truncated(conn):
    result = search_products(conn)
    assert result["count"] == 65
    assert len(result["products"]) == 15
    assert "65" in result["note"]


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


def test_zero_max_price_means_no_limit(conn):
    # Some models fill every optional parameter and send max_price=0 for "no limit"
    result = search_products(conn, query="takamine gd20", category="Violões", max_price=0, available_only=False)
    assert [p["product_id"] for p in result["products"]] == [95]


def test_empty_result_explains_the_filters(conn):
    result = search_products(conn, query="stradivarius", max_price=500)
    assert result["count"] == 0
    assert "stradivarius" in result["hint"] and "500" in result["hint"]


def test_available_only_reports_hidden_exact_matches(conn):
    # Customer asks for an out-of-stock product; the model filtered by available_only=True
    result = search_products(conn, query="giannini gf-3d", available_only=True)
    assert result["count"] == 0
    assert result["unavailable_matches"] == [
        {"product_id": 96, "name": "Giannini GF-3D Dreadnought Sunburst", "availability": "out_of_stock"}
    ]
    assert "hint" not in result


def test_category_browsing_does_not_list_unavailable_products(conn):
    assert "unavailable_matches" not in search_products(conn, category="Violões", available_only=True)


def test_instrument_type_words_do_not_break_the_search(conn):
    # "violão" (violao) is not a substring of the category "violoes": type words are ignored, the category filter covers them
    result = search_products(conn, query="Shelby SN-7C violão 7 cordas", category="Violões")
    assert [p["product_id"] for p in result["products"]] == [113]


def test_generic_query_with_available_results_does_not_list_unavailable_products(conn):
    result = search_products(conn, query="violões", category="Violões", max_price=1000, available_only=True)
    assert result["count"] == 12
    assert "unavailable_matches" not in result


def test_search_results_carry_string_type_from_specs(conn):
    result = search_products(conn, category="Violões", max_price=1000, available_only=True)
    strings = {p["product_id"]: p.get("strings") for p in result["products"]}
    assert strings[91] == "steel"  # "Tagima Woodstock Dreadnought Natural": the name does not say it
    assert strings[83] == "nylon"
    assert set(strings.values()) <= {"nylon", "steel"}
