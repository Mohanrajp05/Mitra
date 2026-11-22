

import asyncio
import copy
import hashlib
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

DEFAULT_ENABLED = True
DEFAULT_TTL_SECONDS = 300.0
DEFAULT_MAX_ENTRIES = 500

_WHITESPACE_PATTERN = re.compile(r"\s+")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name} must be a boolean value.")


@dataclass(frozen=True)
class CacheSettings:
    enabled: bool = DEFAULT_ENABLED
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_entries: int = DEFAULT_MAX_ENTRIES

    def __post_init__(self) -> None:
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero.")
        if self.max_entries <= 0:
            raise ValueError("max_entries must be greater than zero.")


def load_cache_settings() -> CacheSettings:
    raw_ttl = os.getenv("RAG_CACHE_TTL_SECONDS", "").strip()
    raw_max = os.getenv("RAG_CACHE_MAX_ENTRIES", "").strip()
    ttl = float(raw_ttl) if raw_ttl else DEFAULT_TTL_SECONDS
    max_entries = int(raw_max) if raw_max else DEFAULT_MAX_ENTRIES
    return CacheSettings(
        enabled=_bool_env("RAG_CACHE_ENABLED", DEFAULT_ENABLED),
        ttl_seconds=ttl,
        max_entries=max_entries,
    )


class ResponseCache:
    def __init__(self, settings: CacheSettings | None = None) -> None:
        self.settings = settings or load_cache_settings()
        self._entries: OrderedDict[str, tuple[str, float, Any]] = OrderedDict()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def make_key(
        self,
        owner_user_id: str,
        query: str,
        candidate_id: str | None = None,
        job_id: str | None = None,
        top_k: int | None = None,
        document_ids: list[str] | None = None,
    ) -> str:
        normalized = _WHITESPACE_PATTERN.sub(" ", (query or "")).strip().casefold()
        parts = [
            owner_user_id,
            normalized,
            candidate_id or "",
            job_id or "",
            str(top_k) if top_k is not None else "default",
            ",".join(sorted(document_ids)) if document_ids else "",
        ]
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
        return digest

    def get(self, key: str) -> Any:
        entry = self._lookup(key)
        if entry is None:
            with self._lock:
                self._misses += 1
            return None
        with self._lock:
            self._hits += 1
        return entry

    def set(self, key: str, result: Any, owner_user_id: str = "") -> None:
        self._store(key, result, owner_user_id)

    async def get_or_load(
        self,
        owner_user_id: str,
        query: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        candidate_id: str | None = None,
        job_id: str | None = None,
        top_k: int | None = None,
        document_ids: list[str] | None = None,
    ) -> Any:
        key = self.make_key(owner_user_id, query, candidate_id, job_id, top_k, document_ids)
        entry = self._lookup(key)
        if entry is not None:
            with self._lock:
                self._hits += 1
            return entry

        with self._lock:
            self._misses += 1
            key_lock = self._key_locks.get(key)
            if key_lock is None:
                key_lock = asyncio.Lock()
                self._key_locks[key] = key_lock

        async with key_lock:
            entry = self._lookup(key)
            if entry is not None:
                with self._lock:
                    self._hits += 1
                return entry

            result = await loader()
            self._store(key, result, owner_user_id)
            return result

    def invalidate_user(self, owner_user_id: str) -> int:
        removed = 0
        with self._lock:
            stale_keys = [
                key
                for key, (owner, _, _) in self._entries.items()
                if owner == owner_user_id
            ]
            for key in stale_keys:
                self._entries.pop(key, None)
                removed += 1
        return removed

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.settings.enabled,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "entries": len(self._entries),
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._key_locks.clear()

    def _lookup(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            _, expires_at, result = entry
            if expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return result

    def _store(self, key: str, result: Any, owner_user_id: str = "") -> None:
        if result is None or not getattr(result, "has_evidence", False):
            return
        if not getattr(result, "sources", None):
            return

        stored = copy.deepcopy(result)
        expires_at = time.monotonic() + self.settings.ttl_seconds

        with self._lock:
            if not self.settings.enabled:
                return
            self._entries[key] = (owner_user_id, expires_at, stored)
            self._entries.move_to_end(key)
            while len(self._entries) > self.settings.max_entries:
                self._entries.popitem(last=False)
                self._evictions += 1


_response_cache: ResponseCache | None = None


def get_response_cache() -> ResponseCache:
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache


def set_response_cache(cache: ResponseCache | None) -> None:
    global _response_cache
    _response_cache = cache


def reset_response_cache() -> None:
    set_response_cache(None)
