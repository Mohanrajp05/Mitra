
from __future__ import annotations

import asyncio
import base64
import copy
import datetime as _dt
import decimal
import hashlib
import json
import os
import threading
import time
import uuid as _uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.rag.agents.candidate_matching_agent import CandidateMatchingAgent
from app.rag.agents import matching_postcheck
from app.rag.ollama import load_ollama_settings

DEFAULT_ENABLED = True
DEFAULT_TTL_SECONDS = 900.0
DEFAULT_MAX_ENTRIES = 500


MATCH_PIPELINE_VERSION = "v1"


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
class MatchCacheSettings:
    enabled: bool = DEFAULT_ENABLED
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_entries: int = DEFAULT_MAX_ENTRIES

    def __post_init__(self) -> None:
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero.")
        if self.max_entries <= 0:
            raise ValueError("max_entries must be greater than zero.")


def load_match_cache_settings() -> MatchCacheSettings:
    raw_ttl = os.getenv("MATCH_CACHE_TTL_SECONDS", "").strip()
    raw_max = os.getenv("MATCH_CACHE_MAX_ENTRIES", "").strip()
    ttl = float(raw_ttl) if raw_ttl else DEFAULT_TTL_SECONDS
    max_entries = int(raw_max) if raw_max else DEFAULT_MAX_ENTRIES
    return MatchCacheSettings(
        enabled=_bool_env("MATCH_CACHE_ENABLED", DEFAULT_ENABLED),
        ttl_seconds=ttl,
        max_entries=max_entries,
    )


