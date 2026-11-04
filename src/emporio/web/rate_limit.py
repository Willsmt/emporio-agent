"""Per-client sliding-window rate limit, to protect a public deployment from abuse and API cost."""
import threading
import time
from collections import defaultdict, deque
from typing import Callable


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self._window:
                hits.popleft()
            if len(hits) >= self._max:
                return False
            hits.append(now)
            return True
