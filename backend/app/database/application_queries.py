"""Queries for job applications."""

from __future__ import annotations

from typing import Any


def list_jobs_for_candidates(connection) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, owner_user_id, title, company, description, required_skills, "
            "experience_required, location, status, experience_level, job_type, "
            "internship_duration_months, compensation_type, salary_stipend, work_mode, "
            "required_documents, application_deadline, created_at, updated_at FROM jobs "
            "WHERE status = 'open' ORDER BY created_at DESC"
        )
        return cursor.fetchall()


def get_job_for_candidate(connection, job_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, owner_user_id, title, company, description, required_skills, "
            "experience_required, location, status, experience_level, job_type, "
            "internship_duration_months, compensation_type, salary_stipend, work_mode, "
            "required_documents, application_deadline, created_at, updated_at FROM jobs "
            "WHERE id = %s AND status = 'open'",
            (job_id,),
        )
        return cursor.fetchone()


def create_application(connection, candidate_id: str, job_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO applications (candidate_id, job_id)
            VALUES (%s, %s)
            ON CONFLICT (candidate_id, job_id) DO NOTHING
            RETURNING id, candidate_id, job_id, status, applied_at, updated_at
            """,
            (candidate_id, job_id),
        )
        return cursor.fetchone()


def list_applications_for_candidate(connection, candidate_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.id, a.candidate_id, a.job_id, a.status, a.applied_at, a.updated_at,
                   j.title AS job_title, j.company AS job_company, j.location AS job_location
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            WHERE a.candidate_id = %s
            ORDER BY a.applied_at DESC
            """,
            (candidate_id,),
        )
        return cursor.fetchall()


def list_applications_for_job(connection, owner_user_id: str, job_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.id, a.candidate_id, a.job_id, a.status, a.applied_at, a.updated_at,
                   c.full_name AS candidate_name, c.email AS candidate_email, c.phone AS candidate_phone,
                   c.skills AS candidate_skills, c.resume_text AS candidate_resume
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            JOIN candidates c ON c.id = a.candidate_id
            WHERE j.id = %s AND j.owner_user_id = %s
            ORDER BY a.applied_at DESC
            """,
            (job_id, owner_user_id),
        )
        return cursor.fetchall()


def get_application(connection, application_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, candidate_id, job_id, status, applied_at, updated_at FROM applications WHERE id = %s",
            (application_id,),
        )
        return cursor.fetchone()


def update_application_status(connection, owner_user_id: str, application_id: str, status: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE applications a
            SET status = %s, updated_at = now()
            FROM jobs j
            WHERE a.id = %s AND a.job_id = j.id AND j.owner_user_id = %s
            RETURNING a.id, a.candidate_id, a.job_id, a.status, a.applied_at, a.updated_at
            """,
            (status, application_id, owner_user_id),
        )
        return cursor.fetchone()


def candidate_owns_application(connection, candidate_id: str, application_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM applications WHERE id = %s AND candidate_id = %s",
            (application_id, candidate_id),
        )
        return cursor.fetchone() is not None
