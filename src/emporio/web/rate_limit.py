"""Per-client sliding-window rate limit, to protect a public deployment from abuse and API cost."""
import threading
import time
from collections import defaultdict, deque
from typing import Callable


MAX_TRACKED_KEYS = 10_000


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = MAX_TRACKED_KEYS):
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._hits)

    def _prune(self, now: float) -> None:
        """Forget clients with no hits inside the window, so memory stays bounded."""
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] > self._window]:
            del self._hits[key]

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            if key not in self._hits and len(self._hits) >= self._max_keys:
                self._prune(now)
            hits = self._hits[key]
            while hits and now - hits[0] > self._window:
                hits.popleft()
            if len(hits) >= self._max:
                return False
            hits.append(now)
            return True
