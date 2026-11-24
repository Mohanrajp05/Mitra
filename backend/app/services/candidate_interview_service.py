"""Candidate-side interview responses (Phase 3)."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from app.database import scheduling_queries
from app.database.connection import get_connection
from app.services import candidate_portal_service


def _candidate_email(user_id: str) -> str | None:
    profile = candidate_portal_service.get_profile(user_id)
    if profile is None:
        return None
    email = (profile.get("email") or "").strip()
    return email or None


def list_my_interviews(user_id: str) -> list[dict[str, Any]]:
    email = _candidate_email(user_id)
    if not email:
        return []
    with get_connection() as connection:
        return scheduling_queries.list_interviews_for_candidate_email(connection, email)


def _get_owned(user_id: str, interview_id: str) -> dict[str, Any] | None:
    email = _candidate_email(user_id)
    if not email:
        return None
    with get_connection() as connection:
        return scheduling_queries.get_interview_for_candidate_email(connection, email, interview_id)


def accept(user_id: str, interview_id: str) -> dict[str, Any] | None:
    row = _get_owned(user_id, interview_id)
    if row is None or row.get("status") != "scheduled":
        return None
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE scheduled_interviews SET candidate_response='accepted', response_at=now(), updated_at=now() WHERE id=%s",
                (interview_id,),
            )
        connection.commit()
        return scheduling_queries.get_interview_for_candidate_email(connection, _candidate_email(user_id), interview_id)


def decline(user_id: str, interview_id: str, reason: str | None = None) -> dict[str, Any] | None:
    row = _get_owned(user_id, interview_id)
    if row is None or row.get("status") != "scheduled":
        return None
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE scheduled_interviews SET candidate_response='declined', response_at=now(), decline_reason=%s, updated_at=now() WHERE id=%s",
                (reason, interview_id),
            )
        connection.commit()
        return scheduling_queries.get_interview_for_candidate_email(connection, _candidate_email(user_id), interview_id)


def request_reschedule(user_id: str, interview_id: str, suggested_date: date, suggested_start_time: time, reason: str | None = None) -> dict[str, Any] | None:
    row = _get_owned(user_id, interview_id)
    if row is None or row.get("status") != "scheduled":
        return None
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE scheduled_interviews SET candidate_response='reschedule_requested', response_at=now(), "
                "reschedule_requested_date=%s, reschedule_requested_start_time=%s, reschedule_reason=%s, "
                "reschedule_status='pending', updated_at=now() WHERE id=%s",
                (suggested_date, suggested_start_time, reason, interview_id),
            )
        connection.commit()
        return scheduling_queries.get_interview_for_candidate_email(connection, _candidate_email(user_id), interview_id)
