"""Parameterized SQL for persisted interview scheduling.

Every read/write is scoped to ``user_id`` so records are only visible to the
authenticated owner.  Overlap checks use UTC instants (``starts_at``/``ends_at``).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

SCHEDULED_BASE_COLUMNS = (
    "id, user_id, candidate_id, title, interview_date, start_time, "
    "end_time, starts_at, ends_at, duration_minutes, interview_type, "
    "meeting_link, location, notes, status, time_zone, created_at, updated_at, "
    "recruiter_email, confirmation_email_status, confirmation_email_sent_at, "
    "confirmation_email_attempts"
)

SCHEDULED_COLUMNS = (
    "si.id, si.user_id, si.candidate_id, si.title, si.interview_date, si.start_time, "
    "si.end_time, si.starts_at, si.ends_at, si.duration_minutes, si.interview_type, "
    "si.meeting_link, si.location, si.notes, si.status, si.time_zone, "
    "si.created_at, si.updated_at, si.recruiter_email, "
    "si.confirmation_email_status, si.confirmation_email_recipient, "
    "si.confirmation_email_sent_at, si.confirmation_email_attempts, "
    "si.candidate_response, si.response_at, si.decline_reason, "
    "si.reschedule_requested_date, si.reschedule_requested_start_time, "
    "si.reschedule_reason, si.reschedule_status, si.reschedule_decided_at, "
    "c.full_name AS candidate_name, c.email AS candidate_email"
)

UPDATE_FIELDS = (
    "title",
    "interview_date",
    "start_time",
    "end_time",
    "starts_at",
    "ends_at",
    "duration_minutes",
    "interview_type",
    "meeting_link",
    "location",
    "notes",
    "status",
    "time_zone",
)


def lock_slots(connection, keys: list[str]) -> None:
    """Serialize bookings that share a candidate or interviewer.

    Transaction-level advisory locks are released automatically on commit or
    rollback, so concurrent requests cannot both pass the overlap check.
    """
    for key in sorted(set(keys)):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))


def create_interview(connection, values: dict[str, Any]) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO scheduled_interviews (
                user_id, candidate_id, title, interview_date, start_time, end_time,
                starts_at, ends_at, duration_minutes, interview_type, meeting_link,
                location, notes, status, time_zone, recruiter_email,
                confirmation_email_status, confirmation_email_recipient
            ) VALUES (
                %(user_id)s, %(candidate_id)s, %(title)s, %(interview_date)s,
                %(start_time)s, %(end_time)s, %(starts_at)s, %(ends_at)s,
                %(duration_minutes)s, %(interview_type)s, %(meeting_link)s,
                %(location)s, %(notes)s, 'scheduled', %(time_zone)s,
                %(recruiter_email)s, %(confirmation_email_status)s,
                %(confirmation_email_recipient)s
            )
            RETURNING {SCHEDULED_BASE_COLUMNS}
            """,
            values,
        )
        return cursor.fetchone()


def list_interviews(
    connection,
    user_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    clauses = ["si.user_id = %s"]
    params: list[Any] = [user_id]
    if date_from is not None:
        clauses.append("si.interview_date >= %s")
        params.append(date_from)
    if date_to is not None:
        clauses.append("si.interview_date <= %s")
        params.append(date_to)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {SCHEDULED_COLUMNS}
            FROM scheduled_interviews si
            JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = si.user_id
            WHERE {' AND '.join(clauses)}
            ORDER BY si.starts_at ASC, si.id ASC
            """,
            tuple(params),
        )
        return list(cursor.fetchall())


def get_interview(connection, user_id: str, interview_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {SCHEDULED_COLUMNS}
            FROM scheduled_interviews si
            JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = si.user_id
            WHERE si.id = %s AND si.user_id = %s
            """,
            (interview_id, user_id),
        )
        return cursor.fetchone()


def find_overlap(
    connection,
    *,
    candidate_id: str,
    user_id: str,
    starts_at: datetime,
    ends_at: datetime,
    exclude_id: str | None = None,
) -> dict[str, Any] | None:
    clauses = [
        "status <> 'cancelled'",
        "(candidate_id = %s OR user_id = %s)",
        "starts_at < %s",
        "ends_at > %s",
    ]
    params: list[Any] = [candidate_id, user_id, ends_at, starts_at]
    if exclude_id:
        clauses.append("id <> %s")
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, title, starts_at, ends_at FROM scheduled_interviews WHERE {' AND '.join(clauses)} LIMIT 1",
            tuple(params),
        )
        return cursor.fetchone()


