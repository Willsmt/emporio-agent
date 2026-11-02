import re
import sqlite3

import pytest
from pypdf import PdfReader

from emporio.config import POLICIES_PATH, RAW_DIR
from emporio.data.etl import build_database
from emporio.data.policies import SECTION_SLUGS, PolicyParseError, parse_policies

SOURCE_PDF = RAW_DIR / "políticas_da_loja.pdf"
FACT_PATTERN = re.compile(r"\d[\d.,:/x-]*\d|\d")


@pytest.fixture(scope="module")
def curated_text():
    return POLICIES_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def source_text():
    raw = " ".join(page.extract_text() for page in PdfReader(SOURCE_PDF).pages)
    return " ".join(raw.split())


def without_clarifications(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith(">"))


def facts_missing_from_source(curated: str, source: str) -> set[str]:
    return {fact for fact in FACT_PATTERN.findall(curated) if fact not in source}


def test_all_sections_parsed(curated_text):
    sections = parse_policies(curated_text)
    assert [s.slug for s in sections] == list(SECTION_SLUGS.values())


def test_missing_section_is_rejected(curated_text):
    truncated = curated_text.split("## 10.")[0]
    with pytest.raises(PolicyParseError, match="Missing policy sections"):
        parse_policies(truncated)


def test_curated_manual_does_not_invent_numbers(curated_text, source_text):
    """Every number, price, date or phone in the curated manual must exist in the original PDF."""
    sections = parse_policies(curated_text)
    original_content = "\n".join(without_clarifications(s.content) for s in sections)
    assert facts_missing_from_source(original_content, source_text) == set()


def test_fidelity_check_catches_an_invented_value(source_text):
    tampered = "Frete grátis para pedidos acima de R$ 999,00."
    assert facts_missing_from_source(tampered, source_text) == {"999,00"}


def test_contradictions_are_documented(curated_text):
    payment = next(s for s in parse_policies(curated_text) if s.slug == "payment")
    assert "Esclarecimento A4" in payment.content
    assert "(67) 3341-4444" in curated_text


def test_policies_loaded_into_database(tmp_path):
    db_path = build_database(db_path=tmp_path / "test.db")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT slug FROM policy_sections ORDER BY number").fetchall()
    assert [slug for (slug,) in rows] == list(SECTION_SLUGS.values())
