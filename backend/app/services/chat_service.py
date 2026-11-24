
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
    build_session_context,
    clarification_question,
    extract_preferences,
    fallback_role,
    format_company_answer,
    format_company_vacancy_answer,
    format_job_answer,
    is_career_info_question,
    is_company_hiring_query,
    is_company_listing_query,
    is_job_search,
    job_sources,
    _merge_list,
    missing_essential,
    _pending_job_search_missing,
    references_previous_companies,
    search_company_vacancies,
    search_hiring_companies,
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


def _is_pending_answer(content: str) -> bool:
    """A short answer to a pending clarification, not a fresh search request."""
    cleaned = (content or "").strip()
    if not cleaned or len(cleaned) > 120:
        return False
    if is_job_search(cleaned) or references_previous_companies(cleaned):
        return False
    if is_company_listing_query(cleaned) or is_career_info_question(cleaned):
        return False
    if "?" in cleaned:
        return False
    return True


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
    context = build_session_context(history)
    pending_missing = context.pending_missing
    career = kind == "career_info" or is_career_info_question(content)

    # Fixed answers and security refusals always win first.
    if kind in ("greeting", "capability", "injection", "off_topic"):
        result = _general_answer(content, kind)
    elif career:
        # Salary / career-path / role-comparison questions must never be
        # hijacked by a remembered job-search intent.
        logger.info("chat career-info intent=%s", kind)
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
    elif (
        kind == "job_search"
        or references_previous_companies(content)
        or (pending_missing and _is_pending_answer(content))
        or (
            bool(payload.job_search)
            and kind in ("general", "job_search")
            and not is_career_info_question(content)
        )
    ):
        result = await _run_job_search(
            content,
            payload.job_preferences,
            history=history,
            pending_missing=pending_missing,
            context=context,
        )
    else:
        blocked = False
        if kind == "general":
            context_text = context.summary_text()
            try:
                verdict = await classify_unclear_message(
                    content, context=context_text
                )
            except TypeError:
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
    context: Any = None,
) -> Any:
    from app.rag.pipeline import PipelineResult

    if context is None:
        context = build_session_context(history)

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
    # Server-side session context is authoritative; stored prefs only fill gaps.
    merged = base
    try:
        from app.services.job_search_service import SessionContext as _SC

        if not isinstance(context, _SC):
            context = build_session_context(history)
    except Exception:
        pass
    server_prefs = context.preferences if hasattr(context, "preferences") else JobPreferences()
    for field_name in preference_fields:
        server_value = getattr(server_prefs, field_name)
        client_value = getattr(merged, field_name)
        if field_name == "skills":
            if client_value and not server_value:
                server_value = client_value
            merged.skills = _merge_list(server_value, client_value) if server_value else list(client_value)
        elif server_value not in ("", None, False):
            setattr(merged, field_name, server_value)
        elif client_value not in ("", None, False):
            setattr(merged, field_name, client_value)
    base = merged

    if references_previous_companies(content):
        return await _run_company_vacancy_search(content, base, context)

    if is_company_hiring_query(content):
        return await _run_company_search(content, base, history, context)

    if is_company_listing_query(content):
        return await _run_company_listing_search(content, base, history, context)

    prefs = extract_preferences(content, base)

    # If a pending job-search question was answered, apply the answer to the
    # pending slot instead of asking the same question again.  A brand-new
    # job-search or follow-up request must never be mistaken for a short
    # answer to the old question.
    pending = (
        _pending_job_search_missing(history)
        if pending_missing is None
        else pending_missing
    )
    if pending and missing_essential(prefs) and _is_pending_answer(content):
        if pending == "role" and not prefs.role:
            prefs.role = re.sub(r"\s+", " ", content.strip()).strip("?.! ").strip()
        elif pending == "location" and not prefs.location and not prefs.remote:
            prefs.location = re.sub(r"\s+", " ", content.strip()).strip("?.! ").strip()

    missing = missing_essential(prefs)

    if not prefs.role and missing == "role" and is_job_search(content):
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

    search_meta = getattr(prefs, "search_meta", None) or {}
    answer = format_job_answer(listings, prefs)
    if search_meta.get("broader"):
        answer += (
            f"\n\nNote: fewer than 3 postings were found in "
            f"{search_meta.get('original_location') or 'that location'}, so I "
            f"broadened the search to {search_meta.get('used_location') or 'India'}."
        )

    preferences_source = {"kind": "job_preferences", **asdict(prefs)}
    sources = job_sources(listings) + [preferences_source] if listings else [preferences_source]
    if search_meta.get("broader"):
        sources.append({"kind": "job_search_scope", **search_meta})
    if not listings:
        sources.append({"kind": "job_search_no_results", "preferences": asdict(prefs)})
    return PipelineResult(
        query=content,
        answer=answer,
        has_evidence=bool(listings),
        sources=sources,
        evidence_text="",
    )


