

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.security import get_current_user
from app.schemas.job import JobBulkDeleteRequest, JobCreate, JobResponse, JobUpdate
from app.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(current_user: dict = Depends(get_current_user)):
    return job_service.list_jobs(current_user["id"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    current_user: dict = Depends(get_current_user),
):
    return job_service.create_job(current_user["id"], payload)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = job_service.get_job(current_user["id"], job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    return job


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: str,
    payload: JobUpdate,
    current_user: dict = Depends(get_current_user),
):
    job = job_service.update_job(current_user["id"], job_id, payload)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    return job


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_jobs(
    payload: JobBulkDeleteRequest,
    current_user: dict = Depends(get_current_user),
):
    deleted = job_service.delete_jobs(current_user["id"], payload.ids)
    return {"deleted": deleted, "requested": len(payload.ids)}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    deleted = job_service.delete_job(current_user["id"], job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
