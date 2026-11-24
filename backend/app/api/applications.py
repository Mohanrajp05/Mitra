"""Job application REST endpoints (Phase 2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services import application_service, candidate_portal_service

candidate_router = APIRouter(prefix="/api/candidate", tags=["Candidate Applications"])
recruiter_router = APIRouter(prefix="/api", tags=["Applications"])


class StatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)


def _candidate_id_or_403(current_user: dict[str, Any]) -> str:
    user_id = str(current_user.get("id") or "")
    if not user_id or not candidate_portal_service.is_candidate(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required.")
    profile = candidate_portal_service.get_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate profile not found.")
    return str(profile.get("id"))


def _recruiter_or_403(current_user: dict[str, Any]) -> str:
    user_id = str(current_user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    if candidate_portal_service.is_candidate(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    return user_id


@candidate_router.get("/jobs")
def candidate_list_jobs(current_user: dict[str, Any] = Depends(get_current_user)):
    _candidate_id_or_403(current_user)
    return application_service.list_open_jobs()


@candidate_router.get("/jobs/{job_id}")
def candidate_get_job(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    _candidate_id_or_403(current_user)
    job = application_service.get_open_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@candidate_router.post("/jobs/{job_id}/apply", status_code=status.HTTP_201_CREATED)
def candidate_apply(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user.get("id") or "")
    _candidate_id_or_403(current_user)
    result = application_service.apply(user_id, job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job or profile not found.")
    if result.get("duplicate"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have already applied to this job.")
    return result


@candidate_router.get("/applications")
def candidate_applications(current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user.get("id") or "")
    _candidate_id_or_403(current_user)
    return application_service.list_my_applications(user_id)


@recruiter_router.get("/jobs/{job_id}/applicants")
def recruiter_applicants(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _recruiter_or_403(current_user)
    return application_service.list_applicants(user_id, job_id)


@recruiter_router.patch("/applications/{application_id}")
def recruiter_update_application(application_id: str, payload: StatusUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _recruiter_or_403(current_user)
    updated = application_service.update_status(user_id, application_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found or invalid status.")
    return updated
