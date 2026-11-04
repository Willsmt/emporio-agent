from datetime import date

from emporio.agent.tool_registry import build_tools


def test_tool_schemas_are_well_formed(conn):
    tools = build_tools(conn, today=lambda: date(2026, 11, 2))
    assert [t.name for t in tools] == ["search_products", "get_product", "get_order_status", "get_policy"]
    for tool in tools:
        assert tool.description
        assert tool.parameters["type"] == "object"
        for required in tool.parameters.get("required", []):
            assert required in tool.parameters["properties"]


def test_category_enum_comes_from_the_database(conn):
    search = build_tools(conn, today=lambda: date(2026, 11, 2))[0]
    assert "Violões" in search.parameters["properties"]["category"]["enum"]


def test_order_tool_uses_injected_date(conn):
    order_tool = build_tools(conn, today=lambda: date(2026, 2, 20))[2]
    result = order_tool.handler(order_id=7, contact="leticia.rocha@jmail.com")
    assert result["today"] == "2026-02-20"
