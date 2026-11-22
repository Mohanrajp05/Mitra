
import asyncio
import logging
import re
from dataclasses import asdict, fields
from typing import Any
from uuid import UUID

from app.core.audit import (
    CHAT_HISTORY_CLEARED,
    CHAT_SESSION_CREATED,
    CHAT_SESSION_DELETED,
    CHAT_SESSION_RENAMED,
    get_audit_trail,
)
from app.database import chat_queries
from app.database.connection import get_connection
from app.schemas.chat import (
    DEFAULT_SESSION_TITLE,
    ChatMessageCreate,
    ChatSessionCreate,
    ChatSessionRename,
)
from app.services import rag_service
from app.services.guardrails import (
    CAPABILITY_ANSWER,
    GREETING_ANSWER,
    INJECTION_ANSWER,
    OFF_TOPIC_ANSWER,
    classify_message,
    classify_unclear_message,
    validate_message,
)
from app.services.job_search_service import (
    JobPreferences,
    TavilyError,
    clarification_question,
    extract_preferences,
    fallback_role,
    format_job_answer,
    is_job_search,
    job_sources,
    missing_essential,
    search_jobs,
)

logger = logging.getLogger(__name__)


class SessionNotFoundError(RuntimeError):
    pass


class ChatLimitExceededError(RuntimeError):
    pass


MAX_CHAT_SESSIONS_PER_USER = 10


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _require_session(connection, owner_user_id: str, session_id: str) -> dict[str, Any]:
    session = chat_queries.get_session(connection, owner_user_id, session_id)
    if session is None:
        raise SessionNotFoundError("Chat session not found.")
    return session


def _session_title(title: str | None) -> str:
    text = (title or "").strip()
    return text or DEFAULT_SESSION_TITLE


