"""Candidate self-service REST endpoints (Phase 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.rag.config import rag_settings
from app.rag.document_loader import (
    DocumentError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.services import candidate_portal_service, rag_service

router = APIRouter(prefix="/api/candidate", tags=["Candidate Portal"])

RESUME_FILE_EXTENSIONS = {".pdf", ".docx"}


class CandidateOnboardRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = None


class CandidateProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] | None = None
    experience_years: int | None = None
    education: str | None = None
    location: str | None = None
    resume_text: str | None = None


def _require_candidate(current_user: dict[str, Any]) -> str:
    user_id = str(current_user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    if not candidate_portal_service.is_candidate(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required.")
    return user_id


@router.post("/onboard", status_code=status.HTTP_201_CREATED)
def onboard(payload: CandidateOnboardRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    profile = candidate_portal_service.get_profile(user_id)
    if profile is None:
        profile = candidate_portal_service.create_profile(user_id, payload.full_name, payload.email or current_user.get("email"))
    else:
        candidate_portal_service.ensure_candidate_role(user_id)
    return profile


@router.get("/me")
def get_me(current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _require_candidate(current_user)
    profile = candidate_portal_service.get_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate profile not found.")
    return profile


@router.put("/me")
def update_me(payload: CandidateProfileUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _require_candidate(current_user)
    changes = payload.model_dump(exclude_unset=True)
    updated = candidate_portal_service.update_profile(user_id, changes)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate profile not found.")
    return updated


@router.get("/dashboard")
def dashboard(current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _require_candidate(current_user)
    return candidate_portal_service.dashboard(user_id)


@router.get("/resume")
def get_resume(current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _require_candidate(current_user)
    state = candidate_portal_service.get_resume(user_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate profile not found.")
    return state


@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    user_id = _require_candidate(current_user)

    filename = (file.filename or "").strip()
    extension = Path(filename).suffix.lower()
    if extension not in RESUME_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and DOCX resumes are supported.",
        )

    limit = rag_settings.max_upload_bytes
    if file.size is not None and file.size > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Your resume must be 5 MB or smaller.",
        )

    # Read at most one byte over the limit so an oversized upload is rejected
    # without pulling an unbounded amount of data into memory.
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Your resume must be 5 MB or smaller.",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )

    try:
        return await candidate_portal_service.upload_resume(
            user_id,
            filename=filename,
            data=data,
            content_type=file.content_type,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except DocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except (
        candidate_portal_service.ResumeProfileNotFoundError,
        rag_service.RecordNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.delete("/resume")
async def delete_resume(current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _require_candidate(current_user)
    try:
        return await candidate_portal_service.delete_resume(user_id)
    except candidate_portal_service.ResumeProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
