"""Adapter tests with the real SDK types, without network calls."""
import json
from types import SimpleNamespace

from google.genai import types

from emporio.agent.providers.gemini import GeminiProvider
from emporio.agent.providers.openai_provider import OpenAIProvider
from emporio.agent.types import ToolCall, ToolSpec

TOOL = ToolSpec(
    name="get_product",
    description="Product details",
    parameters={"type": "object", "properties": {"product_id": {"type": "integer"}}, "required": ["product_id"]},
    handler=lambda **_: {},
)


def test_gemini_parses_function_call_and_keeps_raw_content():
    content = types.Content(role="model", parts=[
        types.Part(function_call=types.FunctionCall(name="get_product", args={"product_id": 95}), thought_signature=b"sig"),
    ])
    response = types.GenerateContentResponse(candidates=[types.Candidate(content=content)])
    turn = GeminiProvider.parse_response(response)
    assert turn.tool_calls[0].name == "get_product"
    assert turn.tool_calls[0].arguments == {"product_id": 95}
    assert turn.raw is content  # thought signature preserved by sending it back unchanged


def test_gemini_ignores_thought_parts_in_text():
    content = types.Content(role="model", parts=[types.Part(text="pensando...", thought=True), types.Part(text="Olá!")])
    turn = GeminiProvider.parse_response(types.GenerateContentResponse(candidates=[types.Candidate(content=content)]))
    assert turn.text == "Olá!"
    assert turn.tool_calls == []


def test_gemini_tool_declarations_and_results():
    tools = GeminiProvider.build_tools([TOOL])
    assert tools[0].function_declarations[0].name == "get_product"
    provider = GeminiProvider(api_key="x", model="m", client=object())
    items = provider.tool_result_items([(ToolCall("c1", "get_product", {}), {"price": 10})])
    assert items[0].parts[0].function_response.response == {"price": 10}


def test_openai_parses_function_calls_and_text():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(type="reasoning"),
            SimpleNamespace(type="function_call", call_id="call_9", name="get_product", arguments='{"product_id": 95}'),
        ],
        output_text="",
    )
    turn = OpenAIProvider.parse_response(response)
    assert turn.tool_calls == [ToolCall("call_9", "get_product", {"product_id": 95})]
    assert len(turn.raw) == 2  # reasoning item is sent back too


def test_openai_tool_results_are_json_strings():
    provider = OpenAIProvider(api_key="x", model="m", client=object())
    items = provider.tool_result_items([(ToolCall("call_9", "get_product", {}), {"nome": "Violão"})])
    assert items[0]["call_id"] == "call_9"
    assert json.loads(items[0]["output"]) == {"nome": "Violão"}
