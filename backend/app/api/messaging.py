"""Two-way messaging REST endpoints (Phase 4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services import candidate_portal_service, messaging_service

candidate_router = APIRouter(prefix="/api/candidate", tags=["Candidate Messaging"])
recruiter_router = APIRouter(prefix="/api", tags=["Messaging"])


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class StartConversationRequest(BaseModel):
    candidate_id: str
    application_id: str | None = None


def _user_id(current_user: dict[str, Any]) -> str:
    uid = str(current_user.get("id") or "")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return uid


@candidate_router.get("/conversations")
def candidate_list_conversations(current_user: dict[str, Any] = Depends(get_current_user)):
    uid = _user_id(current_user)
    if not candidate_portal_service.is_candidate(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required.")
    return messaging_service.list_conversations(uid)


@candidate_router.get("/conversations/{conversation_id}/messages")
def candidate_list_messages(conversation_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    uid = _user_id(current_user)
    if not candidate_portal_service.is_candidate(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required.")
    msgs = messaging_service.list_messages(uid, conversation_id)
    if msgs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return msgs


@candidate_router.post("/conversations/{conversation_id}/messages")
def candidate_send_message(conversation_id: str, payload: SendMessageRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    uid = _user_id(current_user)
    if not candidate_portal_service.is_candidate(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required.")
    msg = messaging_service.send_message(uid, conversation_id, payload.content)
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return msg


@recruiter_router.get("/conversations")
def recruiter_list_conversations(current_user: dict[str, Any] = Depends(get_current_user)):
    uid = _user_id(current_user)
    if candidate_portal_service.is_candidate(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    return messaging_service.list_conversations(uid)


@recruiter_router.post("/conversations")
def recruiter_start_conversation(payload: StartConversationRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    uid = _user_id(current_user)
    if candidate_portal_service.is_candidate(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    conv = messaging_service.start_or_get_conversation(uid, payload.candidate_id, payload.application_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")
    return conv


@recruiter_router.get("/conversations/{conversation_id}/messages")
def recruiter_list_messages(conversation_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    uid = _user_id(current_user)
    if candidate_portal_service.is_candidate(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    msgs = messaging_service.list_messages(uid, conversation_id)
    if msgs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return msgs


@recruiter_router.post("/conversations/{conversation_id}/messages")
def recruiter_send_message(conversation_id: str, payload: SendMessageRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    uid = _user_id(current_user)
    if candidate_portal_service.is_candidate(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    msg = messaging_service.send_message(uid, conversation_id, payload.content)
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return msg
