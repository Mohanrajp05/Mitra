"""Schemas for in-app interview reminder notifications."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ReminderType = Literal["24_hour", "1_hour"]
NotificationStatus = Literal["pending", "sent", "read", "cancelled"]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    user_id: UUID
    interview_id: UUID
    notification_type: ReminderType
    title: str
    message: str
    scheduled_at: datetime
    status: NotificationStatus
    created_at: datetime
    read_at: datetime | None = None
    interview_date: date | None = None
    start_time: time | None = None
    candidate_name: str | None = None


class UnreadCountResponse(BaseModel):
    count: int
