"""Parameterized SQL queries for jobs and candidates.

Every read, update, and delete includes ``owner_user_id = %s`` so records can
only be accessed by the authenticated Supabase user who owns them.
"""

from typing import Any

JOB_COLUMNS = (
    "id, owner_user_id, title, company, description, required_skills, "
    "experience_required, location, status, experience_level, job_type, "
    "internship_duration_months, compensation_type, salary_stipend, work_mode, "
    "required_documents, application_deadline, created_at, updated_at"
)

CANDIDATE_COLUMNS = (
    "id, owner_user_id, full_name, email, phone, skills, experience_years, "
    "education, location, resume_text, extracted_profile, created_at, updated_at"
)

JOB_UPDATE_FIELDS = {
    "title",
    "company",
    "description",
    "required_skills",
    "experience_required",
    "location",
    "status",
    "experience_level",
    "job_type",
    "internship_duration_months",
    "compensation_type",
    "salary_stipend",
    "work_mode",
    "required_documents",
    "application_deadline",
}

CANDIDATE_UPDATE_FIELDS = {
    "full_name",
    "email",
    "phone",
    "skills",
    "experience_years",
    "education",
    "location",
    "resume_text",
    "extracted_profile",
}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def list_jobs(connection, owner_user_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {JOB_COLUMNS} FROM jobs "
            "WHERE owner_user_id = %s ORDER BY created_at DESC",
            (owner_user_id,),
        )
        return cursor.fetchall()


def get_job(connection, owner_user_id: str, job_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {JOB_COLUMNS} FROM jobs "
            "WHERE id = %s AND owner_user_id = %s",
            (job_id, owner_user_id),
        )
        return cursor.fetchone()


def create_job(connection, owner_user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO jobs (
                owner_user_id, title, company, description, required_skills,
                experience_required, location, status, experience_level, job_type,
                internship_duration_months, compensation_type, salary_stipend,
                work_mode, required_documents, application_deadline
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {JOB_COLUMNS}
            """,
            (
                owner_user_id,
                data["title"],
                data.get("company"),
                data["description"],
                data.get("required_skills") or [],
                data.get("experience_required"),
                data.get("location"),
                data.get("status", "open"),
                data.get("experience_level"),
                data.get("job_type"),
                data.get("internship_duration_months"),
                data.get("compensation_type"),
                data.get("salary_stipend"),
                data.get("work_mode"),
                data.get("required_documents") or [],
                data.get("application_deadline"),
            ),
        )
        return cursor.fetchone()


def update_job(
    connection, owner_user_id: str, job_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    fields = [name for name in changes if name in JOB_UPDATE_FIELDS]
    if not fields:
        return get_job(connection, owner_user_id, job_id)

    assignments = ", ".join(f"{name} = %s" for name in fields)
    params = [changes[name] for name in fields]
    params.extend([job_id, owner_user_id])

    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE jobs SET {assignments}, updated_at = now() "
            f"WHERE id = %s AND owner_user_id = %s RETURNING {JOB_COLUMNS}",
            params,
        )
        return cursor.fetchone()


def delete_job(connection, owner_user_id: str, job_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM jobs WHERE id = %s AND owner_user_id = %s RETURNING id",
            (job_id, owner_user_id),
        )
        return cursor.fetchone() is not None


def delete_jobs(
    connection, owner_user_id: str, job_ids: list[str]
) -> list[str]:
    """Delete several jobs for the owner. Returns the ids actually deleted."""
    ids = [str(job_id) for job_id in job_ids if str(job_id).strip()]
    if not ids:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM jobs WHERE id = ANY(%s::uuid[]) AND owner_user_id = %s "
            "RETURNING id",
            (ids, owner_user_id),
        )
        return [str(row["id"]) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

def list_candidates(connection, owner_user_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CANDIDATE_COLUMNS} FROM candidates "
            "WHERE owner_user_id = %s ORDER BY created_at DESC",
            (owner_user_id,),
        )
        return cursor.fetchall()


def get_candidate(
    connection, owner_user_id: str, candidate_id: str
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {CANDIDATE_COLUMNS} FROM candidates "
            "WHERE id = %s AND owner_user_id = %s",
            (candidate_id, owner_user_id),
        )
        return cursor.fetchone()


def create_candidate(
    connection, owner_user_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO candidates (
                owner_user_id, full_name, email, phone, skills,
                experience_years, education, location, resume_text
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {CANDIDATE_COLUMNS}
            """,
            (
                owner_user_id,
                data["full_name"],
                data.get("email"),
                data.get("phone"),
                data.get("skills") or [],
                data.get("experience_years"),
                data.get("education"),
                data.get("location"),
                data.get("resume_text"),
            ),
        )
        return cursor.fetchone()


def update_candidate(
    connection, owner_user_id: str, candidate_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    fields = [name for name in changes if name in CANDIDATE_UPDATE_FIELDS]
    if not fields:
        return get_candidate(connection, owner_user_id, candidate_id)

    assignments = ", ".join(f"{name} = %s" for name in fields)
    params = [changes[name] for name in fields]
    params.extend([candidate_id, owner_user_id])

    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE candidates SET {assignments}, updated_at = now() "
            f"WHERE id = %s AND owner_user_id = %s RETURNING {CANDIDATE_COLUMNS}",
            params,
        )
        return cursor.fetchone()


def delete_candidate(connection, owner_user_id: str, candidate_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM candidates WHERE id = %s AND owner_user_id = %s RETURNING id",
            (candidate_id, owner_user_id),
        )
        return cursor.fetchone() is not None


def delete_all_candidates_for_owner(connection, owner_user_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM candidates WHERE owner_user_id = %s RETURNING id",
            (owner_user_id,),
        )
        return len(cursor.fetchall())


def delete_all_jobs_for_owner(connection, owner_user_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM jobs WHERE owner_user_id = %s RETURNING id",
            (owner_user_id,),
        )
        return len(cursor.fetchall())


def delete_expired_candidates(
    connection, owner_user_id: str, older_than: str
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM candidates "
            "WHERE owner_user_id = %s AND created_at < %s RETURNING id",
            (owner_user_id, older_than),
        )
        return len(cursor.fetchall())


def count_expired_candidates(
    connection, owner_user_id: str, older_than: str
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM candidates "
            "WHERE owner_user_id = %s AND created_at < %s",
            (owner_user_id, older_than),
        )
        return len(cursor.fetchall())
