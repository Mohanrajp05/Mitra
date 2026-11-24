"""Candidate REST endpoints.

Every endpoint uses the verified Supabase user ID as the owner. A record that
belongs to another user is reported as 404 so its existence is not disclosed.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.security import get_current_user
from app.schemas.candidate import CandidateCreate, CandidateResponse, CandidateUpdate
from app.schemas.consent import ConsentUpdate
from app.services import candidate_portal_service, candidate_service
from app.services import rag_service

router = APIRouter(prefix="/api/candidates", tags=["Candidates"])


def _require_recruiter(current_user: dict) -> str:
    user_id = str(current_user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    if candidate_portal_service.is_candidate(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    return user_id


@router.get("", response_model=list[CandidateResponse])
def list_candidates(current_user: dict = Depends(get_current_user)):
    _require_recruiter(current_user)
    return candidate_service.list_candidates(current_user["id"])


@router.post(
    "", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED
)
def create_candidate(
    payload: CandidateCreate,
    current_user: dict = Depends(get_current_user),
):
    return candidate_service.create_candidate(current_user["id"], payload)


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: str, current_user: dict = Depends(get_current_user)
):
    candidate = candidate_service.get_candidate(current_user["id"], candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found."
        )
    # Enrich the detail response with the resumes linked to this candidate
    # in the document store, and resolve the resume text so the profile
    # shows the parsed resume even when candidates.resume_text only holds a
    # short hand-typed placeholder. Ownership is enforced inside the
    # document store (only this user's documents are returned).
    resume_text, resume_documents = rag_service.candidate_resume_package(
        current_user["id"], candidate
    )
    payload = dict(candidate)
    if resume_text:
        payload["resume_text"] = resume_text
    payload["resume_documents"] = resume_documents
    # Lazy deterministic backfill: candidates created before profile
    # extraction existed get their structured profile the first time the
    # detail page is opened. Deterministic parsing only (no model call), so
    # this stays fast, and it never overwrites an existing extraction.
    if payload.get("extracted_profile") is None and resume_text:
        try:
            from app.services import extraction_service

            extracted = extraction_service.extract_profile_deterministic(
                current_user["id"], candidate, resume_text
            )
            if extracted:
                payload["extracted_profile"] = extracted
        except Exception:
            pass
    return payload


@router.put("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: str,
    payload: CandidateUpdate,
    current_user: dict = Depends(get_current_user),
):
    candidate = candidate_service.update_candidate(
        current_user["id"], candidate_id, payload
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found."
        )
    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: str, current_user: dict = Depends(get_current_user)
):
    deleted = candidate_service.delete_candidate(current_user["id"], candidate_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{candidate_id}/consent")
def get_consent(
    candidate_id: str,
    consent_type: str = "resume_processing",
    current_user: dict = Depends(get_current_user),
):
    try:
        record = candidate_service.get_consent_status(
            current_user["id"], candidate_id, consent_type
        )
    except candidate_service.ConsentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found."
        )
    return record


@router.put("/{candidate_id}/consent")
def set_consent(
    candidate_id: str,
    payload: ConsentUpdate,
    current_user: dict = Depends(get_current_user),
):
    try:
        record = candidate_service.set_consent(
            current_user["id"], candidate_id, payload.consent_type, payload.granted
        )
    except candidate_service.ConsentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found."
        )
    return record