async def _run_company_search(
    content: str,
    prefs: JobPreferences,
    history: list[dict[str, Any]] | None = None,
    context: Any = None,
) -> Any:
    from app.rag.pipeline import PipelineResult

    prefs = extract_preferences(content, prefs)

    if not prefs.role:
        missing = missing_essential(prefs)
        if missing == "role":
            return PipelineResult(
                query=content,
                answer=clarification_question("role", prefs),
                has_evidence=False,
                sources=[
                    {
                        "kind": "job_search_prompt",
                        "missing": "role",
                        "preferences": asdict(prefs),
                    }
                ],
                evidence_text="",
            )
    if not prefs.location and not prefs.remote:
        prefs.location = "India"

    listings: list[dict[str, Any]] = []
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

    if not listings:
        try:
            listings = await search_hiring_companies(prefs)
        except TavilyError as exc:
            return PipelineResult(
                query=content,
                answer=str(exc),
                has_evidence=False,
                sources=[],
                evidence_text="",
            )

    preferences_source = {"kind": "job_preferences", **asdict(prefs)}
    sources = job_sources(listings) + [preferences_source] if listings else [preferences_source]
    return PipelineResult(
        query=content,
        answer=format_company_answer(listings, prefs),
        has_evidence=bool(listings),
        sources=sources,
        evidence_text="",
    )


async def _run_company_listing_search(
    content: str,
    prefs: JobPreferences,
    history: list[dict[str, Any]] | None = None,
    context: Any = None,
) -> Any:
    from app.rag.pipeline import PipelineResult

    prefs = extract_preferences(content, prefs)

    if not prefs.role:
        missing = missing_essential(prefs)
        if missing == "role":
            return PipelineResult(
                query=content,
                answer=clarification_question("role", prefs),
                has_evidence=False,
                sources=[
                    {
                        "kind": "job_search_prompt",
                        "missing": "role",
                        "preferences": asdict(prefs),
                    }
                ],
                evidence_text="",
            )
    if not prefs.location and not prefs.remote:
        prefs.location = "India"

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
    sources = job_sources(listings) + [preferences_source] if listings else [preferences_source]
    if not listings:
        sources.append({"kind": "job_search_no_results", "preferences": asdict(prefs)})
    return PipelineResult(
        query=content,
        answer=format_company_answer(listings, prefs),
        has_evidence=bool(listings),
        sources=sources,
        evidence_text="",
    )


async def _run_company_vacancy_search(
    content: str,
    prefs: JobPreferences,
    context: Any = None,
) -> Any:
    from app.rag.pipeline import PipelineResult

    prefs = extract_preferences(content, prefs)

    companies = getattr(context, "companies", []) or []
    if not companies:
        return PipelineResult(
            query=content,
            answer=(
                "I don't have a verified company list from earlier in this "
                "conversation, so I can't search vacancies for specific companies. "
                "Ask me to find jobs for a role first, or name the companies."
            ),
            has_evidence=False,
            sources=[
                {
                    "kind": "job_search_prompt",
                    "missing": "companies",
                    "preferences": asdict(prefs),
                }
            ],
            evidence_text="",
        )

    if not prefs.role:
        missing = missing_essential(prefs)
        if missing == "role":
            return PipelineResult(
                query=content,
                answer=clarification_question("role", prefs),
                has_evidence=False,
                sources=[
                    {
                        "kind": "job_search_prompt",
                        "missing": "role",
                        "preferences": asdict(prefs),
                    }
                ],
                evidence_text="",
            )
    if not prefs.location and not prefs.remote:
        prefs.location = "India"

    try:
        listings, coverage = await search_company_vacancies(prefs, companies)
    except TavilyError as exc:
        return PipelineResult(
            query=content,
            answer=str(exc),
            has_evidence=False,
            sources=[],
            evidence_text="",
        )

    preferences_source = {"kind": "job_preferences", **asdict(prefs)}
    sources = job_sources(listings) + [preferences_source]
    sources.append({"kind": "company_vacancy_coverage", **coverage})
    if not listings:
        sources.append({"kind": "job_search_no_results", "preferences": asdict(prefs)})
    return PipelineResult(
        query=content,
        answer=format_company_vacancy_answer(listings, prefs, coverage),
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
