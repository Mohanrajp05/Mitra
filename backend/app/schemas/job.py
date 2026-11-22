"""Pydantic schemas for job requests and responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.validators import clean_skills

JobStatus = Literal["open", "closed"]


class JobBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    experience_required: float | None = Field(default=None, ge=0, le=60)
    location: str | None = Field(default=None, max_length=200)
    status: JobStatus = "open"

    @field_validator("company", "location", mode="before")
    @classmethod
    def empty_text_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("required_skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        skills = clean_skills(value)
        if any(len(skill) > 80 for skill in skills):
            raise ValueError("Each skill must be 80 characters or fewer.")
        return skills


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=20_000)
    required_skills: list[str] | None = Field(default=None, max_length=50)
    experience_required: float | None = Field(default=None, ge=0, le=60)
    location: str | None = Field(default=None, max_length=200)
    status: JobStatus | None = None

    @field_validator("company", "location", mode="before")
    @classmethod
    def empty_text_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("title", "description", "status")
    @classmethod
    def reject_null_required_fields(cls, value):
        # Omitted fields use their default and do not reach this validator.
        if value is None:
            raise ValueError("This field cannot be null.")
        return value

    @field_validator("required_skills")
    @classmethod
    def validate_skills(cls, value: list[str] | None) -> list[str]:
        if value is None:
            raise ValueError("required_skills cannot be null.")
        skills = clean_skills(value)
        if any(len(skill) > 80 for skill in skills):
            raise ValueError("Each skill must be 80 characters or fewer.")
        return skills


class JobResponse(JobBase):
    id: UUID
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime


class JobBulkDeleteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in value:
            try:
                UUID(item)
            except ValueError as exc:
                raise ValueError("Each id must be a valid job id.") from exc
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique
