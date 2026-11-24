
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services import candidate_portal_service

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class CurrentUserResponse(BaseModel):
    id: UUID
    email: str | None = None
    user_metadata: dict = Field(default_factory=dict)


class CurrentRoleResponse(BaseModel):
    role: str
    user_id: UUID


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(current_user: dict = Depends(get_current_user)):
    """Return the identity that owns the supplied Supabase access token."""
    return CurrentUserResponse(
        id=current_user["id"],
        email=current_user.get("email"),
        user_metadata=current_user.get("user_metadata") or {},
    )


@router.get("/role", response_model=CurrentRoleResponse)
def read_current_role(current_user: dict = Depends(get_current_user)):
    """Return the role derived from the server-side user_roles table.

    The frontend never supplies its own role: it asks this endpoint, which
    resolves identity from the verified Supabase access token.
    """
    user_id = str(current_user["id"])
    return CurrentRoleResponse(
        role=candidate_portal_service.get_account_role(
            user_id, current_user.get("user_metadata") or {}
        ),
        user_id=user_id,
    )
