

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.audit import (
    ACCOUNT_DATA_DELETED,
    DATA_EXPORTED,
    RETENTION_CLEANUP,
    get_audit_trail,
)
from app.database import chat_queries, consent_queries, queries
from app.database.connection import get_connection
from app.rag.response_cache import get_response_cache
from app.rag.vector_store import get_document_store

RETENTION_POLICIES = {
    "chat_messages": "RETENTION_CHAT_MESSAGES_DAYS",
    "documents": "RETENTION_DOCUMENTS_DAYS",
    "candidates": "RETENTION_CANDIDATES_DAYS",
}


class RetentionConfigError(ValueError):
    pass


def _retention_days(policy: str) -> int:
    raw = os.getenv(RETENTION_POLICIES[policy], "").strip()
    if not raw:
        return 0
    try:
        days = int(raw)
    except ValueError:
        raise RetentionConfigError(
            f"{RETENTION_POLICIES[policy]} must be a whole number of days."
        )
    if days < 0:
        raise RetentionConfigError(
            f"{RETENTION_POLICIES[policy]} must be zero or a positive number of days."
        )
    return days


def _cutoff(days: int) -> datetime | None:
    if days <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def _cutoff_iso(days: int) -> str | None:
    cutoff = _cutoff(days)
    return cutoff.isoformat() if cutoff else None


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def retention_config() -> dict[str, dict[str, Any]]:
    return {
        policy: {
            "env": env_name,
            "days": _retention_days(policy),
            "cutoff": _cutoff_iso(_retention_days(policy)),
        }
        for policy, env_name in RETENTION_POLICIES.items()
    }


def expired_summary(owner_user_id: str) -> dict[str, Any]:
    """Count the caller's own records that are older than each enabled policy."""
    policies = retention_config()

    with get_connection() as connection:
        counts = {
            "chat_messages": 0,
            "candidates": 0,
        }
        for policy in ("chat_messages", "candidates"):
            days = _retention_days(policy)
            if days <= 0:
                continue
            older_than = _cutoff_iso(days)
            if policy == "chat_messages":
                counts[policy] = chat_queries.count_expired_messages(
                    connection, owner_user_id, older_than
                )
            else:
                counts[policy] = queries.count_expired_candidates(
                    connection, owner_user_id, older_than
                )

    documents_expired = 0
    document_days = _retention_days("documents")
    if document_days > 0:
        cutoff = _cutoff(document_days)
        documents_expired = sum(
            1
            for item in get_document_store().list_documents(owner_user_id)
            if (created := _parse_timestamp(item.get("created_at"))) and created < cutoff
        )
    counts["documents"] = documents_expired

    return {
        "owner_user_id": owner_user_id,
        "policies": policies,
        "expired": counts,
        "note": (
            "Nothing is deleted automatically. Expired records are only removed "
            "when cleanup is explicitly requested through the authenticated "
            "retention cleanup endpoint."
        ),
    }


def cleanup_expired(owner_user_id: str) -> dict[str, Any]:
    """Delete only the verified caller's records older than enabled policies."""
    policies = retention_config()
    deleted: dict[str, int] = {
        "chat_messages": 0,
        "documents": 0,
        "candidates": 0,
    }
    warnings: list[str] = []

    with get_connection() as connection:
        message_days = _retention_days("chat_messages")
        if message_days > 0:
            deleted["chat_messages"] = chat_queries.delete_expired_messages(
                connection, owner_user_id, _cutoff_iso(message_days)
            )

        candidate_days = _retention_days("candidates")
        if candidate_days > 0:
            deleted["candidates"] = queries.delete_expired_candidates(
                connection, owner_user_id, _cutoff_iso(candidate_days)
            )

    document_days = _retention_days("documents")
    if document_days > 0:
        cutoff = _cutoff(document_days)
        store = get_document_store()
        for item in store.list_documents(owner_user_id):
            created = _parse_timestamp(item.get("created_at"))
            if created is None or created >= cutoff:
                continue
            document_id = str(item.get("document_id") or "")
            if not document_id:
                continue
            try:
                if store.delete_document(owner_user_id, document_id):
                    get_response_cache().invalidate_user(owner_user_id)
                    deleted["documents"] += 1
            except Exception as exc:
                warnings.append(
                    f"document {document_id} could not be deleted "
                    f"({type(exc).__name__})"
                )

    counts_detail = ", ".join(
        f"{key}={value}" for key, value in deleted.items()
    )
    detail = f"expired_cleanup {counts_detail}"
    if warnings:
        detail += f", warnings={len(warnings)}"
    get_audit_trail().record(
        RETENTION_CLEANUP,
        user_id=owner_user_id,
        status="success",
        detail=detail,
    )

    return {
        "deleted": deleted,
        "warnings": warnings,
        "policies": policies,
    }