def _pipeline_fingerprint() -> str:
    """Fingerprint of model/config/prompt/post-check inputs affecting a match."""
    try:
        settings = load_ollama_settings()
        model = settings.model
    except Exception:
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip() or "llama3.1:8b"

    payload = {
        "pipeline": MATCH_PIPELINE_VERSION,
        "model": model,
        "agent": CandidateMatchingAgent.name,
        "system_prompt_sha256": hashlib.sha256(
            (CandidateMatchingAgent.system_prompt or "").encode("utf-8")
        ).hexdigest(),
        # Thresholds/weights are part of the deterministic scoring contract.
        "scoring": {
            "strong": matching_postcheck.STRONG_SCORE_THRESHOLD,
            "moderate": matching_postcheck.MODERATE_SCORE_THRESHOLD,
            "skill_weight": getattr(matching_postcheck, "SKILL_WEIGHT", 0.8),
            "experience_weight": getattr(matching_postcheck, "EXPERIENCE_WEIGHT", 0.2),
            "partial_skill_credit": getattr(matching_postcheck, "PARTIAL_SKILL_CREDIT", 0.5),
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalize_fingerprint_value(value: Any) -> Any:
  
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, decimal.Decimal):

        if value.is_finite():
            return format(value, "f")
        return str(value)
    if isinstance(value, _uuid.UUID):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return base64.b64encode(raw).decode("ascii")
    if isinstance(value, dict):
        # Keep every key/value; stringify keys for stable JSON object encoding.
        return {str(k): _normalize_fingerprint_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_fingerprint_value(v) for v in value]
    if isinstance(value, (set, frozenset)):
        normalized_items = [_normalize_fingerprint_value(v) for v in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )

    return str(value)


def _resume_fingerprint(owner_user_id: str, candidate_id: str, resolved_resume_text: str | None) -> str:
    """Return a stable version token for the candidate's current resume."""
    try:
        from app.rag.vector_store import get_document_store

        docs = get_document_store().list_documents(owner_user_id)
        resumes = [
            d
            for d in docs
            if isinstance(d, dict)
            and d.get("source_type") == "resume"
            and str(d.get("candidate_id") or "") == str(candidate_id)
        ]
        if resumes:
            current = sorted(
                resumes,
                key=lambda d: str(d.get("updated_at") or d.get("created_at") or ""),
            )[-1]
            return (
                f"doc:{current.get('document_id')}:{current.get('content_hash')}:"
                f"{current.get('updated_at') or current.get('created_at') or ''}"
            )
    except Exception:
        pass
    text = resolved_resume_text or ""
    return "text:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _job_fingerprint(job: dict[str, Any]) -> str:
    """Return a stable version token for the job fields used by matching."""
    skills = [str(s) for s in (job.get("required_skills") or [])]
    payload = {
        "id": str(job.get("id") or ""),
        "title": str(job.get("title") or ""),
        "company": str(job.get("company") or ""),
        "description": str(job.get("description") or ""),
        "required_skills": skills,
        "experience_required": job.get("experience_required"),
        "location": str(job.get("location") or ""),
    }
    normalized = _normalize_fingerprint_value(payload)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MatchCache:
    def __init__(self, settings: MatchCacheSettings | None = None) -> None:
        self.settings = settings or load_match_cache_settings()
        self._entries: OrderedDict[str, tuple[str, str, str, float, Any]] = OrderedDict()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def make_key(
        self,
        owner_user_id: str,
        candidate_id: str,
        job_id: str,
        resume_fingerprint: str,
        job_fingerprint: str,
        pipeline_fingerprint: str | None = None,
    ) -> str:
        pipeline = pipeline_fingerprint or _pipeline_fingerprint()
        parts = [
            owner_user_id,
            candidate_id,
            job_id,
            resume_fingerprint,
            job_fingerprint,
            pipeline,
        ]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    def _lookup(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            _, _, _, expires_at, result = entry
            if expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return copy.deepcopy(result)

    def _store(self, key: str, owner_user_id: str, candidate_id: str, job_id: str, result: Any) -> None:
        if not self._is_cacheable(result):
            return
        stored = copy.deepcopy(result)
        expires_at = time.monotonic() + self.settings.ttl_seconds
        with self._lock:
            if not self.settings.enabled:
                return
            self._entries[key] = (owner_user_id, candidate_id, job_id, expires_at, stored)
            self._entries.move_to_end(key)
            while len(self._entries) > self.settings.max_entries:
                self._entries.popitem(last=False)
                self._evictions += 1

    @staticmethod
    def _is_cacheable(result: Any) -> bool:
        """True only for a complete, validated match payload."""
        if not isinstance(result, dict):
            return False
        if str(result.get("candidate_id") or "") == "" or str(result.get("job_id") or "") == "":
            return False
        match = result.get("match")
        if match is None:
            return False
        # Accept both pydantic models and plain dicts.
        if hasattr(match, "model_dump"):
            try:
                data = match.model_dump()
            except Exception:
                return False
        elif isinstance(match, dict):
            data = match
        else:
            return False
        required_lists = ("matched_skills", "partial_skills", "missing_skills", "evidence")
        for name in required_lists:
            if not isinstance(data.get(name), list):
                return False
    
        if "unverified_skills" in data and not isinstance(data.get("unverified_skills"), list):
            return False
        score = data.get("match_score")
        if not isinstance(score, (int, float)) or score < 0 or score > 100:
            return False
        return True

    async def get_or_load(
        self,
        owner_user_id: str,
        candidate_id: str,
        job_id: str,
        key: str,
        loader: Callable[[], Awaitable[dict[str, Any]]],
        *,
        force_refresh: bool = False,
    ) -> tuple[dict[str, Any], str]:
      
        if not force_refresh:
            cached = self._lookup(key)
            if cached is not None:
                with self._lock:
                    self._hits += 1
                return cached, "hit"

        loop = asyncio.get_running_loop()
        is_leader = False
        with self._lock:
            inflight = self._inflight.get(key)
            if inflight is not None and not inflight.done():
                # Join an identical request that is already computing.
                self._misses += 1
            else:
                if not force_refresh:
                    cached = self._lookup(key)
                    if cached is not None:
                        self._hits += 1
                        return cached, "hit"
                self._misses += 1
                inflight = loop.create_future()
                self._inflight[key] = inflight
                is_leader = True

        if not is_leader:
            result, status = await inflight

            with self._lock:
                if self._misses > 0:
                    self._misses -= 1
                self._hits += 1
            joined_status = "hit" if status in ("miss", "refresh") else status
            return copy.deepcopy(result), joined_status

        try:
            result = await loader()
            self._store(key, owner_user_id, candidate_id, job_id, result)
            status = "refresh" if force_refresh else "miss"
            if not inflight.done():
                inflight.set_result((result, status))
            return copy.deepcopy(result), status
        except Exception as exc:
            if not inflight.done():
                inflight.set_exception(exc)
            raise
        finally:
            with self._lock:
                if self._inflight.get(key) is inflight:
                    self._inflight.pop(key, None)

    def invalidate_user(self, owner_user_id: str) -> int:
        removed = 0
        with self._lock:
            stale = [k for k, (owner, _, _, _, _) in self._entries.items() if owner == owner_user_id]
            for key in stale:
                self._entries.pop(key, None)
                removed += 1
        return removed

    def invalidate_candidate(self, owner_user_id: str, candidate_id: str) -> int:
        removed = 0
        with self._lock:
            stale = [
                k
                for k, (owner, cand, _, _, _) in self._entries.items()
                if owner == owner_user_id and cand == str(candidate_id)
            ]
            for key in stale:
                self._entries.pop(key, None)
                removed += 1
        return removed

    def invalidate_job(self, owner_user_id: str, job_id: str) -> int:
        removed = 0
        with self._lock:
            stale = [
                k
                for k, (owner, _, jid, _, _) in self._entries.items()
                if owner == owner_user_id and jid == str(job_id)
            ]
            for key in stale:
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
            self._inflight.clear()


_match_cache: MatchCache | None = None


def get_match_cache() -> MatchCache:
    global _match_cache
    if _match_cache is None:
        _match_cache = MatchCache()
    return _match_cache


def set_match_cache(cache: MatchCache | None) -> None:
    global _match_cache
    _match_cache = cache


def reset_match_cache() -> None:
    set_match_cache(None)