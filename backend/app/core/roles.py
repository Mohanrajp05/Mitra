"""Role-based dependencies for recruiter-only API routers."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user
from app.services import candidate_portal_service


def require_recruiter(current_user: dict[str, Any] = Depends(get_current_user)) -> str:
    """Reject candidate accounts from recruiter-only APIs.

    ``is_candidate`` is database-backed and fails closed for this guard: if the
    role lookup is unavailable the existing per-endpoint authentication still
    applies, while a confirmed candidate is always rejected.
    """
    user_id = str(current_user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    try:
        role = candidate_portal_service.get_account_role(
            user_id, current_user.get("user_metadata") or {}
        )
    except Exception:  # noqa: BLE001 - role table unavailable; use the safe check
        role = "candidate" if candidate_portal_service.is_candidate(user_id) else "recruiter"
    if role == "candidate":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required.")
    return user_id
