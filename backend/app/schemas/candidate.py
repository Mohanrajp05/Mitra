"""Pydantic schemas for candidate requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.validators import clean_skills, is_valid_email


class CandidateBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    skills: list[str] = Field(default_factory=list, max_length=50)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    education: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)
    resume_text: str | None = Field(default=None, max_length=50_000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_email(value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("phone", "education", "location", "resume_text", mode="before")
    @classmethod
    def empty_text_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        skills = clean_skills(value)
        if any(len(skill) > 80 for skill in skills):
            raise ValueError("Each skill must be 80 characters or fewer.")
        return skills


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    skills: list[str] | None = Field(default=None, max_length=50)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    education: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)
    resume_text: str | None = Field(default=None, max_length=50_000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_email(value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("phone", "education", "location", "resume_text", mode="before")
    @classmethod
    def empty_text_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("full_name")
    @classmethod
    def reject_null_full_name(cls, value):
        # Omitted full_name uses its default and does not reach this validator.
        if value is None:
            raise ValueError("full_name cannot be null.")
        return value

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[str] | None) -> list[str]:
        if value is None:
            raise ValueError("skills cannot be null.")
        skills = clean_skills(value)
        if any(len(skill) > 80 for skill in skills):
            raise ValueError("Each skill must be 80 characters or fewer.")
        return skills


class ResumeDocumentSummary(BaseModel):
    """A resume file linked to a candidate in the document store."""

    document_id: str
    filename: str
    mime_type: str
    byte_size: int
    chunk_count: int
    created_at: str


class CandidateResponse(CandidateBase):
    id: UUID
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime
    # Structured profile extracted from the linked resume (nullable JSONB on
    # the candidates row). NULL until extraction has run for this candidate.
    extracted_profile: dict | None = None
    # Resume files linked to this candidate in the RAG document store.
    # Populated on the candidate detail endpoint; other endpoints return it
    # empty to keep list responses cheap.
    resume_documents: list[ResumeDocumentSummary] = Field(default_factory=list)
