
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONSENT_TYPES = ("resume_processing",)


class ConsentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    consent_type: str = Field(default="resume_processing")
    granted: bool


class ConsentResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    owner_user_id: UUID
    consent_type: str
    status: str
    decided_at: datetime
    created_at: datetime
    updated_at: datetime
