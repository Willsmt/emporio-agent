from datetime import date

import pytest

from emporio.agent.agent import FALLBACK_REPLY, Agent
from emporio.agent.providers.base import ProviderError
from emporio.agent.tool_registry import build_tools
from emporio.agent.types import ModelTurn, ToolSpec
from fakes import ScriptedProvider, tool_call

TODAY = date(2026, 11, 2)


def make_agent(conn, turns, max_steps=6, extra_tools=()):
    provider = ScriptedProvider(turns)
    tools = build_tools(conn, today=lambda: TODAY) + list(extra_tools)
    return Agent(provider, tools, system_prompt=lambda: "test prompt", max_steps=max_steps), provider


def tool_results(history):
    return [item for item in history if item["role"] == "tool"]


def test_answers_without_tools(conn):
    agent, _ = make_agent(conn, [ModelTurn(text="Olá! Como posso ajudar?", tool_calls=[])])
    history = []
    reply = agent.run(history, "oi")
    assert reply.text == "Olá! Como posso ajudar?"
    assert reply.tool_trace == []
    assert [item["role"] for item in history] == ["user", "assistant"]


def test_executes_tool_and_sends_result_back_to_the_model(conn):
    agent, provider = make_agent(conn, [
        ModelTurn(text="", tool_calls=[tool_call("get_product", product_id=95)]),
        ModelTurn(text="O Takamine GD20 custa R$ 2.199,00.", tool_calls=[]),
    ])
    history = []
    reply = agent.run(history, "Quanto custa o Takamine GD20?")

    assert reply.text.startswith("O Takamine")
    assert reply.tool_trace == [{"tool": "get_product", "arguments": {"product_id": 95}, "ok": True}]
    second_request = provider.requests[1]
    assert tool_results(second_request)[0]["result"]["list_price"] == 2199.0


def test_float_integer_arguments_are_coerced(conn):
    agent, _ = make_agent(conn, [
        ModelTurn(text="", tool_calls=[tool_call("get_product", product_id=95.0)]),
        ModelTurn(text="ok", tool_calls=[]),
    ])
    history = []
    agent.run(history, "preço?")
    assert tool_results(history)[0]["result"]["product_id"] == 95


def test_contact_is_redacted_in_trace(conn):
    agent, _ = make_agent(conn, [
        ModelTurn(text="", tool_calls=[tool_call("get_order_status", order_id=1, contact="pedro.oliveira@jmail.com")]),
        ModelTurn(text="Seu pedido foi entregue.", tool_calls=[]),
    ])
    reply = agent.run([], "pedido 1, pedro.oliveira@jmail.com")
    assert reply.tool_trace[0]["arguments"]["contact"] == "***"


@pytest.mark.parametrize(
    "call, expected_error",
    [
        (tool_call("delete_everything"), "Unknown tool"),
        (tool_call("get_product", product_ids=[1]), "Invalid arguments"),
    ],
)
def test_bad_tool_calls_become_errors_for_the_model(conn, call, expected_error):
    agent, _ = make_agent(conn, [ModelTurn(text="", tool_calls=[call]), ModelTurn(text="ok", tool_calls=[])])
    history = []
    reply = agent.run(history, "x")
    assert expected_error in tool_results(history)[0]["result"]["error"]
    assert reply.tool_trace[0]["ok"] is False


def test_failing_tool_does_not_crash_the_conversation(conn):
    def explode():
        raise RuntimeError("database is gone")

    broken = ToolSpec(name="broken", description="", parameters={"type": "object", "properties": {}}, handler=explode)
    agent, _ = make_agent(conn, [ModelTurn(text="", tool_calls=[tool_call("broken")]), ModelTurn(text="ok", tool_calls=[])], extra_tools=[broken])
    history = []
    agent.run(history, "x")
    assert tool_results(history)[0]["result"] == {"error": "Tool broken failed unexpectedly"}


def test_stops_after_max_steps(conn):
    looping = [ModelTurn(text="", tool_calls=[tool_call("get_policy", section="payment")]) for _ in range(3)]
    agent, _ = make_agent(conn, looping, max_steps=3)
    history = []
    reply = agent.run(history, "x")
    assert reply.text == FALLBACK_REPLY
    assert len(reply.tool_trace) == 3
    assert history[-1] == {"role": "assistant", "text": FALLBACK_REPLY}


class FailingSecondCall(ScriptedProvider):
    def generate(self, system_prompt, history, tools):
        if self.requests:
            raise ProviderError("timeout")
        return super().generate(system_prompt, history, tools)


def test_provider_failure_rolls_back_history(conn):
    provider = FailingSecondCall([ModelTurn(text="", tool_calls=[tool_call("get_product", product_id=95)])])
    agent = Agent(provider, build_tools(conn, today=lambda: TODAY), system_prompt=lambda: "p")
    history = [{"role": "user", "text": "oi"}, {"role": "assistant", "text": "Olá!"}]
    with pytest.raises(ProviderError):
        agent.run(history, "preço do takamine?")
    assert history == [{"role": "user", "text": "oi"}, {"role": "assistant", "text": "Olá!"}]
