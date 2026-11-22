"""Interview scheduling service.

Ownership is always derived from the authenticated user.  Candidate IDs are
validated against the authenticated owner's records before any write.  Slots
are validated against the real current time in the recruiter's configured time
zone, and overlapping bookings are rejected both in the service (under advisory
transaction locks) and by partial unique indexes in the database.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from psycopg.errors import UniqueViolation

from app.database import scheduling_queries
from app.database.connection import get_connection
from app.schemas.scheduling import ScheduledInterviewCreate, ScheduledInterviewUpdate
from app.services import candidate_service, email_service, reminder_service

logger = logging.getLogger(__name__)

DURATION_MINUTES = 30


class SchedulingError(RuntimeError):
    pass


class SchedulingValidationError(SchedulingError):
    pass


class SchedulingConflictError(SchedulingError):
    pass


class SchedulingNotFoundError(SchedulingError):
    pass


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise SchedulingValidationError(f"Unknown time zone: {name}") from exc


def _time_window(
    interview_date: date,
    start_time: time,
    duration_minutes: int,
    time_zone: str,
) -> tuple[datetime, datetime, time]:
    zone = _zone(time_zone)
    local_start = datetime.combine(interview_date, start_time, tzinfo=zone)
    starts_at = local_start.astimezone(timezone.utc)
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    local_end = (local_start + timedelta(minutes=duration_minutes)).time().replace(tzinfo=None)
    return starts_at, ends_at, local_end


def _validate_future(starts_at: datetime) -> None:
    if starts_at <= datetime.now(timezone.utc):
        raise SchedulingValidationError(
            "That time has already passed. Choose a future date or a later time slot."
        )


def _validate_contact_fields(interview_type: str, meeting_link, location) -> None:
    if interview_type == "online" and not (meeting_link or "").strip():
        raise SchedulingValidationError("A meeting link is required for an online interview.")
    if interview_type == "in_person" and not (location or "").strip():
        raise SchedulingValidationError("A location is required for an in-person interview.")


def _owned_candidate(user_id: str, candidate_id: str) -> dict[str, Any]:
    candidate = candidate_service.get_candidate(user_id, candidate_id)
    if candidate is None:
        raise SchedulingNotFoundError("Candidate not found.")
    return candidate


def _with_candidate_info(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return row


def create_interview(
    user_id: str, payload: ScheduledInterviewCreate, recruiter_email: str | None = None
) -> dict[str, Any]:
    candidate = _owned_candidate(user_id, payload.candidate_id)
    title = (payload.title or "").strip() or f"Interview with {candidate.get('full_name') or 'candidate'}"
    _validate_contact_fields(payload.interview_type, payload.meeting_link, payload.location)
    starts_at, ends_at, end_time = _time_window(
        payload.interview_date,
        payload.start_time,
        payload.duration_minutes,
        payload.time_zone,
    )
    _validate_future(starts_at)

    candidate_email = (candidate.get("email") or "").strip() or None
    values = {
        "user_id": user_id,
        "candidate_id": str(candidate["id"]),
        "title": title,
        "interview_date": payload.interview_date,
        "start_time": payload.start_time,
        "end_time": end_time,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "duration_minutes": payload.duration_minutes,
        "interview_type": payload.interview_type,
        "meeting_link": payload.meeting_link,
        "location": payload.location,
        "notes": payload.notes,
        "time_zone": payload.time_zone,
        "recruiter_email": (recruiter_email or "").strip() or None,
        "confirmation_email_status": "pending" if candidate_email else "none",
        "confirmation_email_recipient": candidate_email,
    }

    with get_connection() as connection:
        scheduling_queries.lock_slots(connection, [f"user:{user_id}", f"candidate:{values['candidate_id']}"])
        overlap = scheduling_queries.find_overlap(
            connection,
            candidate_id=values["candidate_id"],
            user_id=user_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        if overlap is not None:
            raise SchedulingConflictError(
                "This slot conflicts with an existing interview for this candidate or interviewer."
            )
        try:
            inserted = scheduling_queries.create_interview(connection, values)
        except UniqueViolation as exc:
            raise SchedulingConflictError("This interview slot is already booked.") from exc
        row = scheduling_queries.get_interview(connection, user_id, str(inserted["id"]))
    reminder_service.generate_for_interview(user_id, row, recruiter_email)
    # Best-effort immediate confirmation; failures are tracked for safe retry
    # by the scheduler and never roll back the saved interview.
    try:
        email_service.send_pending_confirmations()
    except Exception as exc:  # noqa: BLE001 - interview is already saved
        logger.warning("Candidate confirmation dispatch failed: %s", type(exc).__name__)
    return row


def list_interviews(
    user_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    with get_connection() as connection:
        return scheduling_queries.list_interviews(
            connection, user_id, date_from=date_from, date_to=date_to
        )


def get_interview(user_id: str, interview_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        row = scheduling_queries.get_interview(connection, user_id, interview_id)
    if row is None:
        raise SchedulingNotFoundError("Interview not found.")
    return row


def availability(user_id: str, candidate_id: str, day: date) -> dict[str, Any]:
    _owned_candidate(user_id, candidate_id)
    with get_connection() as connection:
        slots = scheduling_queries.availability(connection, user_id, candidate_id, day)
    return {"candidate_id": candidate_id, "interview_date": day, "booked_slots": slots}


def update_interview(
    user_id: str,
    interview_id: str,
    payload: ScheduledInterviewUpdate,
    recruiter_email: str | None = None,
) -> dict[str, Any]:
    with get_connection() as connection:
        current = scheduling_queries.get_interview(connection, user_id, interview_id)
    if current is None:
        raise SchedulingNotFoundError("Interview not found.")

    updates: dict[str, Any] = {}
    data = payload.model_dump(exclude_unset=True)
    rescheduling = any(key in data for key in ("interview_date", "start_time", "time_zone"))
    if rescheduling and current.get("status") != "scheduled":
        raise SchedulingValidationError("Only upcoming interviews can be rescheduled.")

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise SchedulingValidationError("Interview title must not be empty.")
        updates["title"] = title

    interview_type = data.get("interview_type", current.get("interview_type"))
    meeting_link = data.get("meeting_link", current.get("meeting_link"))
    location = data.get("location", current.get("location"))
    _validate_contact_fields(interview_type, meeting_link, location)
    for field in ("interview_type", "meeting_link", "location", "notes", "status"):
        if field in data:
            updates[field] = data[field]

    if rescheduling:
        day = data.get("interview_date", current["interview_date"])
        start = data.get("start_time", current["start_time"])
        zone_name = data.get("time_zone", current.get("time_zone") or "UTC")
        duration = int(current.get("duration_minutes") or DURATION_MINUTES)
        starts_at, ends_at, end_time = _time_window(day, start, duration, zone_name)
        _validate_future(starts_at)
        updates.update(
            interview_date=day,
            start_time=start,
            end_time=end_time,
            starts_at=starts_at,
            ends_at=ends_at,
            time_zone=zone_name,
        )
        with get_connection() as connection:
            scheduling_queries.lock_slots(
                connection,
                [f"user:{user_id}", f"candidate:{current['candidate_id']}"],
            )
            overlap = scheduling_queries.find_overlap(
                connection,
                candidate_id=current["candidate_id"],
                user_id=user_id,
                starts_at=starts_at,
                ends_at=ends_at,
                exclude_id=interview_id,
            )
            if overlap is not None:
                raise SchedulingConflictError(
                    "This slot conflicts with an existing interview for this candidate or interviewer."
                )
            try:
                scheduling_queries.update_interview(connection, user_id, interview_id, updates)
            except UniqueViolation as exc:
                raise SchedulingConflictError("This interview slot is already booked.") from exc
    else:
        with get_connection() as connection:
            scheduling_queries.update_interview(connection, user_id, interview_id, updates)

    updated = get_interview(user_id, interview_id)
    if rescheduling:
        reminder_service.regenerate_for_interview(user_id, updated, recruiter_email)
    elif data.get("status") in {"cancelled", "completed", "missed"}:
        reminder_service.cancel_for_interview(user_id, interview_id)
    return updated
