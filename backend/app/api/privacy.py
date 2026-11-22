"""Privacy REST endpoints: export, account-data deletion, and retention.

Every endpoint uses the verified Supabase user ID as the owner; a recruiter
can only export, delete, or clean up their own data. The Supabase Auth
account itself is never deleted.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.services import privacy_service
from app.services.privacy_service import RetentionConfigError

router = APIRouter(prefix="/api/privacy", tags=["Privacy"])


@router.get("/export")
def export_data(current_user: dict = Depends(get_current_user)):
    return privacy_service.export_owner_data(current_user["id"])


@router.delete("/account-data")
def delete_account_data(current_user: dict = Depends(get_current_user)):
    return privacy_service.delete_account_data(current_user["id"])


@router.get("/retention")
def retention_summary(current_user: dict = Depends(get_current_user)):
    try:
        return privacy_service.expired_summary(current_user["id"])
    except RetentionConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )


@router.post("/retention/cleanup")
def retention_cleanup(current_user: dict = Depends(get_current_user)):
    try:
        return privacy_service.cleanup_expired(current_user["id"])
    except RetentionConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
