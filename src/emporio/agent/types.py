"""Provider-neutral types exchanged between the agent loop and the LLM adapters."""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelTurn:
    """One model response: final text and/or tool calls, plus the provider-native payload.

    `raw` must be sent back to the provider unchanged (e.g. Gemini thought signatures).
    """
    text: str
    tool_calls: list[ToolCall]
    raw: Any = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict]


@dataclass
class AgentReply:
    text: str
    tool_trace: list[dict] = field(default_factory=list)
