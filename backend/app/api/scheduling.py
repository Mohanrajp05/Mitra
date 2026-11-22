"""REST endpoints for persisted interview scheduling.

The authenticated Supabase user ID is always the interviewer/owner; candidate
IDs from the client are authorized against that user's own candidate records.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.schemas.scheduling import (
    AvailabilityResponse,
    ScheduledInterviewCreate,
    ScheduledInterviewResponse,
    ScheduledInterviewUpdate,
)
from app.services import scheduling_service

router = APIRouter(prefix="/api/scheduled-interviews", tags=["Scheduled Interviews"])


def _raise_scheduling_error(exc: scheduling_service.SchedulingError) -> None:
    if isinstance(exc, scheduling_service.SchedulingNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, scheduling_service.SchedulingConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, scheduling_service.SchedulingValidationError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post(
    "", response_model=ScheduledInterviewResponse, status_code=status.HTTP_201_CREATED
)
def create_interview(
    payload: ScheduledInterviewCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        return scheduling_service.create_interview(
            current_user["id"], payload, recruiter_email=current_user.get("email")
        )
    except scheduling_service.SchedulingError as exc:
        _raise_scheduling_error(exc)


@router.get("", response_model=list[ScheduledInterviewResponse])
def list_interviews(
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: dict = Depends(get_current_user),
):
    return scheduling_service.list_interviews(
        current_user["id"], date_from=date_from, date_to=date_to
    )


@router.get("/availability", response_model=AvailabilityResponse)
def get_availability(
    candidate_id: str,
    interview_date: date,
    current_user: dict = Depends(get_current_user),
):
    try:
        return scheduling_service.availability(
            current_user["id"], candidate_id, interview_date
        )
    except scheduling_service.SchedulingError as exc:
        _raise_scheduling_error(exc)


@router.get("/{interview_id}", response_model=ScheduledInterviewResponse)
def get_interview(
    interview_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        return scheduling_service.get_interview(current_user["id"], interview_id)
    except scheduling_service.SchedulingError as exc:
        _raise_scheduling_error(exc)


@router.patch("/{interview_id}", response_model=ScheduledInterviewResponse)
def update_interview(
    interview_id: str,
    payload: ScheduledInterviewUpdate,
    current_user: dict = Depends(get_current_user),
):
    try:
        return scheduling_service.update_interview(
            current_user["id"],
            interview_id,
            payload,
            recruiter_email=current_user.get("email"),
        )
    except scheduling_service.SchedulingError as exc:
        _raise_scheduling_error(exc)
