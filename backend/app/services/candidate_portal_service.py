"""Candidate self-service portal (Phase 1).

Candidates authenticate with the same Supabase Auth as recruiters. A candidate
account is identified by a row in ``user_roles`` with role='candidate'. Their
profile is a normal ``candidates`` row owned by themselves (owner_user_id =
authenticated user id), so all existing ownership checks still apply.
"""

from __future__ import annotations

from typing import Any

from app.core.audit import get_audit_trail
from app.database import queries, user_role_queries
from app.database.connection import get_connection
from app.schemas.candidate import CandidateUpdate

# Same ceiling as CandidateUpdate.resume_text: the DB column is TEXT, but the
# API contract (and the paste editor) accept at most 50k characters.
RESUME_TEXT_LIMIT = 50_000


class ResumeProfileNotFoundError(RuntimeError):
    """Raised when a resume operation has no candidate profile to attach to."""


def ensure_candidate_role(user_id: str) -> None:
    with get_connection() as connection:
        if user_role_queries.get_role(connection, user_id) is None:
            user_role_queries.set_role(connection, user_id, "candidate")


def is_candidate(user_id: str) -> bool:
    try:
        with get_connection() as connection:
            return user_role_queries.get_role(connection, user_id) == "candidate"
    except Exception:
        return False


def get_account_role(user_id: str, user_metadata: dict[str, Any] | None = None) -> str:
    """Return the authoritative account role for the authenticated user.

    Recruiters do not have a row in ``user_roles`` (the recruiter workspace
    predates the table), so any authenticated user without an explicit
    ``candidate`` role is treated as a recruiter.

    Accounts that signed up through the candidate registration page carry
    ``role='candidate'`` in their verified Supabase metadata. If email
    confirmation interrupted onboarding, the ``user_roles`` row may not exist
    yet; in that case we persist the intended role so every later lookup is
    database-authoritative.
    """
    with get_connection() as connection:
        role = user_role_queries.get_role(connection, user_id)
    if role == "candidate":
        return "candidate"
    if role is not None:
        return "recruiter"

    intended = str((user_metadata or {}).get("role") or "").strip().lower()
    if intended == "candidate":
        try:
            ensure_candidate_role(user_id)
        except Exception:  # noqa: BLE001 - role lookup must still succeed
            pass
        return "candidate"
    return "recruiter"


def _self_candidate_id(user_id: str) -> str | None:
    with get_connection() as connection:
        rows = queries.list_candidates(connection, user_id)
    if not rows:
        return None
    return str(rows[0].get("id"))


