"""Supabase access-token verification.

The frontend sends ``Authorization: Bearer <access_token>``. FastAPI verifies
that token against Supabase Auth before any jobs or candidates request is
processed. The user's ID always comes from Supabase, never from the client.
"""

import logging
import uuid

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Invalid or expired authentication token.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _fetch_supabase_user(token: str) -> dict:
    """Ask Supabase Auth who owns the access token."""
    if not settings.auth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the server.",
        )

    url = f"{settings.supabase_url}/auth/v1/user"
    headers = {
        "apikey": settings.supabase_publishable_key,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code in (401, 403):
        raise _unauthorized()
    if response.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable.",
        )
    if response.status_code != 200:
        raise _unauthorized()

    data = response.json()
    if not isinstance(data, dict) or not data.get("id"):
        raise _unauthorized()
    return data


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """FastAPI dependency that returns the verified Supabase user."""
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise _unauthorized("Missing bearer token.")

    try:
        user = await _fetch_supabase_user(credentials.credentials)
    except HTTPException:
        raise
    except httpx.HTTPError:
        logger.warning("Could not reach Supabase Auth to verify a token.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable.",
        )

    try:
        user_id = str(uuid.UUID(str(user["id"])))
    except (KeyError, TypeError, ValueError):
        raise _unauthorized()

    return {
        "id": user_id,
        "email": user.get("email"),
        "user_metadata": user.get("user_metadata") or {},
    }
