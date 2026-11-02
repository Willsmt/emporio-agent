"""Pure pricing rules from the store policy manual (sections 3 and 6). No I/O."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
PIX_DISCOUNT_PERCENT = Decimal("5")
MAX_INSTALLMENTS = 12
INSTALLMENT_MINIMUMS = [  # (max installments in tier, minimum installment value) — policy 3.1 / A4
    (3, Decimal("50")),
    (6, Decimal("80")),
    (12, Decimal("100")),
]


def to_money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(price: Decimal, percent) -> Decimal:
    return to_money(price * (1 - Decimal(str(percent)) / 100))


def minimum_installment(installments: int) -> Decimal:
    for tier_limit, minimum in INSTALLMENT_MINIMUMS:
        if installments <= tier_limit:
            return minimum
    raise ValueError(f"Installments above {MAX_INSTALLMENTS} are not offered")


def installment_options(total: Decimal) -> list[dict]:
    """Interest-free credit card options allowed for this total. 1x is always allowed."""
    options = []
    for n in range(1, MAX_INSTALLMENTS + 1):
        value = to_money(total / n)
        if n == 1 or value >= minimum_installment(n):
            options.append({"installments": n, "installment_value": float(value)})
    return options


def payment_summary(list_price, promotion_percent=None) -> dict:
    """Final prices per payment method. Promotions and the PIX discount never stack (policy 6.2)."""
    list_price = to_money(list_price)
    if promotion_percent:
        price = apply_discount(list_price, promotion_percent)
        pix_price = price
        pix_note = "PIX discount does not apply to promotional prices"
    else:
        price = list_price
        pix_price = apply_discount(list_price, PIX_DISCOUNT_PERCENT)
        pix_note = "5% PIX discount applied over the list price"
    return {
        "list_price": float(list_price),
        "promotion_percent": float(promotion_percent) if promotion_percent else None,
        "price": float(price),
        "pix_price": float(pix_price),
        "pix_note": pix_note,
        "debit_price": float(price),
        "boleto_price": float(price),
        "credit_card_options": installment_options(price),
    }
