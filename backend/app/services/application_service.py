"""Job application service (Phase 2)."""

from __future__ import annotations

from typing import Any

from app.database import application_queries, queries
from app.database.connection import get_connection
from app.services import candidate_portal_service


def _self_candidate_id(user_id: str) -> str | None:
    profile = candidate_portal_service.get_profile(user_id)
    if profile is None:
        return None
    return str(profile.get("id"))


def list_open_jobs() -> list[dict[str, Any]]:
    with get_connection() as connection:
        return application_queries.list_jobs_for_candidates(connection)


def get_open_job(job_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        return application_queries.get_job_for_candidate(connection, job_id)


def apply(user_id: str, job_id: str) -> dict[str, Any] | None:
    candidate_id = _self_candidate_id(user_id)
    if candidate_id is None:
        return None
    job = get_open_job(job_id)
    if job is None:
        return None
    with get_connection() as connection:
        created = application_queries.create_application(connection, candidate_id, job_id)
    if created is None:
        # Duplicate application
        return {"duplicate": True}
    return created


def list_my_applications(user_id: str) -> list[dict[str, Any]]:
    candidate_id = _self_candidate_id(user_id)
    if candidate_id is None:
        return []
    with get_connection() as connection:
        return application_queries.list_applications_for_candidate(connection, candidate_id)


def list_applicants(owner_user_id: str, job_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        job_row = queries.get_job(connection, owner_user_id, job_id)
        if job_row is None:
            return []
        return application_queries.list_applications_for_job(connection, owner_user_id, job_id)


def update_status(owner_user_id: str, application_id: str, new_status: str) -> dict[str, Any] | None:
    allowed = {"applied", "under_review", "shortlisted", "rejected", "interview", "hired", "withdrawn"}
    if new_status not in allowed:
        return None
    with get_connection() as connection:
        return application_queries.update_application_status(connection, owner_user_id, application_id, new_status)
