"""Parameterized SQL queries for chat sessions and messages.

Every query filters by ``owner_user_id`` so a session or message is only
visible to the authenticated recruiter who owns it.
"""

from typing import Any

from psycopg.types.json import Jsonb

CHAT_SESSION_COLUMNS = "id, owner_user_id, title, created_at, updated_at"

CHAT_MESSAGE_COLUMNS = (
    "id, session_id, owner_user_id, role, content, sources, has_evidence, "
    "created_at"
)


def list_sessions(connection, owner_user_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CHAT_SESSION_COLUMNS} FROM chat_sessions "
            "WHERE owner_user_id = %s ORDER BY updated_at DESC, created_at DESC",
            (owner_user_id,),
        )
        return cursor.fetchall()


def get_session(
    connection, owner_user_id: str, session_id: str
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CHAT_SESSION_COLUMNS} FROM chat_sessions "
            "WHERE id = %s AND owner_user_id = %s",
            (session_id, owner_user_id),
        )
        return cursor.fetchone()


def create_session(
    connection, owner_user_id: str, title: str
) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO chat_sessions (owner_user_id, title) "
            f"VALUES (%s, %s) RETURNING {CHAT_SESSION_COLUMNS}",
            (owner_user_id, title),
        )
        return cursor.fetchone()


def rename_session(
    connection, owner_user_id: str, session_id: str, title: str
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE chat_sessions SET title = %s "
            f"WHERE id = %s AND owner_user_id = %s "
            f"RETURNING {CHAT_SESSION_COLUMNS}",
            (title, session_id, owner_user_id),
        )
        return cursor.fetchone()


def delete_session(connection, owner_user_id: str, session_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM chat_sessions "
            "WHERE id = %s AND owner_user_id = %s RETURNING id",
            (session_id, owner_user_id),
        )
        return cursor.fetchone() is not None


def delete_all_sessions(connection, owner_user_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM chat_sessions WHERE owner_user_id = %s RETURNING id",
            (owner_user_id,),
        )
        return len(cursor.fetchall())


def delete_expired_messages(connection, owner_user_id: str, older_than: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM chat_messages "
            "WHERE owner_user_id = %s AND created_at < %s RETURNING id",
            (owner_user_id, older_than),
        )
        return len(cursor.fetchall())


def count_expired_messages(connection, owner_user_id: str, older_than: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM chat_messages "
            "WHERE owner_user_id = %s AND created_at < %s",
            (owner_user_id, older_than),
        )
        return len(cursor.fetchall())


def list_messages(
    connection, owner_user_id: str, session_id: str
) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CHAT_MESSAGE_COLUMNS} FROM chat_messages "
            "WHERE session_id = %s AND owner_user_id = %s "
            "ORDER BY created_at ASC, role DESC, id ASC",
            (session_id, owner_user_id),
        )
        return cursor.fetchall()


def create_message(
    connection,
    owner_user_id: str,
    session_id: str,
    *,
    role: str,
    content: str,
    sources: list[dict[str, Any]] | None = None,
    has_evidence: bool = True,
) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO chat_messages "
            f"(session_id, owner_user_id, role, content, sources, has_evidence) "
            f"VALUES (%s, %s, %s, %s, %s, %s) "
            f"RETURNING {CHAT_MESSAGE_COLUMNS}",
            (
                session_id,
                owner_user_id,
                role,
                content,
                Jsonb(sources or []),
                has_evidence,
            ),
        )
        return cursor.fetchone()


def touch_session(connection, owner_user_id: str, session_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE chat_sessions SET updated_at = now() "
            "WHERE id = %s AND owner_user_id = %s",
            (session_id, owner_user_id),
        )
