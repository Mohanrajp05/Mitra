from fastapi import APIRouter, HTTPException, Query, status

from app.services.job_search_service import build_job_url

router = APIRouter(tags=["Job search"])


@router.get("/job-link")
async def job_link(
    source: str = Query(...),
    role: str = Query(...),
    location: str = Query(""),
    fallback: bool = Query(False),
):
    try:
        return {
            "url": build_job_url(
                source, role, location, naukri_fallback=fallback
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