def get_profile(user_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        rows = queries.list_candidates(connection, user_id)
    if not rows:
        return None
    return rows[0]


def create_profile(user_id: str, full_name: str, email: str | None = None) -> dict[str, Any]:
    ensure_candidate_role(user_id)
    data = {"full_name": full_name, "email": email, "skills": []}
    with get_connection() as connection:
        candidate = queries.create_candidate(connection, user_id, data)
    get_audit_trail().record("candidate_self_registered", user_id=user_id, resource_id=str(candidate.get("id") or ""))
    return candidate


def update_profile(user_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    candidate_id = _self_candidate_id(user_id)
    if candidate_id is None:
        return None
    payload = CandidateUpdate(**changes)
    changes = payload.model_dump(exclude_unset=True)
    with get_connection() as connection:
        candidate = queries.update_candidate(connection, user_id, candidate_id, changes)
    if candidate is not None:
        get_audit_trail().record("candidate_self_updated", user_id=user_id, resource_id=str(candidate.get("id") or ""))
    return candidate


def _resume_state(profile: dict[str, Any], resume_text: str | None, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the resume summary shown on the candidate resume page.

    File metadata lives in the existing RAG document store (the project's
    only document storage), so no schema change is needed. ``status`` is
    derived from that metadata plus the persisted resume text.
    """
    latest = documents[0] if documents else None
    if latest is not None:
        status = "uploaded"
    elif resume_text:
        status = "text_only"
    else:
        status = "missing"

    return {
        "candidate_id": str(profile.get("id") or ""),
        "status": status,
        "has_resume": bool(latest is not None or resume_text),
        "file": latest,
        "documents": documents,
        # Bounded for the paste editor; the document store keeps the full text.
        "resume_text": (resume_text or "")[:RESUME_TEXT_LIMIT],
    }


def get_resume(user_id: str) -> dict[str, Any] | None:
    """Return the authenticated candidate's own resume state."""
    profile = get_profile(user_id)
    if profile is None:
        return None

    from app.services import rag_service  # deferred: avoids an import cycle

    resume_text, documents = rag_service.candidate_resume_package(user_id, profile)
    return _resume_state(profile, resume_text, documents)


async def upload_resume(
    user_id: str,
    *,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Store a resume for the authenticated candidate and extract its text.

    Reuses the existing RAG document pipeline, which validates the filename
    and the actual file bytes, enforces the size limit, rejects unsafe names,
    stores the original privately, parses the text and embeds it. The
    extracted text is also persisted to ``candidates.resume_text`` so the
    candidate profile, recruiter applicant views, and matching that read the
    candidate row all see the uploaded resume.
    """
    profile = get_profile(user_id)
    if profile is None:
        raise ResumeProfileNotFoundError("Candidate profile not found.")
    candidate_id = str(profile.get("id") or "")

    from app.services import rag_service  # deferred: avoids an import cycle

    record = await rag_service.save_document(
        user_id,
        filename=filename,
        data=data,
        source_type="resume",
        candidate_id=candidate_id,
        content_type=content_type,
    )

    resume_text, _ = rag_service.candidate_resume_package(user_id, profile)
    text = (resume_text or "")[:RESUME_TEXT_LIMIT]
    if text:
        with get_connection() as connection:
            queries.update_candidate(
                connection, user_id, candidate_id, {"resume_text": text}
            )

    get_audit_trail().record(
        "candidate_resume_uploaded",
        user_id=user_id,
        resource_id=str(getattr(record, "document_id", "") or ""),
        detail=f"filename={getattr(record, 'filename', '')}",
    )

    updated = get_profile(user_id) or profile
    resume_text, documents = rag_service.candidate_resume_package(user_id, updated)
    return _resume_state(updated, resume_text, documents)


async def delete_resume(user_id: str) -> dict[str, Any]:
    """Remove the candidate's resume file(s) and stored resume text."""
    profile = get_profile(user_id)
    if profile is None:
        raise ResumeProfileNotFoundError("Candidate profile not found.")
    candidate_id = str(profile.get("id") or "")

    from app.services import rag_service  # deferred: avoids an import cycle

    documents = await rag_service.list_documents(user_id)
    removed = 0
    for document in documents:
        if document.get("source_type") != "resume":
            continue
        if str(document.get("candidate_id") or "") != candidate_id:
            continue
        try:
            await rag_service.delete_document(
                user_id, str(document.get("document_id") or "")
            )
            removed += 1
        except rag_service.RecordNotFoundError:
            continue

    with get_connection() as connection:
        queries.update_candidate(
            connection,
            user_id,
            candidate_id,
            {"resume_text": None, "extracted_profile": None},
        )

    # Deleting a resume must never leave a cached match built from it.
    try:
        rag_service._invalidate_match_cache_for_candidate(user_id, candidate_id)
    except Exception:  # noqa: BLE001 - cleanup must not fail the request
        pass

    get_audit_trail().record(
        "candidate_resume_removed",
        user_id=user_id,
        resource_id=candidate_id,
        detail=f"documents_removed={removed}",
    )

    updated = get_profile(user_id) or profile
    resume_text, remaining = rag_service.candidate_resume_package(user_id, updated)
    return _resume_state(updated, resume_text, remaining)


def _safe_rows(loader) -> list[dict[str, Any]]:
    """Dashboard sections must not fail the whole page if one source errors."""
    try:
        rows = loader()
    except Exception:  # noqa: BLE001 - degrade gracefully to an empty section
        return []
    return rows if isinstance(rows, list) else []


def dashboard(user_id: str) -> dict[str, Any]:
    from datetime import date

    # Imported lazily to avoid a circular import: the Phase 2/3/4 services all
    # depend on this module for the candidate identity lookup.
    from app.services import application_service, candidate_interview_service, messaging_service

    profile = get_profile(user_id)
    fields = ["full_name", "email", "phone", "skills", "education", "resume_text"]
    filled = sum(1 for field in fields if profile and profile.get(field))
    completion = int(round(100 * filled / len(fields))) if profile else 0

    applications = _safe_rows(lambda: application_service.list_my_applications(user_id))
    interviews = _safe_rows(lambda: candidate_interview_service.list_my_interviews(user_id))
    conversations = _safe_rows(lambda: messaging_service.list_conversations(user_id))

    def _interview_date(row: dict[str, Any]) -> date | None:
        value = row.get("interview_date")
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    today = date.today()

    def _is_upcoming(row: dict[str, Any]) -> bool:
        scheduled_for = _interview_date(row)
        return row.get("status") == "scheduled" and scheduled_for is not None and scheduled_for >= today

    upcoming = [row for row in interviews if _is_upcoming(row)]
    upcoming.sort(key=lambda row: (str(row.get("interview_date") or ""), str(row.get("start_time") or "")))

    stats = {
        "total_applications": len(applications),
        "under_review": sum(1 for row in applications if row.get("status") == "under_review"),
        "shortlisted": sum(1 for row in applications if row.get("status") == "shortlisted"),
        "upcoming_interviews": len(upcoming),
    }

    return {
        "profile_completion": completion,
        "has_resume": bool(profile and profile.get("resume_text")),
        "profile": profile,
        "stats": stats,
        "recent_applications": applications[:5],
        "upcoming_interviews": upcoming[:5],
        "recent_messages": conversations[:5],
    }
