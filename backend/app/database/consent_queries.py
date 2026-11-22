"""Parameterized SQL queries for candidate consent records.

Every query filters by ``owner_user_id`` so a consent record is only visible
to the authenticated recruiter who owns the candidate. One row exists per
(candidate_id, consent_type); status flips between granted and withdrawn and
``decided_at`` always reflects the latest decision.
"""

from typing import Any

CONSENT_COLUMNS = (
    "id, candidate_id, owner_user_id, consent_type, status, decided_at, "
    "created_at, updated_at"
)


def get_consent(
    connection, owner_user_id: str, candidate_id: str, consent_type: str
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CONSENT_COLUMNS} FROM candidate_consents "
            "WHERE candidate_id = %s AND consent_type = %s AND owner_user_id = %s",
            (candidate_id, consent_type, owner_user_id),
        )
        return cursor.fetchone()


def upsert_consent(
    connection,
    owner_user_id: str,
    candidate_id: str,
    consent_type: str,
    granted: bool,
) -> dict[str, Any]:
    status = "granted" if granted else "withdrawn"
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO candidate_consents (
                candidate_id, owner_user_id, consent_type, status, decided_at
            )
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (candidate_id, consent_type) DO UPDATE
            SET status = EXCLUDED.status,
                decided_at = EXCLUDED.decided_at,
                owner_user_id = EXCLUDED.owner_user_id
            RETURNING {CONSENT_COLUMNS}
            """,
            (candidate_id, owner_user_id, consent_type, status),
        )
        return cursor.fetchone()


def list_consents(
    connection, owner_user_id: str, candidate_id: str
) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CONSENT_COLUMNS} FROM candidate_consents "
            "WHERE candidate_id = %s AND owner_user_id = %s "
            "ORDER BY decided_at DESC",
            (candidate_id, owner_user_id),
        )
        return cursor.fetchall()


def list_consents_for_owner(
    connection, owner_user_id: str
) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CONSENT_COLUMNS} FROM candidate_consents "
            "WHERE owner_user_id = %s ORDER BY decided_at DESC",
            (owner_user_id,),
        )
        return cursor.fetchall()


def delete_consents_for_owner(connection, owner_user_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM candidate_consents WHERE owner_user_id = %s RETURNING id",
            (owner_user_id,),
        )
        return len(cursor.fetchall())


def delete_expired_consents(
    connection, owner_user_id: str, older_than: str
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM candidate_consents "
            "WHERE owner_user_id = %s AND decided_at < %s RETURNING id",
            (owner_user_id, older_than),
        )
        return len(cursor.fetchall())
