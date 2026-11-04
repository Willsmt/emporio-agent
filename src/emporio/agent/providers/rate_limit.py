"""Client-side pacing for providers with low request-per-minute quotas (e.g. Gemini free tier).

A Decorator: wraps any LLMProvider and only delays `generate`; everything else is delegated.
"""
import time
from typing import Any, Callable

from emporio.agent.types import ModelTurn, ToolSpec


class RateLimitedProvider:
    def __init__(
        self,
        provider: Any,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._provider = provider
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def generate(self, system_prompt: str, history: list[Any], tools: list[ToolSpec]) -> ModelTurn:
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()
        return self._provider.generate(system_prompt, history, tools)
