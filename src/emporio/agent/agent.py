"""The agent loop: model -> tool calls -> tool results -> model, until a final answer."""
import logging
from typing import Any, Callable

from emporio.agent.providers.base import LLMProvider, ProviderError
from emporio.agent.types import AgentReply, ModelTurn, ToolCall, ToolSpec

logger = logging.getLogger(__name__)

MAX_STEPS = 6
SENSITIVE_ARGUMENTS = {"contact"}
FALLBACK_REPLY = (
    "Desculpe, não consegui concluir sua solicitação agora. "
    "Você pode falar com a nossa equipe pelo (67) 3341-4444 ou contato@emporiodamusica.com.br."
)


def redact(arguments: dict) -> dict:
    return {k: ("***" if k in SENSITIVE_ARGUMENTS else v) for k, v in arguments.items()}


def coerce_integers(arguments: dict, schema: dict) -> dict:
    """Some providers send JSON integers as floats (95.0); convert them back per the tool schema."""
    properties = schema.get("properties", {})
    coerced = dict(arguments)
    for key, value in arguments.items():
        if properties.get(key, {}).get("type") == "integer" and isinstance(value, float) and value.is_integer():
            coerced[key] = int(value)
    return coerced


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        tools: list[ToolSpec],
        system_prompt: Callable[[], str],
        max_steps: int = MAX_STEPS,
    ):
        self.provider = provider
        self.tools = {tool.name: tool for tool in tools}
        self.system_prompt = system_prompt
        self.max_steps = max_steps

    def execute(self, call: ToolCall) -> dict:
        tool = self.tools.get(call.name)
        if tool is None:
            return {"error": f"Unknown tool '{call.name}'", "available_tools": sorted(self.tools)}
        try:
            return tool.handler(**coerce_integers(call.arguments, tool.parameters))
        except TypeError as exc:
            return {"error": f"Invalid arguments for {call.name}: {exc}"}
        except Exception:  # a failing tool must not crash the conversation
            logger.exception("Tool %s failed", call.name)
            return {"error": f"Tool {call.name} failed unexpectedly"}

    def run(self, history: list[Any], user_text: str) -> AgentReply:
        """Process one customer message. `history` is the provider-native conversation and is mutated.

        If the provider fails, the history is rolled back so the conversation stays consistent.
        """
        start = len(history)
        try:
            return self._run(history, user_text)
        except ProviderError:
            del history[start:]
            raise

    def _run(self, history: list[Any], user_text: str) -> AgentReply:
        history.append(self.provider.user_message(user_text))
        trace: list[dict] = []
        system_prompt = self.system_prompt()

        for _ in range(self.max_steps):
            turn: ModelTurn = self.provider.generate(system_prompt, history, list(self.tools.values()))
            history.extend(self.provider.turn_items(turn))
            if not turn.tool_calls:
                return AgentReply(text=turn.text or FALLBACK_REPLY, tool_trace=trace)

            results = []
            for call in turn.tool_calls:
                result = self.execute(call)
                logger.info("tool=%s args=%s error=%s", call.name, redact(call.arguments), "error" in result)
                trace.append({"tool": call.name, "arguments": redact(call.arguments), "ok": "error" not in result})
                results.append((call, result))
            history.extend(self.provider.tool_result_items(results))

        logger.warning("Max steps (%s) reached without a final answer", self.max_steps)
        history.append(self.provider.assistant_message(FALLBACK_REPLY))
        return AgentReply(text=FALLBACK_REPLY, tool_trace=trace)
