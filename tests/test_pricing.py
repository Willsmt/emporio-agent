from decimal import Decimal

import pytest

from emporio.tools.pricing import installment_options, minimum_installment, payment_summary


@pytest.mark.parametrize(
    "installments, minimum",
    [(1, Decimal("50")), (3, Decimal("50")), (4, Decimal("80")), (6, Decimal("80")), (7, Decimal("100")), (12, Decimal("100"))],
)
def test_installment_minimum_tiers(installments, minimum):
    assert minimum_installment(installments) == minimum


def test_large_purchase_allows_twelve_installments():
    options = installment_options(Decimal("2199.00"))
    assert options[-1] == {"installments": 12, "installment_value": 183.25}


def test_installments_respect_tier_minimums():
    # R$ 429,90: 3x = 143.30 ok; 4x = 107.48 ok (>= 80); 5x = 85.98 ok; 6x = 71.65 < 80 blocked
    allowed = [o["installments"] for o in installment_options(Decimal("429.90"))]
    assert allowed == [1, 2, 3, 4, 5]


def test_cheap_item_only_one_installment():
    assert [o["installments"] for o in installment_options(Decimal("90.00"))] == [1]


def test_pix_discount_on_regular_price():
    summary = payment_summary(2199.0)
    assert summary["price"] == 2199.0
    assert summary["pix_price"] == 2089.05


def test_pix_discount_does_not_stack_with_promotion():
    summary = payment_summary(549.0, promotion_percent=20)
    assert summary["price"] == 439.2
    assert summary["pix_price"] == 439.2
