"""Lightweight audit logging for important user and system actions.

Storage for this MVP: structured audit lines on the dedicated ``audit``
logger plus a bounded in-memory ring buffer for diagnostics. No new database
tables and no event-streaming infrastructure.

Every entry contains only structured metadata: timestamp, event type,
authenticated user UUID (when applicable), resource UUID (when applicable),
request ID, and a success/failure status. The ``record`` signature accepts no
free-form content on purpose — complete chat messages, resumes, API keys, and
tokens can never enter audit entries.

In-memory buffer contents reset when the backend restarts and are not shared
between workers. The buffer is internal; it is never exposed through an API
endpoint.
"""

import json
import logging
import threading
from collections import deque
from datetime import datetime, timezone

DEFAULT_BUFFER_SIZE = 500

audit_logger = logging.getLogger("audit")

CHAT_SESSION_CREATED = "chat_session_created"
CHAT_SESSION_RENAMED = "chat_session_renamed"
CHAT_SESSION_DELETED = "chat_session_deleted"
CHAT_HISTORY_CLEARED = "chat_history_cleared"
DOCUMENT_UPLOADED = "document_uploaded"
DOCUMENT_DELETED = "document_deleted"
DOCUMENTS_REINDEXED = "documents_reindexed"
LLM_PROVIDER_FALLBACK = "llm_provider_fallback"
RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
CANDIDATE_CREATED = "candidate_created"
CANDIDATE_UPDATED = "candidate_updated"
CANDIDATE_DELETED = "candidate_deleted"
CONSENT_GRANTED = "consent_granted"
CONSENT_WITHDRAWN = "consent_withdrawn"
DATA_EXPORTED = "data_exported"
ACCOUNT_DATA_DELETED = "account_data_deleted"
RETENTION_CLEANUP = "retention_cleanup"

KNOWN_EVENT_TYPES = frozenset(
    {
        CHAT_SESSION_CREATED,
        CHAT_SESSION_RENAMED,
        CHAT_SESSION_DELETED,
        CHAT_HISTORY_CLEARED,
        DOCUMENT_UPLOADED,
        DOCUMENT_DELETED,
        DOCUMENTS_REINDEXED,
        LLM_PROVIDER_FALLBACK,
        RATE_LIMIT_EXCEEDED,
        CANDIDATE_CREATED,
        CANDIDATE_UPDATED,
        CANDIDATE_DELETED,
        CONSENT_GRANTED,
        CONSENT_WITHDRAWN,
        DATA_EXPORTED,
        ACCOUNT_DATA_DELETED,
        RETENTION_CLEANUP,
    }
)


class AuditTrail:
    def __init__(self, buffer_size: int = DEFAULT_BUFFER_SIZE) -> None:
        self.buffer_size = buffer_size
        self._events: deque[dict] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()

    def record(
        self,
        event_type: str,
        *,
        user_id: str | None = None,
        resource_id: str | None = None,
        status: str = "success",
        detail: str | None = None,
    ) -> dict | None:
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "user_id": user_id,
                "resource_id": resource_id,
                "status": status,
                "request_id": _current_request_id(),
                "detail": detail,
            }
            with self._lock:
                self._events.append(entry)
            audit_logger.info(
                "audit %s",
                json.dumps(entry, ensure_ascii=False, default=str),
            )
            return entry
        except Exception:
            return None

    def recent(self, limit: int | None = None) -> list[dict]:
        with self._lock:
            events = list(self._events)
        if limit is not None:
            events = events[-limit:]
        return events

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


def _current_request_id() -> str:
    try:
        from app.main import request_id_var

        return request_id_var.get()
    except Exception:
        return "-"


_audit_trail: AuditTrail | None = None


def get_audit_trail() -> AuditTrail:
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = AuditTrail()
    return _audit_trail


def set_audit_trail(trail: AuditTrail | None) -> None:
    global _audit_trail
    _audit_trail = trail


def reset_audit_trail() -> None:
    set_audit_trail(None)
