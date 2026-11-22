"""Interview reminder generation, delivery and notification access.

Reminder rows are the in-app notifications: they become visible to the user
once the scheduler claims a due row and moves it from ``pending`` to ``sent``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import reminder_queries
from app.database.connection import get_connection

REMINDER_OFFSETS = (
    ("24_hour", timedelta(hours=24), "24 hours"),
    ("1_hour", timedelta(hours=1), "1 hour"),
)


class ReminderError(RuntimeError):
    pass


class ReminderNotFoundError(ReminderError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value))


def generate_for_interview(
    user_id: str, interview: dict[str, Any], recruiter_email: str | None = None
) -> int:
    """Create both applicable reminders; expire past ones are skipped."""
    starts_at = _as_utc(interview["starts_at"])
    candidate = interview.get("candidate_name") or "your candidate"
    date_text = str(interview.get("interview_date") or "")
    time_text = str(interview.get("start_time") or "")[:5]
    recipient = (recruiter_email or "").strip() or None
    email_status = "pending" if recipient else "none"

    created = 0
    with get_connection() as connection:
        for kind, offset, label in REMINDER_OFFSETS:
            scheduled_at = starts_at - offset
            if scheduled_at <= utcnow():
                continue
            inserted = reminder_queries.insert_reminder(
                connection,
                {
                    "user_id": user_id,
                    "interview_id": str(interview["id"]),
                    "notification_type": kind,
                    "title": f"Interview reminder: {candidate}",
                    "message": (
                        f"This is your {label} reminder for the interview with {candidate} "
                        f"on {date_text} at {time_text}."
                    ),
                    "scheduled_at": scheduled_at,
                    "recipient_email": recipient,
                    "email_status": email_status,
                },
            )
            created += int(inserted)
    return created


def regenerate_for_interview(
    user_id: str, interview: dict[str, Any], recruiter_email: str | None = None
) -> int:
    with get_connection() as connection:
        reminder_queries.cancel_pending(connection, user_id, str(interview["id"]))
    return generate_for_interview(user_id, interview, recruiter_email)


def cancel_for_interview(user_id: str, interview_id: str) -> int:
    with get_connection() as connection:
        return reminder_queries.cancel_pending(connection, user_id, str(interview_id))


def process_due_reminders(limit: int = 50) -> list[dict[str, Any]]:
    """Claim due reminders exactly once and mark them as sent."""
    with get_connection() as connection:
        return reminder_queries.claim_due(connection, limit)


def list_notifications(user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as connection:
        return reminder_queries.list_for_user(connection, user_id, limit)


def unread_count(user_id: str) -> int:
    with get_connection() as connection:
        return reminder_queries.unread_count(connection, user_id)


def mark_read(user_id: str, reminder_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        row = reminder_queries.mark_read(connection, user_id, reminder_id)
    if row is None:
        raise ReminderNotFoundError("Notification not found.")
    return row


def mark_all_read(user_id: str) -> int:
    with get_connection() as connection:
        return reminder_queries.mark_all_read(connection, user_id)
