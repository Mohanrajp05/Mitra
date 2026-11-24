"""Candidate interview response REST endpoints (Phase 3)."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services import candidate_interview_service, candidate_portal_service, scheduling_service

candidate_router = APIRouter(prefix="/api/candidate", tags=["Candidate Interviews"])
recruiter_router = APIRouter(prefix="/api/scheduled-interviews", tags=["Scheduled Interviews"])


class DeclineRequest(BaseModel):
    reason: str | None = None


class RescheduleRequest(BaseModel):
    suggested_date: date
    suggested_start_time: time
    reason: str | None = None


class RescheduleDecisionRequest(BaseModel):
    approve: bool


def _candidate_or_403(current_user: dict[str, Any]) -> str:
    user_id = str(current_user.get("id") or "")
    if not user_id or not candidate_portal_service.is_candidate(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required.")
    return user_id


def _recruiter_or_403(current_user: dict[str, Any]) -> str:
    user_id = str(current_user.get("id") or "")
    if not user_id or candidate_portal_service.is_candidate(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    return user_id


@candidate_router.get("/interviews")
def list_my_interviews(current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _candidate_or_403(current_user)
    return candidate_interview_service.list_my_interviews(user_id)


@candidate_router.post("/interviews/{interview_id}/accept")
def accept_interview(interview_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _candidate_or_403(current_user)
    row = candidate_interview_service.accept(user_id, interview_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found or not actionable.")
    return row


@candidate_router.post("/interviews/{interview_id}/decline")
def decline_interview(interview_id: str, payload: DeclineRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _candidate_or_403(current_user)
    row = candidate_interview_service.decline(user_id, interview_id, payload.reason)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found or not actionable.")
    return row


@candidate_router.post("/interviews/{interview_id}/reschedule-request")
def request_reschedule(interview_id: str, payload: RescheduleRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _candidate_or_403(current_user)
    row = candidate_interview_service.request_reschedule(user_id, interview_id, payload.suggested_date, payload.suggested_start_time, payload.reason)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found or not actionable.")
    return row


@recruiter_router.post("/{interview_id}/reschedule-decision")
def reschedule_decision(interview_id: str, payload: RescheduleDecisionRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    user_id = _recruiter_or_403(current_user)
    # Reuse scheduling_service update by fetching current interview
    current = scheduling_service.get_interview(user_id, interview_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found.")
    if not payload.approve:
        # reject request
        with __import__("app.database.connection", fromlist=["get_connection"]).get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE scheduled_interviews SET reschedule_status='rejected', reschedule_decided_at=now(), updated_at=now() WHERE id=%s", (interview_id,))
            conn.commit()
        return scheduling_service.get_interview(user_id, interview_id)
    # approve: apply requested date/time via update_interview
    from app.schemas.scheduling import ScheduledInterviewUpdate
    from datetime import datetime
    req_date = current.get("reschedule_requested_date")
    req_time = current.get("reschedule_requested_start_time")
    if not req_date or not req_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending reschedule request.")
    # compute end_time
    dur = current.get("duration_minutes") or 30
    from datetime import timedelta
    start_dt = datetime.combine(req_date, req_time)
    end_time = (start_dt + timedelta(minutes=dur)).time()
    upd = ScheduledInterviewUpdate(
        interview_date=req_date,
        start_time=req_time,
        end_time=end_time,
        time_zone=current.get("time_zone") or "UTC",
    )
    updated = scheduling_service.update_interview(user_id, interview_id, upd, recruiter_email=current.get("recruiter_email"))
    # mark response
    with __import__("app.database.connection", fromlist=["get_connection"]).get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE scheduled_interviews SET candidate_response='rescheduled', reschedule_status='approved', reschedule_decided_at=now(), updated_at=now() WHERE id=%s", (interview_id,))
        conn.commit()
    return scheduling_service.get_interview(user_id, interview_id)
