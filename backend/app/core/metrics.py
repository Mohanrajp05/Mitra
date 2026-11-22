"""Lightweight in-process application metrics.

Bounded, thread-safe counters for API requests and AI provider activity.
Everything lives in process memory only: metrics reset whenever the backend
restarts and are not shared between multiple workers or replicas. No external
monitoring services are required.

Recording methods never raise: a metrics failure must never break a normal
application request. Recorded values are aggregates and identifiers only —
never request bodies, prompts, credentials, or candidate content.
"""

import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

DEFAULT_SLOW_REQUEST_MS = 2_000.0
MAX_STATUS_CODES = 64
MAX_SLOW_REQUESTS = 50
MAX_PROVIDERS = 16


def _slow_request_threshold() -> float:
    raw = os.getenv("METRICS_SLOW_REQUEST_MS", "").strip()
    if not raw:
        return DEFAULT_SLOW_REQUEST_MS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SLOW_REQUEST_MS
    return value if value > 0 else DEFAULT_SLOW_REQUEST_MS


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.slow_request_ms = _slow_request_threshold()
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._requests_total = 0
        self._requests_success = 0
        self._requests_failed = 0
        self._status_counts: dict[int, int] = {}
        self._duration_count = 0
        self._duration_total_ms = 0.0
        self._duration_max_ms = 0.0
        self._slow_requests: deque[dict] = deque(maxlen=MAX_SLOW_REQUESTS)
        self._slow_requests_total = 0
        self._llm_calls_total = 0
        self._llm_calls_success = 0
        self._llm_calls_failed = 0
        self._llm_attempts_failed = 0
        self._llm_fallback_attempts = 0
        self._llm_timeouts = 0
        self._llm_provider_failures: dict[str, int] = {}
        self._llm_latency_count = 0
        self._llm_latency_total_ms = 0.0
        self._llm_latency_max_ms = 0.0

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        request_id: str,
    ) -> None:
        try:
            with self._lock:
                self._requests_total += 1
                if status_code < 400:
                    self._requests_success += 1
                else:
                    self._requests_failed += 1
                if len(self._status_counts) < MAX_STATUS_CODES or status_code in self._status_counts:
                    self._status_counts[status_code] = (
                        self._status_counts.get(status_code, 0) + 1
                    )
                self._duration_count += 1
                self._duration_total_ms += duration_ms
                self._duration_max_ms = max(self._duration_max_ms, duration_ms)
                if duration_ms > self.slow_request_ms:
                    self._slow_requests_total += 1
                    self._slow_requests.append(
                        {
                            "request_id": request_id,
                            "method": method,
                            "path": path,
                            "status": status_code,
                            "duration_ms": round(duration_ms, 2),
                        }
                    )
        except Exception:
            pass

    def record_llm_provider_failure(self, provider_slug: str, timeout: bool = False) -> None:
        try:
            with self._lock:
                self._llm_attempts_failed += 1
                if len(self._llm_provider_failures) < MAX_PROVIDERS or provider_slug in self._llm_provider_failures:
                    self._llm_provider_failures[provider_slug] = (
                        self._llm_provider_failures.get(provider_slug, 0) + 1
                    )
                if timeout:
                    self._llm_timeouts += 1
        except Exception:
            pass

    def record_llm_fallback(self) -> None:
        try:
            with self._lock:
                self._llm_fallback_attempts += 1
        except Exception:
            pass

    def record_llm_success(self, duration_ms: float) -> None:
        try:
            with self._lock:
                self._llm_calls_total += 1
                self._llm_calls_success += 1
                self._llm_latency_count += 1
                self._llm_latency_total_ms += duration_ms
                self._llm_latency_max_ms = max(self._llm_latency_max_ms, duration_ms)
        except Exception:
            pass

    def record_llm_failure(self, duration_ms: float) -> None:
        try:
            with self._lock:
                self._llm_calls_total += 1
                self._llm_calls_failed += 1
        except Exception:
            pass

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "started_at": self._started_at,
                "slow_request_threshold_ms": self.slow_request_ms,
                "requests": {
                    "total": self._requests_total,
                    "success": self._requests_success,
                    "failed": self._requests_failed,
                    "status_counts": dict(sorted(self._status_counts.items())),
                    "duration": {
                        "count": self._duration_count,
                        "total_ms": round(self._duration_total_ms, 2),
                        "max_ms": round(self._duration_max_ms, 2),
                    },
                    "slow": {
                        "total": self._slow_requests_total,
                        "recent": list(self._slow_requests),
                    },
                },
                "llm": {
                    "calls_total": self._llm_calls_total,
                    "calls_success": self._llm_calls_success,
                    "calls_failed": self._llm_calls_failed,
                    "attempts_failed": self._llm_attempts_failed,
                    "fallback_attempts": self._llm_fallback_attempts,
                    "timeouts": self._llm_timeouts,
                    "provider_failures": dict(sorted(self._llm_provider_failures.items())),
                    "latency": {
                        "count": self._llm_latency_count,
                        "total_ms": round(self._llm_latency_total_ms, 2),
                        "max_ms": round(self._llm_latency_max_ms, 2),
                    },
                },
            }

    def clear(self) -> None:
        with self._lock:
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._requests_total = self._requests_success = self._requests_failed = 0
            self._status_counts.clear()
            self._duration_count = 0
            self._duration_total_ms = self._duration_max_ms = 0.0
            self._slow_requests.clear()
            self._slow_requests_total = 0
            self._llm_calls_total = self._llm_calls_success = self._llm_calls_failed = 0
            self._llm_attempts_failed = self._llm_fallback_attempts = 0
            self._llm_timeouts = 0
            self._llm_provider_failures.clear()
            self._llm_latency_count = 0
            self._llm_latency_total_ms = self._llm_latency_max_ms = 0.0


_metrics: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    global _metrics
    if _metrics is None:
        _metrics = MetricsRegistry()
    return _metrics


def set_metrics(registry: MetricsRegistry | None) -> None:
    global _metrics
    _metrics = registry


def reset_metrics() -> None:
    set_metrics(None)
