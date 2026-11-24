"""Two-way messaging service (Phase 4)."""

from __future__ import annotations

from typing import Any

from app.database import messaging_queries
from app.database.connection import get_connection
from app.services import candidate_portal_service


def _candidate_id(user_id: str) -> str | None:
    profile = candidate_portal_service.get_profile(user_id)
    if profile is None:
        return None
    return str(profile.get("id"))


def _is_candidate(user_id: str) -> bool:
    return candidate_portal_service.is_candidate(user_id)


def list_conversations(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        if _is_candidate(user_id):
            cid = _candidate_id(user_id)
            if cid is None:
                return []
            return messaging_queries.list_for_candidate(connection, cid)
        return messaging_queries.list_for_recruiter(connection, user_id)


def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        conv = messaging_queries.get_conversation(connection, conversation_id)
    if conv is None:
        return None
    if _is_candidate(user_id):
        if str(conv.get("candidate_id")) != (_candidate_id(user_id) or ""):
            return None
    else:
        if str(conv.get("recruiter_user_id")) != user_id:
            return None
    return conv


def list_messages(user_id: str, conversation_id: str) -> list[dict[str, Any]] | None:
    conv = get_conversation(user_id, conversation_id)
    if conv is None:
        return None
    with get_connection() as connection:
        msgs = messaging_queries.list_messages(connection, conversation_id)
        messaging_queries.mark_read(connection, conversation_id, "candidate" if _is_candidate(user_id) else "recruiter")
        connection.commit()
    return msgs


def send_message(user_id: str, conversation_id: str, content: str) -> dict[str, Any] | None:
    conv = get_conversation(user_id, conversation_id)
    if conv is None:
        return None
    role = "candidate" if _is_candidate(user_id) else "recruiter"
    with get_connection() as connection:
        msg = messaging_queries.add_message(connection, conversation_id, user_id, role, content)
        connection.commit()
    return msg


def start_or_get_conversation(recruiter_user_id: str, candidate_id: str, application_id: str | None) -> dict[str, Any] | None:
    # validate candidate belongs to recruiter
    from app.database import queries
    with get_connection() as connection:
        cand = queries.get_candidate(connection, recruiter_user_id, candidate_id)
        if cand is None:
            return None
        conv = messaging_queries.create_or_get_conversation(connection, recruiter_user_id, candidate_id, application_id)
        connection.commit()
    return conv
