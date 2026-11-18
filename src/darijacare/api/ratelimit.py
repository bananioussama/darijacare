"""In-memory sliding-window rate limiter (one API process).

Enough for the academic deployment (a single backend container). Behind several
workers or replicas it would move to the nginx proxy or a shared store (Phase 6).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """At most ``limit`` hits per ``window`` seconds for each (bucket, key)."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, bucket: str, key: str, limit: int) -> float | None:
        """Record one hit; return ``None`` if allowed, else seconds before a retry."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[(bucket, key)]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= limit:
                return max(self.window - (now - hits[0]), 0.0)
            hits.append(now)
            return None

    def reset(self) -> None:
        """Forget every hit (tests)."""
        with self._lock:
            self._hits.clear()