def export_owner_data(owner_user_id: str) -> dict[str, Any]:
    """Collect the verified caller's own application data for export."""
    with get_connection() as connection:
        jobs = queries.list_jobs(connection, owner_user_id)
        candidates = queries.list_candidates(connection, owner_user_id)
        consents = consent_queries.list_consents_for_owner(connection, owner_user_id)
        sessions = chat_queries.list_sessions(connection, owner_user_id)
        sessions_with_messages = [
            {
                **dict(session),
                "messages": chat_queries.list_messages(
                    connection, owner_user_id, str(session.get("id") or "")
                ),
            }
            for session in sessions
        ]

    documents = get_document_store().list_documents(owner_user_id)

    counts = {
        "jobs": len(jobs),
        "candidates": len(candidates),
        "consents": len(consents),
        "chat_sessions": len(sessions_with_messages),
        "chat_messages": sum(
            len(item.get("messages") or []) for item in sessions_with_messages
        ),
        "documents": len(documents),
    }

    get_audit_trail().record(
        DATA_EXPORTED,
        user_id=owner_user_id,
        detail="counts=" + ", ".join(f"{k}={v}" for k, v in counts.items()),
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "owner_user_id": owner_user_id,
        "counts": counts,
        "jobs": [dict(job) for job in jobs],
        "candidates": [dict(candidate) for candidate in candidates],
        "consents": [dict(consent) for consent in consents],
        "chat_sessions": sessions_with_messages,
        "documents": documents,
        "note": (
            "Document metadata is included but uploaded file contents are not; "
            "files must be downloaded individually through the document "
            "endpoints. The Supabase Auth account is managed by Supabase and "
            "is not part of this export."
        ),
    }


def delete_account_data(owner_user_id: str) -> dict[str, Any]:
    """Delete the verified caller's application data, file cleanup included.

    Categories are processed in a safe order (document files first, then
    database rows that cascade). A failure in one category is recorded as a
    warning and does not stop the remaining categories. The Supabase Auth
    account itself is never deleted.
    """
    deleted: dict[str, int] = {}
    warnings: list[str] = []

    document_count = 0
    try:
        store = get_document_store()
        for item in store.list_documents(owner_user_id):
            document_id = str(item.get("document_id") or "")
            if not document_id:
                continue
            try:
                if store.delete_document(owner_user_id, document_id):
                    get_response_cache().invalidate_user(owner_user_id)
                    document_count += 1
            except Exception as exc:
                warnings.append(
                    f"document {document_id} could not be deleted "
                    f"({type(exc).__name__})"
                )
    except Exception as exc:
        warnings.append(
            f"document store unavailable; uploaded files may remain "
            f"({type(exc).__name__})"
        )
    deleted["documents"] = document_count

    try:
        with get_connection() as connection:
            deleted["consents"] = consent_queries.delete_consents_for_owner(
                connection, owner_user_id
            )
            deleted["candidates"] = queries.delete_all_candidates_for_owner(
                connection, owner_user_id
            )
            deleted["jobs"] = queries.delete_all_jobs_for_owner(
                connection, owner_user_id
            )
            deleted["chat_sessions"] = chat_queries.delete_all_sessions(
                connection, owner_user_id
            )
    except Exception as exc:
        warnings.append(
            "database deletion incomplete; some records may remain "
            f"({type(exc).__name__})"
        )

    detail = ", ".join(f"{key}={value}" for key, value in deleted.items())
    if warnings:
        detail += f", warnings={len(warnings)}"
    get_audit_trail().record(
        ACCOUNT_DATA_DELETED,
        user_id=owner_user_id,
        status="failure" if warnings else "success",
        detail=detail,
    )

    return {
        "deleted": deleted,
        "warnings": warnings,
        "supabase_account": (
            "not_deleted: the application has no supported mechanism to delete "
            "a Supabase Auth account. Manage the account through Supabase Auth "
            "directly."
        ),
    }
