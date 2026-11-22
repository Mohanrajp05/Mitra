"""Schemas for persisted interview scheduling (calendar appointments)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

InterviewType = Literal["online", "in_person"]
ScheduledStatus = Literal["scheduled", "completed", "cancelled", "missed"]


class ScheduledInterviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    title: str | None = None
    interview_date: date
    start_time: time
    time_zone: str = "UTC"
    duration_minutes: Literal[10, 30] = 30
    interview_type: InterviewType = "online"
    meeting_link: str | None = None
    location: str | None = None
    notes: str | None = None

    @field_validator("candidate_id", "time_zone")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("title", "meeting_link", "location", "notes")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ScheduledInterviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    interview_date: date | None = None
    start_time: time | None = None
    time_zone: str | None = None
    interview_type: InterviewType | None = None
    meeting_link: str | None = None
    location: str | None = None
    notes: str | None = None
    status: ScheduledStatus | None = None


class ScheduledInterviewResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    user_id: UUID
    candidate_id: UUID
    candidate_name: str | None = None
    candidate_email: str | None = None
    title: str
    interview_date: date
    start_time: time
    end_time: time
    starts_at: datetime
    ends_at: datetime
    duration_minutes: int = 30
    interview_type: InterviewType
    meeting_link: str | None = None
    location: str | None = None
    notes: str | None = None
    status: ScheduledStatus
    time_zone: str = "UTC"
    created_at: datetime
    updated_at: datetime


class AvailabilityResponse(BaseModel):
    candidate_id: str
    interview_date: date
    booked_slots: list[str] = Field(default_factory=list)
