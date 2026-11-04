"""The contract every LLM adapter implements (Adapter pattern).

Each provider keeps the conversation history in its own native format, so provider-specific
data (such as Gemini thought signatures or OpenAI reasoning items) survives between steps.
The agent loop only appends whatever the adapter returns.
"""
from typing import Any, Protocol

from emporio.agent.types import ModelTurn, ToolCall, ToolSpec


class ProviderError(Exception):
    pass


class LLMProvider(Protocol):
    name: str

    def generate(self, system_prompt: str, history: list[Any], tools: list[ToolSpec]) -> ModelTurn: ...

    def user_message(self, text: str) -> Any: ...

    def assistant_message(self, text: str) -> Any: ...

    def turn_items(self, turn: ModelTurn) -> list[Any]: ...

    def tool_result_items(self, results: list[tuple[ToolCall, dict]]) -> list[Any]: ...
