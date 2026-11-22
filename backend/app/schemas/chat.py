"""Pydantic schemas for chat sessions and messages."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.rag import SourceReference

ChatRole = Literal["user", "assistant"]

DEFAULT_SESSION_TITLE = "New conversation"


class ChatSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str = "document"
    document_id: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    score: float | None = None
    source_type: str | None = None
    filename: str | None = None


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str | None = Field(default=None, max_length=200)


class ChatSessionRename(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    owner_user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    content: str = Field(min_length=1, max_length=4_000)
    document_ids: list[str] | None = Field(default=None, max_length=20)
    candidate_id: str | None = None
    job_id: str | None = None
    job_search: bool = False
    job_preferences: dict[str, Any] | None = None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    session_id: UUID
    owner_user_id: UUID
    role: ChatRole
    content: str
    sources: list[ChatSource] = Field(default_factory=list, max_length=20)
    has_evidence: bool = True
    created_at: datetime


class ChatExchangeResponse(BaseModel):
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse


class ChatHistoryDeleteResponse(BaseModel):
    deleted: int
