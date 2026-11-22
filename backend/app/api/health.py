"""Health endpoints.

``/api/health`` reports process/configuration status without touching the
database. ``/api/health/db`` runs a real query and only reports success when
PostgreSQL actually answered.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database.connection import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "database_configured": settings.database_configured,
        "auth_configured": settings.auth_configured,
    }


@router.get("/health/db")
def database_health_check():
    """Run a real query against the application database."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database() AS database_name, "
                    "current_user AS database_user, "
                    "version() AS server_version"
                )
                row = cursor.fetchone()
    except Exception as exc:
        # Log the type only: exception text may include connection details.
        logger.warning("Database health check failed (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "unavailable",
                "detail": "Could not connect to the application database.",
            },
        )

    if not row:
        logger.warning("Database health check returned no rows.")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "unavailable",
                "detail": "The database did not return a health result.",
            },
        )

    return {
        "status": "ok",
        "database": "connected",
        "database_name": row["database_name"],
        "database_user": row["database_user"],
        "server_version": row["server_version"].split(",")[0],
    }
