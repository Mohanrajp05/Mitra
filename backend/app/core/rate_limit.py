"""In-process sliding-window rate limiting for expensive chat endpoints.

The limiter keeps request timestamps per key (the verified Supabase user ID)
in a plain dict protected by a lock. It is intentionally simple:

- Limits reset whenever the backend process restarts.
- Limits are NOT shared across multiple workers or replicas; each process
  enforces its own window. This is acceptable for the current single-process
  deployment and deliberately avoids introducing Redis.

The limiter counts every send attempt, including requests rejected by
validation, so repeated abusive or suspicious requests are throttled too.
"""

import os
import threading
import time
from collections import defaultdict, deque

DEFAULT_MAX_REQUESTS = 30
DEFAULT_WINDOW_SECONDS = 60.0


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "Too many messages sent. Please wait a moment and try again."
        )
        self.retry_after = max(1, int(retry_after))


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero.")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero.")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def acquire(self, key: str) -> tuple[bool, float]:
        """Record one hit for key. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= window_start:
                hits.popleft()
            if len(hits) >= self.max_requests:
                retry_after = self.window_seconds - (now - hits[0])
                return False, max(retry_after, 1.0)
            hits.append(now)
            return True, 0.0

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


def _load_limiter() -> SlidingWindowRateLimiter:
    raw_max = os.getenv("CHAT_RATE_LIMIT_MAX_REQUESTS", "").strip()
    raw_window = os.getenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "").strip()
    max_requests = int(raw_max) if raw_max else DEFAULT_MAX_REQUESTS
    window = float(raw_window) if raw_window else DEFAULT_WINDOW_SECONDS
    return SlidingWindowRateLimiter(max_requests, window)


_rate_limiter: SlidingWindowRateLimiter | None = None


def get_rate_limiter() -> SlidingWindowRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = _load_limiter()
    return _rate_limiter


def set_rate_limiter(limiter: SlidingWindowRateLimiter | None) -> None:
    global _rate_limiter
    _rate_limiter = limiter
