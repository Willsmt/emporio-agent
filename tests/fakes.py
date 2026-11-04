"""A scripted LLM provider: replays predefined model turns, so the agent loop is tested offline."""
from emporio.agent.types import ModelTurn, ToolCall


def tool_call(name: str, call_id: str = "call_1", **arguments) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


class ScriptedProvider:
    name = "scripted"

    def __init__(self, turns: list[ModelTurn]):
        self.turns = list(turns)
        self.requests: list[list] = []

    def generate(self, system_prompt, history, tools):
        self.requests.append(list(history))
        return self.turns.pop(0)

    def user_message(self, text):
        return {"role": "user", "text": text}

    def assistant_message(self, text):
        return {"role": "assistant", "text": text}

    def turn_items(self, turn):
        return [{"role": "assistant", "text": turn.text, "tool_calls": turn.tool_calls}]

    def tool_result_items(self, results):
        return [{"role": "tool", "name": call.name, "result": result} for call, result in results]
