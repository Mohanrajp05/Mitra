
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class CurrentUserResponse(BaseModel):
    id: UUID
    email: str | None = None
    user_metadata: dict = Field(default_factory=dict)


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(current_user: dict = Depends(get_current_user)):
    """Return the identity that owns the supplied Supabase access token."""
    return CurrentUserResponse(
        id=current_user["id"],
        email=current_user.get("email"),
        user_metadata=current_user.get("user_metadata") or {},
    )
