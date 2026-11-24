"""Queries for the candidate/recruiter role mapping."""

from __future__ import annotations

from typing import Any


def get_role(connection, user_id: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT role FROM user_roles WHERE user_id = %s", (user_id,)
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return str(row.get("role") if isinstance(row, dict) else row[0])


def set_role(connection, user_id: str, role: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO user_roles (user_id, role)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            (user_id, role),
        )
