"""Queries for two-way messaging."""

from __future__ import annotations

from typing import Any


def create_or_get_conversation(connection, recruiter_user_id: str, candidate_id: str, application_id: str | None) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversations (recruiter_user_id, candidate_id, application_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (recruiter_user_id, candidate_id, application_id) DO NOTHING
            RETURNING id, recruiter_user_id, candidate_id, application_id, created_at, updated_at
            """,
            (recruiter_user_id, candidate_id, application_id),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "SELECT id, recruiter_user_id, candidate_id, application_id, created_at, updated_at FROM conversations "
                "WHERE recruiter_user_id=%s AND candidate_id=%s AND application_id IS NOT DISTINCT FROM %s",
                (recruiter_user_id, candidate_id, application_id),
            )
            row = cursor.fetchone()
    return row


def list_for_recruiter(connection, recruiter_user_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, c.recruiter_user_id, c.candidate_id, c.application_id, c.created_at, c.updated_at,
                   cand.full_name AS candidate_name, cand.email AS candidate_email,
                   j.title AS job_title,
                   (SELECT m.content FROM messages m WHERE m.conversation_id = c.id ORDER BY m.sent_at DESC LIMIT 1) AS last_message,
                   (SELECT m.sent_at FROM messages m WHERE m.conversation_id = c.id ORDER BY m.sent_at DESC LIMIT 1) AS last_message_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id AND m.sender_role = 'candidate' AND m.read_at IS NULL) AS unread_count
            FROM conversations c
            JOIN candidates cand ON cand.id = c.candidate_id
            LEFT JOIN applications a ON a.id = c.application_id
            LEFT JOIN jobs j ON j.id = a.job_id
            WHERE c.recruiter_user_id = %s
            ORDER BY c.updated_at DESC
            """,
            (recruiter_user_id,),
        )
        return cursor.fetchall()


def list_for_candidate(connection, candidate_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, c.recruiter_user_id, c.candidate_id, c.application_id, c.created_at, c.updated_at,
                   cand.full_name AS candidate_name,
                   j.title AS job_title,
                   (SELECT m.content FROM messages m WHERE m.conversation_id = c.id ORDER BY m.sent_at DESC LIMIT 1) AS last_message,
                   (SELECT m.sent_at FROM messages m WHERE m.conversation_id = c.id ORDER BY m.sent_at DESC LIMIT 1) AS last_message_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id AND m.sender_role = 'recruiter' AND m.read_at IS NULL) AS unread_count
            FROM conversations c
            JOIN candidates cand ON cand.id = c.candidate_id
            LEFT JOIN applications a ON a.id = c.application_id
            LEFT JOIN jobs j ON j.id = a.job_id
            WHERE c.candidate_id = %s
            ORDER BY c.updated_at DESC
            """,
            (candidate_id,),
        )
        return cursor.fetchall()


def get_conversation(connection, conversation_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, recruiter_user_id, candidate_id, application_id, created_at, updated_at FROM conversations WHERE id=%s",
            (conversation_id,),
        )
        return cursor.fetchone()


def list_messages(connection, conversation_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, conversation_id, sender_user_id, sender_role, content, sent_at, read_at FROM messages WHERE conversation_id=%s ORDER BY sent_at ASC",
            (conversation_id,),
        )
        return cursor.fetchall()


def add_message(connection, conversation_id: str, sender_user_id: str, sender_role: str, content: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO messages (conversation_id, sender_user_id, sender_role, content) VALUES (%s,%s,%s,%s) RETURNING id, conversation_id, sender_user_id, sender_role, content, sent_at, read_at",
            (conversation_id, sender_user_id, sender_role, content),
        )
        row = cursor.fetchone()
        cursor.execute("UPDATE conversations SET updated_at=now() WHERE id=%s", (conversation_id,))
    return row


def mark_read(connection, conversation_id: str, reader_role: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE messages SET read_at=now() WHERE conversation_id=%s AND sender_role<>%s AND read_at IS NULL",
            (conversation_id, reader_role),
        )


def unread_count(connection, conversation_id: str, reader_role: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id=%s AND sender_role<>%s AND read_at IS NULL",
            (conversation_id, reader_role),
        )
        row = cursor.fetchone()
    return int((row.get("n") if isinstance(row, dict) else row[0]) or 0)
