"""OpenAI adapter (Responses API) with manual function calling.

`store=False` keeps conversations out of OpenAI's storage; reasoning items are passed back
encrypted, which is the stateless pattern for reasoning models.
"""
import json
from typing import Any

import openai
from openai import OpenAI

from emporio.agent.providers.base import ProviderError
from emporio.agent.types import ModelTurn, ToolCall, ToolSpec


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, client: Any | None = None):
        self.model = model
        self.client = client or OpenAI(api_key=api_key)

    @staticmethod
    def build_tools(tools: list[ToolSpec]) -> list[dict]:
        return [
            {"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ]

    @staticmethod
    def parse_response(response: Any) -> ModelTurn:
        calls = []
        for item in response.output:
            if item.type != "function_call":
                continue
            try:
                arguments = json.loads(item.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_invalid_json": item.arguments}
            calls.append(ToolCall(id=item.call_id, name=item.name, arguments=arguments))
        return ModelTurn(text=(response.output_text or "").strip(), tool_calls=calls, raw=list(response.output))

    def generate(self, system_prompt: str, history: list[Any], tools: list[ToolSpec]) -> ModelTurn:
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=history,
                tools=self.build_tools(tools),
                store=False,
                include=["reasoning.encrypted_content"],
            )
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI API error: {exc}") from exc
        return self.parse_response(response)

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def assistant_message(self, text: str) -> dict:
        return {"role": "assistant", "content": text}

    def turn_items(self, turn: ModelTurn) -> list[Any]:
        return list(turn.raw)

    def tool_result_items(self, results: list[tuple[ToolCall, dict]]) -> list[Any]:
        return [
            {"type": "function_call_output", "call_id": call.id, "output": json.dumps(result, ensure_ascii=False)}
            for call, result in results
        ]