def list_sessions(owner_user_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        return chat_queries.list_sessions(connection, owner_user_id)


def _session_event_id(session: Any) -> str:
    if isinstance(session, dict):
        return str(session.get("id") or "")
    return str(getattr(session, "id", "") or "")


def create_session(
    owner_user_id: str, payload: ChatSessionCreate | None = None
) -> dict[str, Any]:
    title = _session_title(payload.title if payload else None)
    with get_connection() as connection:
        existing_sessions = [
            session
            for session in chat_queries.list_sessions(connection, owner_user_id)
            if session is not None
        ]
        existing_sessions.sort(
            key=lambda session: str(session.get("created_at") or "")
        )
        if len(existing_sessions) >= MAX_CHAT_SESSIONS_PER_USER:
            get_audit_trail().record(
                CHAT_SESSION_CREATED,
                user_id=owner_user_id,
                resource_id="",
                status="failure",
                detail="chat_limit_exceeded",
            )
            raise ChatLimitExceededError(
                "You have reached the maximum limit of "
                f"{MAX_CHAT_SESSIONS_PER_USER} chat conversations for your account. "
                "You cannot create a new conversation right now."
            )
        session = chat_queries.create_session(connection, owner_user_id, title)
    get_audit_trail().record(
        CHAT_SESSION_CREATED,
        user_id=owner_user_id,
        resource_id=_session_event_id(session),
    )
    return session


def rename_session(
    owner_user_id: str, session_id: str, payload: ChatSessionRename
) -> dict[str, Any]:
    if not _is_uuid(session_id):
        get_audit_trail().record(
            CHAT_SESSION_RENAMED,
            user_id=owner_user_id,
            resource_id=session_id,
            status="failure",
            detail="session_not_found",
        )
        raise SessionNotFoundError("Chat session not found.")

    with get_connection() as connection:
        session = chat_queries.rename_session(
            connection, owner_user_id, session_id, payload.title
        )

    if session is None:
        get_audit_trail().record(
            CHAT_SESSION_RENAMED,
            user_id=owner_user_id,
            resource_id=session_id,
            status="failure",
            detail="session_not_found",
        )
        raise SessionNotFoundError("Chat session not found.")

    get_audit_trail().record(
        CHAT_SESSION_RENAMED,
        user_id=owner_user_id,
        resource_id=_session_event_id(session),
    )
    return session


def delete_session(owner_user_id: str, session_id: str) -> None:
    if not _is_uuid(session_id):
        get_audit_trail().record(
            CHAT_SESSION_DELETED,
            user_id=owner_user_id,
            resource_id=session_id,
            status="failure",
            detail="session_not_found",
        )
        raise SessionNotFoundError("Chat session not found.")

    with get_connection() as connection:
        deleted = chat_queries.delete_session(connection, owner_user_id, session_id)

    if not deleted:
        get_audit_trail().record(
            CHAT_SESSION_DELETED,
            user_id=owner_user_id,
            resource_id=session_id,
            status="failure",
            detail="session_not_found",
        )
        raise SessionNotFoundError("Chat session not found.")

    get_audit_trail().record(
        CHAT_SESSION_DELETED, user_id=owner_user_id, resource_id=session_id
    )


def delete_all_sessions(owner_user_id: str) -> int:
    with get_connection() as connection:
        deleted = chat_queries.delete_all_sessions(connection, owner_user_id)
    get_audit_trail().record(
        CHAT_HISTORY_CLEARED,
        user_id=owner_user_id,
        detail=f"deleted_count={deleted}",
    )
    return deleted


def list_messages(owner_user_id: str, session_id: str) -> list[dict[str, Any]]:
    if not _is_uuid(session_id):
        raise SessionNotFoundError("Chat session not found.")

    with get_connection() as connection:
        _require_session(connection, owner_user_id, session_id)
        return chat_queries.list_messages(connection, owner_user_id, session_id)


def _check_session(owner_user_id: str, session_id: str) -> None:
    with get_connection() as connection:
        _require_session(connection, owner_user_id, session_id)


CHAT_HISTORY_LIMIT_TURNS = 6


def _load_history(owner_user_id: str, session_id: str) -> list[dict[str, Any]]:
    """Load the recent conversation history (oldest → newest) for context."""
    with get_connection() as connection:
        messages = chat_queries.list_messages(connection, owner_user_id, session_id)
    history: list[dict[str, Any]] = []
    for message in list(messages or [])[-(CHAT_HISTORY_LIMIT_TURNS * 2):]:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        history.append(
            {
                "role": str(message.get("role") or ""),
                "content": content,
                "sources": message.get("sources") or [],
            }
        )
    return history


def _pending_job_search_missing(history: list[dict[str, Any]] | None) -> str:
    """Return the first still-missing job-search preference from history."""
    for message in reversed(list(history or [])):
        if str(message.get("role") or "") != "assistant":
            continue
        sources = message.get("sources") or []
        if isinstance(sources, dict):
            sources = [sources]
        for source in sources if isinstance(sources, list) else []:
            if isinstance(source, dict) and source.get("kind") == "job_search_prompt":
                missing = source.get("missing") or []
                if isinstance(missing, str) and missing.strip():
                    return missing.strip()
                if isinstance(missing, (list, tuple)) and missing:
                    return str(missing[0])
    return ""



def _persist_exchange(
    owner_user_id: str,
    session_id: str,
    content: str,
    result: Any,
) -> dict[str, Any]:
    with get_connection() as connection:
        _require_session(connection, owner_user_id, session_id)
        user_message = chat_queries.create_message(
            connection,
            owner_user_id,
            session_id,
            role="user",
            content=content,
        )
        assistant_message = chat_queries.create_message(
            connection,
            owner_user_id,
            session_id,
            role="assistant",
            content=result.answer,
            sources=result.sources,
            has_evidence=result.has_evidence,
        )
        chat_queries.touch_session(connection, owner_user_id, session_id)

    return {"user_message": user_message, "assistant_message": assistant_message}


async def send_message(
    owner_user_id: str, session_id: str, payload: ChatMessageCreate
) -> dict[str, Any]:
    if not _is_uuid(session_id):
        raise SessionNotFoundError("Chat session not found.")

    content = validate_message(payload.content)

    await asyncio.to_thread(_check_session, owner_user_id, session_id)

    history: list[dict[str, Any]] = []
    try:
        history = await asyncio.to_thread(_load_history, owner_user_id, session_id)
    except Exception:
        # History is context only; never block a valid exchange on it.
        history = []

    kind = classify_message(content)
    pending_missing = _pending_job_search_missing(history)

    # Fixed answers and security refusals always win first.
    if kind in ("greeting", "capability", "injection", "off_topic"):
        result = _general_answer(content, kind)
    elif kind == "job_search" or payload.job_search or pending_missing:
        # The user is either starting a job search or answering a pending
        # role/location question.  This must be decided BEFORE the standalone
        # intent check, otherwise a short answer ("Andhra Pradesh") is judged
        # out of context and rejected as off-topic.
        result = await _run_job_search(
            content,
            payload.job_preferences,
            history=history,
            pending_missing=pending_missing,
        )
    else:
        blocked = False
        if kind == "general":
            verdict = await classify_unclear_message(content)
            if verdict is False:
                blocked = True
        if blocked:
            result = _general_answer(content, "off_topic")
        else:
            logger.info("chat rag query intent=%s", kind)
            query_kwargs: dict[str, Any] = {}
            if payload.candidate_id:
                query_kwargs["candidate_id"] = payload.candidate_id
            if payload.job_id:
                query_kwargs["job_id"] = payload.job_id
            if payload.document_ids:
                query_kwargs["document_ids"] = payload.document_ids
            if history:
                result = await rag_service.query(
                    owner_user_id, content, history=history, **query_kwargs
                )
            else:
                result = await rag_service.query(owner_user_id, content, **query_kwargs)

    return await asyncio.to_thread(
        _persist_exchange, owner_user_id, session_id, content, result
    )


async def _run_job_search(
    content: str,
    stored: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    pending_missing: str | None = None,
) -> Any:
    from app.rag.pipeline import PipelineResult

    # ChatSource responses include null metadata fields (document_id, chunk_id,
    # ...) which the frontend copies into job_preferences.  Keep only real
    # preference fields so a follow-up can never 500 on unknown keys.
    preference_fields = {field.name for field in fields(JobPreferences)}
    clean_stored = {
        key: value
        for key, value in (stored or {}).items()
        if key in preference_fields and value is not None
    }
    base = JobPreferences(**clean_stored)
    prefs = extract_preferences(content, base)

    # If a pending job-search question was answered, apply the answer to the
    # pending slot instead of asking the same question again.
    pending = (
        _pending_job_search_missing(history)
        if pending_missing is None
        else pending_missing
    )
    if pending and missing_essential(prefs):
        if pending == "role" and not prefs.role:
            # Preserve the user-provided role text verbatim.
            prefs.role = re.sub(r"\s+", " ", content.strip()).strip("?.! ").strip()
        elif pending == "location" and not prefs.location and not prefs.remote:
            prefs.location = re.sub(r"\s+", " ", content.strip()).strip("?.! ").strip()

    missing = missing_essential(prefs)

    if not prefs.role and missing == "role" and is_job_search(content):
        # Accept user-provided role text that no alias pattern covers.
        fallback = fallback_role(content)
        if fallback:
            prefs.role = fallback
            missing = missing_essential(prefs)

    if missing:
        return PipelineResult(
            query=content,
            answer=clarification_question(missing, prefs),
            has_evidence=False,
            sources=[
                {
                    "kind": "job_search_prompt",
                    "missing": missing,
                    "preferences": asdict(prefs),
                }
            ],
            evidence_text="",
        )

    try:
        listings = await search_jobs(prefs)
    except TavilyError as exc:
        return PipelineResult(
            query=content,
            answer=str(exc),
            has_evidence=False,
            sources=[],
            evidence_text="",
        )

    preferences_source = {"kind": "job_preferences", **asdict(prefs)}
    sources = job_sources(listings) + [preferences_source] if listings else []
    return PipelineResult(
        query=content,
        answer=format_job_answer(listings, prefs),
        has_evidence=bool(listings),
        sources=sources,
        evidence_text="",
    )


def _general_answer(content: str, kind: str) -> Any:
    from app.rag.pipeline import PipelineResult

    answer = {
        "greeting": GREETING_ANSWER,
        "capability": CAPABILITY_ANSWER,
        "off_topic": OFF_TOPIC_ANSWER,
        "injection": INJECTION_ANSWER,
    }[kind]
    return PipelineResult(
        query=content,
        answer=answer,
        has_evidence=True,
        sources=[],
        evidence_text="",
    )
