from emporio.tools.policies import get_policy


def test_get_policy_returns_full_section(conn):
    result = get_policy(conn, "returns_and_exchanges")
    assert result["title"] == "Política de Trocas e Devoluções"
    assert "7 (sete) dias corridos" in result["content"]


def test_unknown_section_lists_valid_options(conn):
    result = get_policy(conn, "refunds")
    assert "error" in result
    assert "payment" in result["valid_sections"]
