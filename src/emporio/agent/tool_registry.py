"""Binds the deterministic tools to a database connection and describes them to the LLM."""
import sqlite3
from datetime import date
from typing import Callable

from emporio.agent.types import ToolSpec
from emporio.data.policies import SECTION_SLUGS
from emporio.tools.catalog import get_product, list_categories, search_products
from emporio.tools.orders import get_order_status
from emporio.tools.policies import get_policy

POLICY_SECTIONS_HELP = (
    "about_store (company data, address, phone, e-mail, catalog scope), opening_hours, "
    "payment (methods, PIX discount, installments), returns_and_exchanges (regret, defects, preference), "
    "shipping (delivery fees, carriers, tracking), promotions (rules, campaigns), "
    "customer_service (tone, special situations, complaints), warranty, privacy (LGPD), final_provisions"
)


def build_tools(conn: sqlite3.Connection, today: Callable[[], date]) -> list[ToolSpec]:
    categories = list_categories(conn)
    return [
        ToolSpec(
            name="search_products",
            description=(
                "Search the store catalog. Use for questions about which instruments exist, prices, "
                "availability or options within a budget. Returns final prices (with active promotions) "
                "and availability. All filters are optional."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Brand, model or words from the product name, e.g. 'takamine gd20'."},
                    "category": {"type": "string", "enum": categories, "description": "Product category."},
                    "max_price": {"type": "number", "description": "Maximum final price in BRL."},
                    "available_only": {"type": "boolean", "description": "Only products available for purchase now."},
                },
            },
            handler=lambda **args: search_products(conn, **args),
        ),
        ToolSpec(
            name="get_product",
            description=(
                "Full details of one product by id: description, specs, availability, prices per payment "
                "method (PIX, debit, boleto, credit card installments) or, if unavailable, similar alternatives."
            ),
            parameters={
                "type": "object",
                "properties": {"product_id": {"type": "integer", "description": "Id returned by search_products."}},
                "required": ["product_id"],
            },
            handler=lambda **args: get_product(conn, **args),
        ),
        ToolSpec(
            name="get_order_status",
            description=(
                "Look up an order. Requires BOTH the order number and the e-mail or phone registered on the "
                "order; the tool verifies they belong to the same customer (LGPD). Ask the customer for both "
                "before calling and never guess them. Returns status, items, tracking and, for delivered "
                "orders, the deadlines for returns, exchanges and warranty."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Order number."},
                    "contact": {"type": "string", "description": "E-mail or phone given by the customer."},
                },
                "required": ["order_id", "contact"],
            },
            handler=lambda **args: get_order_status(conn, today=today(), **args),
        ),
        ToolSpec(
            name="get_policy",
            description=(
                "Read one section of the store's official policy manual. Use before answering any question "
                f"about store rules or information. Sections: {POLICY_SECTIONS_HELP}."
            ),
            parameters={
                "type": "object",
                "properties": {"section": {"type": "string", "enum": list(SECTION_SLUGS.values())}},
                "required": ["section"],
            },
            handler=lambda **args: get_policy(conn, **args),
        ),
    ]
