import asyncio
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.core.security import get_current_user
from app.schemas.rag import (
    CommunicationRequest,
    CommunicationResponse,
    DocumentListResponse,
    DocumentResponse,
    JobAnalysisResponse,
    MatchRequest,
    MatchResponse,
    RagQueryRequest,
    RagQueryResponse,
    ReindexResponse,
    ScheduleRequest,
    ScheduleResponse,
    SourceReference,
)
from app.services import rag_service
from app.rag.response_cache import get_response_cache

router = APIRouter(prefix="/api/rag", tags=["RAG"])

SourceTypeForm = Literal["resume", "job_description", "knowledge"]


@router.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    source_type: SourceTypeForm = Form("resume"),
    candidate_id: str | None = Form(None),
    job_id: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    data = await file.read()
    record = await rag_service.save_document(
        current_user["id"],
        filename=file.filename or "",
        data=data,
        source_type=source_type,
        candidate_id=candidate_id,
        job_id=job_id,
        content_type=file.content_type,
    )
    return DocumentResponse(**record.summary())


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(current_user: dict = Depends(get_current_user)):
    documents = await rag_service.list_documents(current_user["id"])
    return DocumentListResponse(documents=documents, total=len(documents))


@router.get("/documents/{document_id}/file")
async def download_document_file(
    document_id: str, current_user: dict = Depends(get_current_user)
):
    """Stream the stored original file for one of the user's documents.

    Ownership is enforced inside the document store: a document belonging to
    another user answers with the same 404 as a missing one, and no internal
    storage paths are exposed.
    """
    opened = await asyncio.to_thread(
        rag_service.open_document_file, current_user["id"], document_id
    )
    if opened is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
        )
    path, media_type, filename = opened
    return FileResponse(
        path=path, media_type=media_type, filename=filename
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str, current_user: dict = Depends(get_current_user)
):
    await rag_service.delete_document(current_user["id"], document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/reindex", response_model=ReindexResponse)
async def reindex_documents(current_user: dict = Depends(get_current_user)):
    report = await rag_service.reindex(current_user["id"])
    return ReindexResponse(**report.as_dict())


@router.get("/cache/stats")
async def cache_stats(current_user: dict = Depends(get_current_user)):
    from app.rag.match_cache import get_match_cache

    stats = get_response_cache().stats()
    # Preserve the legacy RAG-only shape for existing consumers and tests.
    stats["rag"] = dict(stats)
    stats["match"] = get_match_cache().stats()
    return stats


@router.post("/query", response_model=RagQueryResponse)
async def query_documents(
    payload: RagQueryRequest, current_user: dict = Depends(get_current_user)
):
    result = await rag_service.query(
        current_user["id"],
        payload.query,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        top_k=payload.top_k,
    )
    return RagQueryResponse(
        query=result.query,
        has_evidence=result.has_evidence,
        answer=result.answer,
        sources=[SourceReference(**item) for item in result.sources],
    )


@router.post("/jobs/{job_id}/analysis", response_model=JobAnalysisResponse)
async def analyze_job(
    job_id: str, current_user: dict = Depends(get_current_user)
):
    return await rag_service.analyze_job(current_user["id"], job_id)


@router.post(
    "/candidates/{candidate_id}/match", response_model=MatchResponse
)
async def match_candidate(
    candidate_id: str,
    payload: MatchRequest,
    current_user: dict = Depends(get_current_user),
):
    return await rag_service.match_candidate(
        current_user["id"],
        candidate_id,
        payload.job_id,
        force_refresh=payload.force_refresh,
    )


@router.post("/communication", response_model=CommunicationResponse)
async def draft_communication(
    payload: CommunicationRequest, current_user: dict = Depends(get_current_user)
):
    return await rag_service.draft_communication(
        current_user["id"],
        payload.draft_type,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        custom_notes=payload.custom_notes,
    )


@router.post("/interview-schedule", response_model=ScheduleResponse)
async def schedule_interview(
    payload: ScheduleRequest, current_user: dict = Depends(get_current_user)
):
    return await rag_service.schedule_suggestions(
        current_user["id"],
        payload.date_start,
        payload.date_end,
        payload.busy_slots,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
    )
