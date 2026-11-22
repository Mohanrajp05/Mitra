"""Authenticated in-app interview notification endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.schemas.notification import NotificationResponse, UnreadCountResponse
from app.services import reminder_service

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationResponse])
def list_notifications(current_user: dict = Depends(get_current_user)):
    return reminder_service.list_notifications(current_user["id"])


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(current_user: dict = Depends(get_current_user)):
    return {"count": reminder_service.unread_count(current_user["id"])}


@router.patch("/read-all", response_model=UnreadCountResponse)
def read_all(current_user: dict = Depends(get_current_user)):
    reminder_service.mark_all_read(current_user["id"])
    return {"count": reminder_service.unread_count(current_user["id"])}


@router.patch("/{reminder_id}/read", response_model=NotificationResponse)
def mark_read(
    reminder_id: str, current_user: dict = Depends(get_current_user)
):
    try:
        return reminder_service.mark_read(current_user["id"], reminder_id)
    except reminder_service.ReminderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
