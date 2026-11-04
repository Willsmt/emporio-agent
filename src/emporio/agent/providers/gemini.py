"""Gemini adapter (google-genai SDK) with manual function calling."""
from typing import Any

from google import genai
from google.genai import errors, types

from emporio.agent.providers.base import ProviderError
from emporio.agent.types import ModelTurn, ToolCall, ToolSpec


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, client: Any | None = None):
        self.model = model
        self.client = client or genai.Client(api_key=api_key)

    @staticmethod
    def build_tools(tools: list[ToolSpec]) -> list[types.Tool]:
        declarations = [
            types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    @staticmethod
    def parse_response(response: types.GenerateContentResponse) -> ModelTurn:
        if not response.candidates or response.candidates[0].content is None:
            raise ProviderError("Gemini returned no content (possibly blocked by safety filters)")
        content = response.candidates[0].content
        parts = content.parts or []
        text = "".join(p.text for p in parts if p.text and not p.thought)
        calls = [
            ToolCall(id=p.function_call.id or f"call_{i}", name=p.function_call.name, arguments=dict(p.function_call.args or {}))
            for i, p in enumerate(parts)
            if p.function_call
        ]
        return ModelTurn(text=text.strip(), tool_calls=calls, raw=content)

    def generate(self, system_prompt: str, history: list[Any], tools: list[ToolSpec]) -> ModelTurn:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=self.build_tools(tools),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            response = self.client.models.generate_content(model=self.model, contents=history, config=config)
        except errors.APIError as exc:
            raise ProviderError(f"Gemini API error: {exc}") from exc
        return self.parse_response(response)

    def user_message(self, text: str) -> types.Content:
        return types.Content(role="user", parts=[types.Part(text=text)])

    def assistant_message(self, text: str) -> types.Content:
        return types.Content(role="model", parts=[types.Part(text=text)])

    def turn_items(self, turn: ModelTurn) -> list[Any]:
        return [turn.raw]  # unchanged: keeps the thought signatures Gemini 3+ requires

    def tool_result_items(self, results: list[tuple[ToolCall, dict]]) -> list[Any]:
        parts = [types.Part.from_function_response(name=call.name, response=result) for call, result in results]
        return [types.Content(role="user", parts=parts)]
