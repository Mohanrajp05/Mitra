"""Business logic for jobs.

The owner_user_id always comes from the verified Supabase token in the API
layer; it is passed through to every query.
"""

from app.database import queries
from app.database.connection import get_connection
from app.rag.vector_store import get_document_store
from app.schemas.job import JobCreate, JobUpdate


def list_jobs(owner_user_id: str):
    with get_connection() as connection:
        return queries.list_jobs(connection, owner_user_id)


def get_job(owner_user_id: str, job_id: str):
    with get_connection() as connection:
        return queries.get_job(connection, owner_user_id, job_id)


def create_job(owner_user_id: str, payload: JobCreate):
    data = payload.model_dump()
    with get_connection() as connection:
        return queries.create_job(connection, owner_user_id, data)


_MATCH_RELEVANT_JOB_FIELDS = {
    "title",
    "company",
    "description",
    "required_skills",
    "experience_required",
    "location",
}


def _invalidate_match_cache_for_job(owner_user_id: str, job_id: str) -> None:
    try:
        from app.rag.match_cache import get_match_cache

        get_match_cache().invalidate_job(owner_user_id, job_id)
    except Exception:
        return


def update_job(owner_user_id: str, job_id: str, payload: JobUpdate):
    changes = payload.model_dump(exclude_unset=True)
    with get_connection() as connection:
        job = queries.update_job(connection, owner_user_id, job_id, changes)
    if job is not None and _MATCH_RELEVANT_JOB_FIELDS.intersection(changes):
        _invalidate_match_cache_for_job(owner_user_id, job_id)
    return job


def delete_job(owner_user_id: str, job_id: str) -> bool:
    with get_connection() as connection:
        deleted = queries.delete_job(connection, owner_user_id, job_id)
    if deleted:
        _invalidate_match_cache_for_job(owner_user_id, job_id)
        _delete_job_documents(owner_user_id, job_id)
    return deleted


def delete_jobs(owner_user_id: str, job_ids: list[str]) -> int:
    """Delete several jobs and their attached documents. Returns the count."""
    with get_connection() as connection:
        deleted_ids = queries.delete_jobs(connection, owner_user_id, job_ids)
    for job_id in deleted_ids:
        _invalidate_match_cache_for_job(owner_user_id, job_id)
        _delete_job_documents(owner_user_id, job_id)
    return len(deleted_ids)


def _delete_job_documents(owner_user_id: str, job_id: str) -> int:
    """Remove vector-store documents attached to a deleted job.

    Failures are contained: the job deletion itself always succeeds and the
    documents can be cleaned up later.
    """
    try:
        store = get_document_store()
        removed = 0
        for item in store.list_documents(owner_user_id):
            if item.get("job_id") != job_id:
                continue
            document_id = str(item.get("document_id") or "")
            if document_id and store.delete_document(owner_user_id, document_id):
                removed += 1
        return removed
    except Exception:
        return 0
