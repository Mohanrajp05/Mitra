"""Parameterized SQL queries for mock interview sessions.

Every query filters by ``user_id`` so sessions are only visible to the
authenticated owner.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

INTERVIEW_SESSION_COLUMNS = (
    "id, user_id, document_id, resume_filename, candidate_role, status, "
    "interview_type, difficulty, mode, current_question_number, total_questions, "
    "final_score, evaluation_report, extracted_info, created_at, updated_at, completed_at"
)

INTERVIEW_QUESTION_COLUMNS = (
    "id, session_id, user_id, question_number, question_type, question_text, "
    "difficulty, answer_text, evaluation, created_at, answered_at"
)

RESUMABLE_STATUSES = ("awaiting_resume", "ready", "in_progress")


def create_session(
    connection,
    user_id: str,
    *,
    interview_type: str = "Technical + HR",
    total_questions: int = 10,
    difficulty: str = "Adaptive",
    mode: str = "Text-based",
) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO interview_sessions (
                user_id, status, interview_type, total_questions, difficulty, mode
            )
            VALUES (%s, 'awaiting_resume', %s, %s, %s, %s)
            RETURNING {INTERVIEW_SESSION_COLUMNS}
            """,
            (user_id, interview_type, total_questions, difficulty, mode),
        )
        return cursor.fetchone()


def get_session(connection, user_id: str, session_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {INTERVIEW_SESSION_COLUMNS} FROM interview_sessions WHERE id = %s AND user_id = %s",
            (session_id, user_id),
        )
        return cursor.fetchone()


def get_current_session(connection, user_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {INTERVIEW_SESSION_COLUMNS} FROM interview_sessions
            WHERE user_id = %s AND status = ANY(%s)
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (user_id, list(RESUMABLE_STATUSES)),
        )
        return cursor.fetchone()


def count_document_references(
    connection, user_id: str, document_id: str
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) AS total FROM interview_sessions WHERE user_id = %s AND document_id = %s",
            (user_id, document_id),
        )
        row = cursor.fetchone()
    if isinstance(row, dict):
        return int(row.get("total") or 0)
    return int(row[0]) if row else 0


def delete_questions(connection, user_id: str, session_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM interview_questions WHERE user_id = %s AND session_id = %s",
            (user_id, session_id),
        )
        return int(cursor.rowcount or 0)


def insert_question(
    connection,
    user_id: str,
    session_id: str,
    question: dict[str, Any],
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO interview_questions (
                session_id, user_id, question_number, question_type, question_text, difficulty
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id, question_number) DO NOTHING
            RETURNING {INTERVIEW_QUESTION_COLUMNS}
            """,
            (
                session_id,
                user_id,
                question.get("question_number"),
                question.get("question_type") or "technical",
                question.get("question_text") or "",
                question.get("difficulty") or "Easy",
            ),
        )
        return cursor.fetchone()


def list_questions(
    connection, user_id: str, session_id: str
) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {INTERVIEW_QUESTION_COLUMNS}
            FROM interview_questions
            WHERE user_id = %s AND session_id = %s
            ORDER BY question_number ASC
            """,
            (user_id, session_id),
        )
        rows = cursor.fetchall()
    return [dict(row) if not isinstance(row, dict) else row for row in rows]


def get_question(
    connection, user_id: str, session_id: str, question_number: int
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {INTERVIEW_QUESTION_COLUMNS}
            FROM interview_questions
            WHERE user_id = %s AND session_id = %s AND question_number = %s
            """,
            (user_id, session_id, question_number),
        )
        return cursor.fetchone()


def update_question_answer(
    connection,
    user_id: str,
    session_id: str,
    question_number: int,
    *,
    answer_text: str,
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE interview_questions
            SET answer_text = %s, answered_at = now()
            WHERE user_id = %s AND session_id = %s AND question_number = %s
            RETURNING {INTERVIEW_QUESTION_COLUMNS}
            """,
            (answer_text, user_id, session_id, question_number),
        )
        return cursor.fetchone()


def update_question_evaluation(
    connection,
    user_id: str,
    session_id: str,
    question_number: int,
    evaluation: dict[str, Any],
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE interview_questions
            SET evaluation = %s
            WHERE user_id = %s AND session_id = %s AND question_number = %s
            RETURNING {INTERVIEW_QUESTION_COLUMNS}
            """,
            (Jsonb(evaluation), user_id, session_id, question_number),
        )
        return cursor.fetchone()


def update_session(connection, user_id: str, session_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "document_id",
        "resume_filename",
        "candidate_role",
        "status",
        "current_question_number",
        "total_questions",
        "final_score",
        "evaluation_report",
        "extracted_info",
        "completed_at",
    }
    fields = [name for name in changes if name in allowed]
    if not fields:
        return get_session(connection, user_id, session_id)

    values = []
    for name in fields:
        value = changes[name]
        if name in {"evaluation_report", "extracted_info"} and value is not None:
            value = Jsonb(value)
        values.append(value)

    assignments = ", ".join(f"{name} = %s" for name in fields)
    params = [*values, session_id, user_id]
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE interview_sessions
            SET {assignments}, updated_at = now()
            WHERE id = %s AND user_id = %s
            RETURNING {INTERVIEW_SESSION_COLUMNS}
            """,
            params,
        )
        return cursor.fetchone()
