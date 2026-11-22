"""Mock interview REST endpoints (Part 1 + Part 2)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.security import get_current_user
from app.schemas.interview import (
    InterviewAnswerRequest,
    InterviewAnswerResponse,
    InterviewCompleteReport,
    InterviewQuestionResponse,
    InterviewSessionResponse,
    InterviewStartResponse,
)
from app.services import interview_service
from app.services.interview_service import (
    InterviewError,
    InterviewQuestionNotFoundError,
    InterviewSessionNotFoundError,
    InterviewStateError,
)

router = APIRouter(prefix="/api/interviews", tags=["Interviews"])


def _generation_unavailable(exc: Exception) -> HTTPException:
    """Map an internal generation failure to a safe, retryable response.

    Provider details (URLs, status codes, keys) must never reach the client.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "The AI interviewer is temporarily unavailable. Please try again in a moment."
        ),
        headers={"Retry-After": "5"},
    )


@router.post(
    "/sessions",
    response_model=InterviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(current_user: dict = Depends(get_current_user)):
    return await asyncio.to_thread(interview_service.create_session, current_user["id"])


@router.get("/sessions/current", response_model=InterviewSessionResponse | None)
async def get_current_session(current_user: dict = Depends(get_current_user)):
    return await asyncio.to_thread(interview_service.get_current_session, current_user["id"])


@router.get("/sessions/{session_id}", response_model=InterviewSessionResponse)
async def get_session(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> InterviewSessionResponse:
    try:
        return await asyncio.to_thread(
            interview_service.get_session, current_user["id"], session_id
        )
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/resume",
    response_model=InterviewSessionResponse,
)
async def upload_resume(
    session_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> InterviewSessionResponse:
    data = await file.read()
    try:
        return await interview_service.attach_resume(
            current_user["id"],
            session_id,
            filename=file.filename or "",
            data=data,
            content_type=file.content_type,
        )
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InterviewStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/sessions/{session_id}/resume",
    response_model=InterviewSessionResponse,
)
async def remove_resume(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> InterviewSessionResponse:
    try:
        return await interview_service.remove_resume(current_user["id"], session_id)
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InterviewStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/start",
    response_model=InterviewStartResponse,
)
async def start_interview(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> InterviewStartResponse:
    try:
        result = await interview_service.start_session(current_user["id"], session_id)
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InterviewStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InterviewError as exc:
        raise _generation_unavailable(exc) from exc
    except Exception as exc:  # noqa: BLE001 - provider failures must not surface details
        raise _generation_unavailable(exc) from exc
    return result


@router.get(
    "/sessions/{session_id}/questions",
    response_model=list[InterviewQuestionResponse],
)
async def list_questions(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> list[InterviewQuestionResponse]:
    try:
        return await interview_service.list_questions_for_session(
            current_user["id"], session_id
        )
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/questions/current",
    response_model=InterviewQuestionResponse,
)
async def get_current_question(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> InterviewQuestionResponse:
    try:
        return await interview_service.get_current_question(
            current_user["id"], session_id
        )
    except InterviewQuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InterviewStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InterviewError as exc:
        raise _generation_unavailable(exc) from exc
    except Exception as exc:  # noqa: BLE001 - provider failures must not surface details
        raise _generation_unavailable(exc) from exc


@router.post(
    "/sessions/{session_id}/questions/{question_number}/answer",
    response_model=InterviewAnswerResponse,
)
async def answer_question(
    session_id: str,
    question_number: int,
    payload: InterviewAnswerRequest,
    current_user: dict = Depends(get_current_user),
) -> InterviewAnswerResponse:
    try:
        result = await interview_service.submit_answer(
            current_user["id"],
            session_id,
            question_number,
            payload.answer_text,
        )
    except InterviewQuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InterviewStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InterviewError as exc:
        raise _generation_unavailable(exc) from exc
    except Exception as exc:  # noqa: BLE001 - provider failures must not surface details
        raise _generation_unavailable(exc) from exc
    return result


@router.post(
    "/sessions/{session_id}/complete",
    response_model=InterviewCompleteReport,
)
async def complete_interview(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> InterviewCompleteReport:
    try:
        return await interview_service.complete_interview(
            current_user["id"], session_id
        )
    except InterviewSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InterviewStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
