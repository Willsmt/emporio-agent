"""Load the store's raw CSVs and curated policies, clean them and build the SQLite database.

Run with: python -m emporio.data.etl
"""
import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from emporio.config import DB_PATH, POLICIES_PATH, RAW_DIR
from emporio.data.policies import parse_policies
from emporio.text import digits_only, normalize

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
RAW_FILE_PATTERN = "desafio_tecnico_ai_eng - {table}.csv"
TABLES = ["categories", "products", "customers", "orders", "order_items", "promotions"]


class DataValidationError(Exception):
    pass


def read_raw(raw_dir: Path) -> dict[str, pd.DataFrame]:
    return {table: pd.read_csv(raw_dir / RAW_FILE_PATTERN.format(table=table)) for table in TABLES}


def clean_products(products: pd.DataFrame) -> pd.DataFrame:
    df = products.copy()
    df["name"] = df["name"].str.strip()
    df["name_search"] = df["name"].map(normalize)
    for product_id, specs in zip(df["product_id"], df["specs"]):
        try:
            json.loads(specs)
        except (TypeError, json.JSONDecodeError) as exc:
            raise DataValidationError(f"Invalid specs JSON for product {product_id}") from exc
    return df


def clean_customers(customers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Normalize contacts and drop duplicate customers sharing the same email.

    Among duplicates, keep the record referenced by orders; otherwise the lowest id.
    """
    df = customers.copy()
    df["email"] = df["email"].str.strip().str.lower()
    df["phone_digits"] = df["phone"].map(digits_only)

    customers_with_orders = set(orders["customer_id"])
    df["_has_orders"] = df["customer_id"].isin(customers_with_orders)
    df = df.sort_values(["_has_orders", "customer_id"], ascending=[False, True])

    duplicated = df["email"].duplicated(keep="first")
    for _, row in df[duplicated].iterrows():
        logger.warning("Dropping duplicate customer %s (email %s)", row["customer_id"], row["email"])

    return df[~duplicated].drop(columns="_has_orders").sort_values("customer_id")


def validate(tables: dict[str, pd.DataFrame]) -> None:
    active = tables["promotions"].query("is_active == 1")
    conflicting = active[active["product_id"].duplicated(keep=False)]
    if not conflicting.empty:
        raise DataValidationError(
            f"Products with more than one active promotion: {sorted(set(conflicting['product_id']))}"
        )


def build_database(
    raw_dir: Path = RAW_DIR,
    db_path: Path = DB_PATH,
    policies_path: Path = POLICIES_PATH,
) -> Path:
    raw = read_raw(raw_dir)
    policies = parse_policies(policies_path.read_text(encoding="utf-8"))
    tables = {
        **raw,
        "products": clean_products(raw["products"]),
        "customers": clean_customers(raw["customers"], raw["orders"]),
    }
    validate(tables)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(".tmp")
    tmp_path.unlink(missing_ok=True)

    # sqlite3's own context manager only commits or rolls back; closing() releases the file before replace().
    with closing(sqlite3.connect(tmp_path)) as conn, conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for table in TABLES:
            tables[table].to_sql(table, conn, if_exists="append", index=False)
        conn.executemany(
            "INSERT INTO policy_sections (slug, number, title, content) VALUES (?, ?, ?, ?)",
            [(p.slug, p.number, p.title, p.content) for p in policies],
        )
        broken_references = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken_references:
            raise DataValidationError(f"Broken foreign keys: {broken_references}")
    tmp_path.replace(db_path)

    logger.info("Database built at %s", db_path)
    return db_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_database()