def update_interview(
    connection,
    user_id: str,
    interview_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    if not updates:
        return get_interview(connection, user_id, interview_id)
    assignments = ", ".join(f"{field} = %s" for field in updates if field in UPDATE_FIELDS)
    if not assignments:
        return get_interview(connection, user_id, interview_id)
    params = [updates[field] for field in UPDATE_FIELDS if field in updates]
    params.extend([interview_id, user_id])
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE scheduled_interviews
            SET {assignments}
            WHERE id = %s AND user_id = %s
            RETURNING {SCHEDULED_BASE_COLUMNS}
            """,
            tuple(params),
        )
        return cursor.fetchone()


def availability(
    connection,
    user_id: str,
    candidate_id: str,
    day: date,
) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT to_char(start_time, 'HH24:MI') AS slot
            FROM scheduled_interviews
            WHERE user_id = %s
              AND status <> 'cancelled'
              AND interview_date = %s
              AND (candidate_id = %s OR user_id = %s)
            ORDER BY start_time
            """,
            (user_id, day, candidate_id, user_id),
        )
        return [row["slot"] for row in cursor.fetchall()]


def recover_stale_confirmations(connection, timeout_minutes: int) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE scheduled_interviews
            SET confirmation_email_status = 'pending'
            WHERE confirmation_email_status = 'sending'
              AND (confirmation_email_claimed_at IS NULL
                   OR confirmation_email_claimed_at < now() - (%s * interval '1 minute'))
            """,
            (timeout_minutes,),
        )
        return int(cursor.rowcount or 0)


def claim_confirmations(
    connection,
    *,
    retry_delay_minutes: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Atomically claim candidate confirmations for delivery."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("interview-confirmation-email-dispatcher",),
        )
        cursor.execute(
            f"""
            SELECT {SCHEDULED_COLUMNS}
            FROM scheduled_interviews si
            JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = si.user_id
            WHERE si.status <> 'cancelled'
              AND si.confirmation_email_status IN ('pending', 'failed')
              AND si.confirmation_email_recipient IS NOT NULL
              AND (si.confirmation_email_next_attempt_at IS NULL
                   OR si.confirmation_email_next_attempt_at <= now())
            ORDER BY si.starts_at
            LIMIT %s
            FOR UPDATE OF si SKIP LOCKED
            """,
            (limit,),
        )
        rows = list(cursor.fetchall())
        if rows:
            ids = [row["id"] for row in rows]
            cursor.execute(
                """
                UPDATE scheduled_interviews
                SET confirmation_email_status = 'sending',
                    confirmation_email_claimed_at = now(),
                    confirmation_email_attempts = confirmation_email_attempts + 1
                WHERE id = ANY(%s)
                  AND confirmation_email_status IN ('pending', 'failed')
                """,
                (ids,),
            )
        return rows


def mark_confirmation_sent(connection, interview_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE scheduled_interviews
            SET confirmation_email_status = 'sent',
                confirmation_email_sent_at = now(),
                confirmation_email_last_error = NULL,
                confirmation_email_next_attempt_at = NULL
            WHERE id = %s AND confirmation_email_status = 'sending'
            """,
            (interview_id,),
        )
        return cursor.rowcount > 0


def mark_confirmation_failed(
    connection, interview_id: str, error: str, retry_delay_minutes: int
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE scheduled_interviews
            SET confirmation_email_status = 'failed',
                confirmation_email_last_error = %s,
                confirmation_email_next_attempt_at = now() + (%s * interval '1 minute')
            WHERE id = %s AND confirmation_email_status = 'sending'
            """,
            (error[:500], retry_delay_minutes, interview_id),
        )
        return cursor.rowcount > 0


def get_interview_for_candidate_email(connection, candidate_email: str, interview_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {SCHEDULED_COLUMNS} FROM scheduled_interviews si "
            "JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = si.user_id "
            "WHERE si.id = %s AND c.email = %s",
            (interview_id, candidate_email),
        )
        return cursor.fetchone()


def list_interviews_for_candidate_email(connection, candidate_email: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {SCHEDULED_COLUMNS} FROM scheduled_interviews si "
            "JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = si.user_id "
            "WHERE c.email = %s ORDER BY si.starts_at ASC",
            (candidate_email,),
        )
        return cursor.fetchall()
