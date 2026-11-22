"""Chat session and message REST endpoints.

The verified Supabase user ID is always used as the owner. Sessions that belong
to another user are reported as 404 so their existence is not disclosed.
"""

from fastapi import APIRouter, Depends, Response, status

from app.core.audit import RATE_LIMIT_EXCEEDED, get_audit_trail
from app.core.rate_limit import RateLimitExceeded, get_rate_limiter
from app.core.security import get_current_user
from app.schemas.chat import (
    ChatExchangeResponse,
    ChatHistoryDeleteResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionRename,
    ChatSessionResponse,
)
from app.services import chat_service

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.get("/sessions", response_model=list[ChatSessionResponse])
def list_sessions(current_user: dict = Depends(get_current_user)):
    return chat_service.list_sessions(current_user["id"])


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: ChatSessionCreate | None = None,
    current_user: dict = Depends(get_current_user),
):
    return chat_service.create_session(current_user["id"], payload)


@router.delete("/sessions", response_model=ChatHistoryDeleteResponse)
def delete_all_sessions(current_user: dict = Depends(get_current_user)):
    deleted = chat_service.delete_all_sessions(current_user["id"])
    return {"deleted": deleted}


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_session(
    session_id: str,
    payload: ChatSessionRename,
    current_user: dict = Depends(get_current_user),
):
    return chat_service.rename_session(current_user["id"], session_id, payload)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str, current_user: dict = Depends(get_current_user)
):
    chat_service.delete_session(current_user["id"], session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
)
def list_messages(
    session_id: str, current_user: dict = Depends(get_current_user)
):
    return chat_service.list_messages(current_user["id"], session_id)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatExchangeResponse,
)
async def send_message(
    session_id: str,
    payload: ChatMessageCreate,
    current_user: dict = Depends(get_current_user),
):
    allowed, retry_after = get_rate_limiter().acquire(f"chat:{current_user['id']}")
    if not allowed:
        get_audit_trail().record(
            RATE_LIMIT_EXCEEDED,
            user_id=current_user["id"],
            status="failure",
            detail=f"retry_after={retry_after}",
        )
        raise RateLimitExceeded(retry_after)
    return await chat_service.send_message(
        current_user["id"], session_id, payload
    )
