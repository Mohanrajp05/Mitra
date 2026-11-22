"""Parameterized SQL for in-app interview reminders/notifications.

Every read and write is scoped to ``user_id``.  Due reminders are claimed with
a transaction-level advisory lock plus ``FOR UPDATE SKIP LOCKED`` so multiple
application workers can never process the same reminder twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

REMINDER_BASE_COLUMNS = (
    "id, user_id, interview_id, notification_type, title, message, "
    "scheduled_at, status, created_at, read_at, recipient_email, email_status, "
    "email_sent_at, email_last_error, email_attempts"
)

REMINDER_COLUMNS = (
    "r.id, r.user_id, r.interview_id, r.notification_type, r.title, r.message, "
    "r.scheduled_at, r.status, r.created_at, r.read_at, r.recipient_email, "
    "r.email_status, r.email_sent_at, r.email_last_error, r.email_attempts, "
    "si.interview_date, si.start_time, c.full_name AS candidate_name"
)

DISPATCH_LOCK_KEY = "interview-reminder-dispatcher"


def insert_reminder(connection, values: dict[str, Any]) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO interview_reminders (
                user_id, interview_id, notification_type, title, message,
                scheduled_at, status, recipient_email, email_status
            ) VALUES (
                %(user_id)s, %(interview_id)s, %(notification_type)s, %(title)s,
                %(message)s, %(scheduled_at)s, 'pending',
                %(recipient_email)s, %(email_status)s
            )
            ON CONFLICT (interview_id, notification_type)
                WHERE status <> 'cancelled'
            DO NOTHING
            """,
            values,
        )
        return cursor.rowcount > 0


def cancel_pending(connection, user_id: str, interview_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interview_reminders
            SET status = 'cancelled'
            WHERE user_id = %s AND interview_id = %s AND status = 'pending'
            """,
            (user_id, interview_id),
        )
        return int(cursor.rowcount or 0)


def list_for_user(connection, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {REMINDER_COLUMNS}
            FROM interview_reminders r
            JOIN scheduled_interviews si ON si.id = r.interview_id AND si.user_id = r.user_id
            JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = r.user_id
            WHERE r.user_id = %s AND r.status IN ('sent', 'read')
            ORDER BY r.scheduled_at DESC, r.created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return list(cursor.fetchall())


def unread_count(connection, user_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) AS total FROM interview_reminders WHERE user_id = %s AND status = 'sent'",
            (user_id,),
        )
        row = cursor.fetchone()
    if isinstance(row, dict):
        return int(row.get("total") or 0)
    return int(row[0]) if row else 0


def mark_read(connection, user_id: str, reminder_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE interview_reminders
            SET status = 'read', read_at = now()
            WHERE id = %s AND user_id = %s AND status = 'sent'
            RETURNING {REMINDER_BASE_COLUMNS}
            """,
            (reminder_id, user_id),
        )
        return cursor.fetchone()


def mark_all_read(connection, user_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interview_reminders
            SET status = 'read', read_at = now()
            WHERE user_id = %s AND status = 'sent'
            """,
            (user_id,),
        )
        return int(cursor.rowcount or 0)


def claim_due(connection, limit: int = 50) -> list[dict[str, Any]]:
    """Atomically claim and mark due reminders as sent (one worker wins)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (DISPATCH_LOCK_KEY,),
        )
        cursor.execute(
            f"""
            SELECT {REMINDER_COLUMNS}
            FROM interview_reminders r
            JOIN scheduled_interviews si ON si.id = r.interview_id AND si.user_id = r.user_id
            JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = r.user_id
            WHERE r.status = 'pending' AND r.scheduled_at <= now()
            ORDER BY r.scheduled_at
            LIMIT %s
            FOR UPDATE OF r SKIP LOCKED
            """,
            (limit,),
        )
        rows = list(cursor.fetchall())
        if rows:
            ids = [row["id"] for row in rows]
            cursor.execute(
                """
                UPDATE interview_reminders
                SET status = 'sent'
                WHERE id = ANY(%s) AND status = 'pending'
                """,
                (ids,),
            )
        return rows


def recover_stale_sending(connection, timeout_minutes: int) -> int:
    """Return rows stuck in 'sending' after a worker crash to the queue."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interview_reminders
            SET email_status = 'pending'
            WHERE email_status = 'sending'
              AND (email_claimed_at IS NULL
                   OR email_claimed_at < now() - (%s * interval '1 minute'))
            """,
            (timeout_minutes,),
        )
        return int(cursor.rowcount or 0)


def claim_emails(
    connection,
    *,
    retry_delay_minutes: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Atomically claim emails for already-created in-app notifications."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("interview-reminder-email-dispatcher",),
        )
        cursor.execute(
            f"""
            SELECT {REMINDER_COLUMNS}
            FROM interview_reminders r
            JOIN scheduled_interviews si ON si.id = r.interview_id AND si.user_id = r.user_id
            JOIN candidates c ON c.id = si.candidate_id AND c.owner_user_id = r.user_id
            WHERE r.status IN ('sent', 'read')
              AND r.email_status IN ('pending', 'failed')
              AND r.recipient_email IS NOT NULL
              AND (r.email_next_attempt_at IS NULL OR r.email_next_attempt_at <= now())
            ORDER BY r.scheduled_at
            LIMIT %s
            FOR UPDATE OF r SKIP LOCKED
            """,
            (limit,),
        )
        rows = list(cursor.fetchall())
        if rows:
            ids = [row["id"] for row in rows]
            cursor.execute(
                """
                UPDATE interview_reminders
                SET email_status = 'sending', email_claimed_at = now(),
                    email_attempts = email_attempts + 1
                WHERE id = ANY(%s) AND email_status IN ('pending', 'failed')
                """,
                (ids,),
            )
        return rows


def mark_email_sent(connection, reminder_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interview_reminders
            SET email_status = 'sent', email_sent_at = now(),
                email_last_error = NULL, email_next_attempt_at = NULL
            WHERE id = %s AND email_status = 'sending'
            """,
            (reminder_id,),
        )
        return cursor.rowcount > 0


def mark_email_failed(
    connection, reminder_id: str, error: str, retry_delay_minutes: int
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interview_reminders
            SET email_status = 'failed', email_last_error = %s,
                email_next_attempt_at = now() + (%s * interval '1 minute')
            WHERE id = %s AND email_status = 'sending'
            """,
            (error[:500], retry_delay_minutes, reminder_id),
        )
        return cursor.rowcount > 0
