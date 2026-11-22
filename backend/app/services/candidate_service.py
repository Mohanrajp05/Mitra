"""Business logic for candidates and their consent records.

The owner_user_id always comes from the verified Supabase token in the API
layer; it is passed through to every query. Consent is never assumed: a
candidate without a consent record is reported as ``not_recorded`` and is
treated as not consented. Important candidate changes are recorded in the
audit trail as metadata only (never resume text or contact details).
"""

from app.core.audit import (
    CANDIDATE_CREATED,
    CANDIDATE_DELETED,
    CANDIDATE_UPDATED,
    CONSENT_GRANTED,
    CONSENT_WITHDRAWN,
    get_audit_trail,
)
from app.database import consent_queries, queries
from app.database.connection import get_connection
from app.schemas.candidate import CandidateCreate, CandidateUpdate
from app.schemas.consent import CONSENT_TYPES


class ConsentTypeError(ValueError):
    pass


def list_candidates(owner_user_id: str):
    with get_connection() as connection:
        return queries.list_candidates(connection, owner_user_id)


def get_candidate(owner_user_id: str, candidate_id: str):
    with get_connection() as connection:
        return queries.get_candidate(connection, owner_user_id, candidate_id)


def create_candidate(owner_user_id: str, payload: CandidateCreate):
    data = payload.model_dump()
    with get_connection() as connection:
        candidate = queries.create_candidate(connection, owner_user_id, data)
    get_audit_trail().record(
        CANDIDATE_CREATED,
        user_id=owner_user_id,
        resource_id=str(candidate.get("id") or ""),
    )
    return candidate


_MATCH_RELEVANT_CANDIDATE_FIELDS = {"experience_years", "resume_text"}


def _invalidate_match_cache_for_candidate(owner_user_id: str, candidate_id: str) -> None:
    try:
        from app.rag.match_cache import get_match_cache

        get_match_cache().invalidate_candidate(owner_user_id, candidate_id)
    except Exception:
        return


def update_candidate(owner_user_id: str, candidate_id: str, payload: CandidateUpdate):
    changes = payload.model_dump(exclude_unset=True)
    with get_connection() as connection:
        candidate = queries.update_candidate(
            connection, owner_user_id, candidate_id, changes
        )
    if candidate is not None:
        get_audit_trail().record(
            CANDIDATE_UPDATED,
            user_id=owner_user_id,
            resource_id=str(candidate.get("id") or ""),
            detail=f"fields={','.join(sorted(changes))}",
        )
        if _MATCH_RELEVANT_CANDIDATE_FIELDS.intersection(changes):
            _invalidate_match_cache_for_candidate(owner_user_id, candidate_id)
    return candidate


def delete_candidate(owner_user_id: str, candidate_id: str) -> bool:
    with get_connection() as connection:
        deleted = queries.delete_candidate(connection, owner_user_id, candidate_id)
    if deleted:
        _invalidate_match_cache_for_candidate(owner_user_id, candidate_id)
        get_audit_trail().record(
            CANDIDATE_DELETED,
            user_id=owner_user_id,
            resource_id=candidate_id,
        )
    return deleted


def get_consent_status(owner_user_id: str, candidate_id: str, consent_type: str):
    """Return the consent status without ever assuming consent.

    Returns the row plus a computed ``status`` of granted, withdrawn, or
    ``not_recorded`` when no consent record exists yet. No historical consent
    is fabricated.
    """
    if consent_type not in CONSENT_TYPES:
        raise ConsentTypeError(
            "consent_type must be one of: " + ", ".join(CONSENT_TYPES) + "."
        )

    with get_connection() as connection:
        candidate = queries.get_candidate(connection, owner_user_id, candidate_id)
        if candidate is None:
            return None

        record = consent_queries.get_consent(
            connection, owner_user_id, candidate_id, consent_type
        )

    if record is None:
        return {
            "candidate_id": str(candidate.get("id") or ""),
            "consent_type": consent_type,
            "status": "not_recorded",
            "decided_at": None,
        }
    return record


def set_consent(owner_user_id: str, candidate_id: str, consent_type: str, granted: bool):
    """Record a consent decision (grant or withdrawal) for an owned candidate."""
    if consent_type not in CONSENT_TYPES:
        raise ConsentTypeError(
            "consent_type must be one of: " + ", ".join(CONSENT_TYPES) + "."
        )

    with get_connection() as connection:
        candidate = queries.get_candidate(connection, owner_user_id, candidate_id)
        if candidate is None:
            return None

        record = consent_queries.upsert_consent(
            connection, owner_user_id, candidate_id, consent_type, granted
        )

    get_audit_trail().record(
        CONSENT_GRANTED if granted else CONSENT_WITHDRAWN,
        user_id=owner_user_id,
        resource_id=candidate_id,
        detail=f"consent_type={consent_type}",
    )
    return record
