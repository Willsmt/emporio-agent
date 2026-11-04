from emporio.evaluation.checks import Checks, evaluate
from emporio.evaluation.scenarios import CONVERSATIONS, SCENARIOS


def test_all_checks_pass():
    checks = Checks(tools_called=("get_product",), reply_matches=(r"indisponivel",), reply_excludes=(r"paris",))
    result = evaluate(checks, ["search_products", "get_product"], "Esse modelo está INDISPONÍVEL.")
    assert result.passed and result.failures == []


def test_each_kind_of_failure_is_reported():
    checks = Checks(tools_called=("get_policy",), tools_not_called=("get_order_status",),
                    reply_matches=(r"3341-4444",), reply_excludes=(r"3321-4500",))
    result = evaluate(checks, ["get_order_status"], "Ligue para (67) 3321-4500")
    assert not result.passed
    assert len(result.failures) == 4


def test_scenarios_and_conversations_are_well_formed():
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    assert all(s.turns and s.description for s in SCENARIOS)
    assert 3 <= len(CONVERSATIONS) <= 5  # challenge deliverable


def test_runner_writes_report_and_transcript_offline(monkeypatch, tmp_path, db_path):
    from datetime import date

    from emporio.agent.agent import Agent
    from emporio.agent.tool_registry import build_tools
    from emporio.agent.types import ModelTurn
    from emporio.evaluation import runner
    from emporio.evaluation.scenarios import Conversation, Scenario
    from emporio.settings import Settings
    from emporio.tools.db import connect_readonly
    from fakes import ScriptedProvider, tool_call

    def fake_agent(settings):
        provider = ScriptedProvider([
            ModelTurn(text="", tool_calls=[tool_call("get_product", product_id=95)]),
            ModelTurn(text="Custa R$ 2.199,00 ou R$ 2.089,05 no PIX.", tool_calls=[]),
        ])
        tools = build_tools(connect_readonly(db_path), today=lambda: date(2026, 11, 2))
        return Agent(provider, tools, system_prompt=lambda: "p")

    monkeypatch.setattr(runner, "build_agent", fake_agent)
    monkeypatch.setattr(runner, "REPORT_PATH", tmp_path / "report.md")
    monkeypatch.setattr(runner, "CONVERSATIONS_DIR", tmp_path)
    settings = Settings(provider="gemini", model="fake", api_key="k")

    scenario = Scenario("price", "price", ("Quanto custa?",),
                        Checks(tools_called=("get_product",), reply_matches=(r"2\.089,05",)))
    result = runner.run_scenario(settings, scenario)
    assert result["passed"]
    report = runner.write_report(settings, [result]).read_text(encoding="utf-8")
    assert "1/1 scenarios passed" in report

    transcript = runner.write_conversation(settings, Conversation("t", "T", "why", ("Quanto custa?",))).read_text(encoding="utf-8")
    assert "**Mel:** Custa R$ 2.199,00" in transcript
    assert "get_product" in transcript
