import asyncio
from typing import Any

from app.core.audit import (
    DOCUMENT_DELETED,
    DOCUMENT_UPLOADED,
    DOCUMENTS_REINDEXED,
    get_audit_trail,
)
from app.database import queries
from app.database.connection import get_connection
from app.rag.document_loader import normalize_text
from app.rag.agents.matching_postcheck import finalize_match
from app.rag.agents.candidate_matching_agent import CandidateMatchingAgent
from app.rag.ollama import OllamaError, get_ollama_client
from app.rag.orchestrator import Orchestrator, get_orchestrator
from app.rag.pipeline import PipelineResult, get_rag_pipeline
from app.rag.response_cache import get_response_cache, reset_response_cache
from app.rag.vector_store import get_document_store
from app.schemas.rag import JobAnalysis, MatchResult

SOURCE_TYPES = ("resume", "job_description", "knowledge")


class RagServiceError(RuntimeError):
    pass


class RecordNotFoundError(RagServiceError):
    pass


class RagAgentError(RagServiceError):
    pass


def _get_document_store():
    return get_document_store()


def _get_job(owner_user_id: str, job_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        job = queries.get_job(connection, owner_user_id, job_id)

    if job is None:
        raise RecordNotFoundError("Job not found.")

    return job


def _get_candidate(owner_user_id: str, candidate_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        candidate = queries.get_candidate(connection, owner_user_id, candidate_id)

    if candidate is None:
        raise RecordNotFoundError("Candidate not found.")

    return candidate


def _check_links(
    owner_user_id: str,
    candidate_id: str | None,
    job_id: str | None,
) -> None:
    if not candidate_id and not job_id:
        return

    with get_connection() as connection:
        if candidate_id:
            candidate = queries.get_candidate(connection, owner_user_id, candidate_id)
            if candidate is None:
                raise RecordNotFoundError("Candidate not found.")
        if job_id:
            job = queries.get_job(connection, owner_user_id, job_id)
            if job is None:
                raise RecordNotFoundError("Job not found.")


def _job_text(job: dict[str, Any]) -> str:
    parts = [
        job.get("title") or "",
        job.get("company") or "",
        job.get("description") or "",
    ]
    skills = ", ".join(job.get("required_skills") or [])
    if skills:
        parts.append(f"Required skills: {skills}")
    if job.get("experience_required") is not None:
        parts.append(f"Experience required: {job['experience_required']} years")
    if job.get("location"):
        parts.append(f"Location: {job['location']}")

    return normalize_text("\n".join(part for part in parts if part.strip()))


def _match_retrieval_query(job: dict[str, Any], max_chars: int) -> str:
    """Build a bounded, requirement-focused query for resume retrieval.

    A job description can be much larger than the embedding provider's query
    limit.  The full description is still sent to the analysis agent; this
    shorter query is only used to retrieve relevant chunks from the selected
    candidate's resume.
    """
    parts = [job.get("title") or ""]
    skills = ", ".join(job.get("required_skills") or [])
    if skills:
        parts.append(f"Required skills: {skills}")
    if job.get("experience_required") is not None:
        parts.append(f"Experience required: {job['experience_required']} years")
    if job.get("location"):
        parts.append(f"Location: {job['location']}")
    if job.get("description"):
        parts.append(job["description"])

    return normalize_text("\n".join(part for part in parts if part.strip()))[:max_chars].rstrip()


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("full_name") or "",
        f"Skills: {', '.join(candidate.get('skills') or [])}"
        if candidate.get("skills")
        else "",
    ]
    if candidate.get("experience_years") is not None:
        parts.append(f"Experience: {candidate['experience_years']} years")
    if candidate.get("education"):
        parts.append(f"Education: {candidate['education']}")
    if candidate.get("resume_text"):
        parts.append(candidate["resume_text"])

    return normalize_text("\n".join(part for part in parts if part.strip()))


PLACEHOLDER_RESUME_CHARS = 200


def _resolve_resume_text(
    owner_user_id: str, candidate: dict[str, Any], candidate_id: str
) -> str | None:
    """Return the best available resume text for a candidate.

    When a resume document exists in the document store for this candidate,
    its parsed text always takes precedence over ``candidates.resume_text``
    so that a replaced resume is immediately reflected in matching and the
    candidate profile.  The DB column is only a fallback when no linked
    resume document exists or the document store is unavailable.
    """
    try:
        document_text = _get_document_store().document_text_for(
            owner_user_id, candidate_id=candidate_id, source_type="resume"
        )
    except Exception:
        document_text = None
    if document_text and document_text.strip():
        return document_text

    text = candidate.get("resume_text")
    if text and len(text.strip()) >= PLACEHOLDER_RESUME_CHARS:
        return text

    return text or None


def _agent_output(results: list, agent_name: str, owner_user_id: str) -> Any:
    for result in results:
        if result.agent == agent_name:
            if not result.is_ok:
                raise RagAgentError(
                    f"The {agent_name} agent failed: {result.error}"
                )
            return result.output

    raise RagAgentError(f"The {agent_name} agent did not run.")


def _document_event_id(record: Any) -> str:
    if isinstance(record, dict):
        return str(record.get("document_id") or "")
    return str(getattr(record, "document_id", "") or "")


def _invalidate_match_cache_for_candidate(owner_user_id: str, candidate_id: str) -> None:
    try:
        from app.rag.match_cache import get_match_cache

        get_match_cache().invalidate_candidate(owner_user_id, candidate_id)
    except Exception:
        return


def _cleanup_replaced_resume(
    owner_user_id: str, candidate_id: str, new_record: Any
) -> int:
    """Remove obsolete resume files left behind by a resume replacement.

    After a new resume is saved for a candidate, older resumes for the same
    owner and candidate with a different content hash are deleted so the
    candidate's personal data does not linger in storage. Failures are
    contained: the upload itself always succeeds.
    """
    if isinstance(new_record, dict):
        summary = new_record
    elif hasattr(new_record, "summary"):
        summary = new_record.summary()
    else:
        summary = {}

    new_document_id = str(summary.get("document_id") or "")
    new_hash = str(summary.get("content_hash") or "")

    try:
        documents = _get_document_store().list_documents(owner_user_id)
    except Exception:
        return 0

    removed = 0
    for item in documents:
        if not isinstance(item, dict):
            continue
        if item.get("source_type") != "resume":
            continue
        if item.get("candidate_id") != candidate_id:
            continue
        document_id = str(item.get("document_id") or "")
        if not document_id or document_id == new_document_id:
            continue
        if new_hash and str(item.get("content_hash") or "") == new_hash:
            continue
        try:
            if _get_document_store().delete_document(owner_user_id, document_id):
                get_response_cache().invalidate_user(owner_user_id)
                get_audit_trail().record(
                    DOCUMENT_DELETED,
                    user_id=owner_user_id,
                    resource_id=document_id,
                    detail="resume_replaced",
                )
                removed += 1
        except Exception:
            continue

    if removed:
        _invalidate_match_cache_for_candidate(owner_user_id, candidate_id)
    return removed


async def save_document(
    owner_user_id: str,
    *,
    filename: str,
    data: bytes,
    source_type: str,
    candidate_id: str | None = None,
    job_id: str | None = None,
    content_type: str | None = None,
) -> Any:
    if source_type not in SOURCE_TYPES:
        raise ValueError("source_type must be resume, job_description, or knowledge.")

    await asyncio.to_thread(_check_links, owner_user_id, candidate_id, job_id)

    record = await asyncio.to_thread(
        _get_document_store().save_document,
        owner_user_id,
        filename=filename,
        data=data,
        source_type=source_type,
        candidate_id=candidate_id,
        job_id=job_id,
        content_type=content_type,
    )
    get_response_cache().invalidate_user(owner_user_id)
    get_audit_trail().record(
        DOCUMENT_UPLOADED,
        user_id=owner_user_id,
        resource_id=_document_event_id(record),
    )
    if source_type == "resume" and candidate_id:
        _invalidate_match_cache_for_candidate(owner_user_id, candidate_id)
        await asyncio.to_thread(
            _cleanup_replaced_resume, owner_user_id, candidate_id, record
        )
        # Extract the structured profile from the new resume so the candidate
        # page can show it and stale extraction never survives a replacement.
        # Best-effort: extraction problems must never fail the upload.
        try:
            from app.services import extraction_service  # avoids a cycle

            await extraction_service.extract_profile_for_candidate(
                owner_user_id, candidate_id
            )
        except Exception:
            pass
    return record


async def list_documents(owner_user_id: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_get_document_store().list_documents, owner_user_id)


def open_document_file(
    owner_user_id: str, document_id: str
) -> tuple[Any, str, str] | None:
    """Return (path, mime_type, filename) for the stored original file.

    Ownership is enforced by the document store; None means the document
    does not exist for this user (callers answer with a uniform 404).
    """
    return _get_document_store().open_original(owner_user_id, document_id)


def candidate_resume_package(
    owner_user_id: str, candidate: dict[str, Any]
) -> tuple[str | None, list[dict[str, Any]]]:
    """Resume text and linked resume documents for the candidate profile.

    Returns (resume_text, documents) where resume_text is resolved through
    _resolve_resume_text (DB text preferred, linked document text used when
    the DB value is a short placeholder) and documents lists the resume
    files linked to this candidate in the document store. Store read
    failures degrade to an empty document list so the profile still loads.
    """
    candidate_id = str(candidate.get("id") or "")
    resolved = None
    if candidate_id:
        try:
            resolved = _resolve_resume_text(owner_user_id, candidate, candidate_id)
        except Exception:
            resolved = None

    documents: list[dict[str, Any]] = []
    if candidate_id:
        try:
            for item in _get_document_store().list_documents(owner_user_id):
                if not isinstance(item, dict):
                    continue
                if item.get("source_type") != "resume":
                    continue
                if item.get("candidate_id") != candidate_id:
                    continue
                documents.append(
                    {
                        "document_id": str(item.get("document_id") or ""),
                        "filename": str(item.get("filename") or ""),
                        "mime_type": str(item.get("mime_type") or ""),
                        "byte_size": int(item.get("byte_size") or 0),
                        "chunk_count": int(item.get("chunk_count") or 0),
                        "created_at": str(item.get("created_at") or ""),
                    }
                )
        except Exception:
            documents = []

    return resolved, documents


async def delete_document(owner_user_id: str, document_id: str) -> None:
    store = _get_document_store()
    record = await asyncio.to_thread(store.get_document, owner_user_id, document_id)
    deleted = await asyncio.to_thread(store.delete_document, owner_user_id, document_id)
    if not deleted:
        get_audit_trail().record(
            DOCUMENT_DELETED,
            user_id=owner_user_id,
            resource_id=document_id,
            status="failure",
            detail="document_not_found",
        )
        raise RecordNotFoundError("Document not found.")
    get_response_cache().invalidate_user(owner_user_id)
    # A deleted resume must not keep feeding the candidate page: clear the
    # structured extraction so it is re-derived (lazily) only from text that
    # legitimately remains. Best-effort: the document is already gone.
    if record is not None and record.source_type == "resume" and record.candidate_id:
        _invalidate_match_cache_for_candidate(owner_user_id, record.candidate_id)
        try:
            with get_connection() as connection:
                queries.update_candidate(
                    connection,
                    owner_user_id,
                    record.candidate_id,
                    {"extracted_profile": None},
                )
        except Exception:
            pass
    get_audit_trail().record(
        DOCUMENT_DELETED, user_id=owner_user_id, resource_id=document_id
    )


async def reindex(owner_user_id: str) -> Any:
    report = await asyncio.to_thread(_get_document_store().rebuild_index, owner_user_id)
    get_response_cache().invalidate_user(owner_user_id)
    summary = report.as_dict() if hasattr(report, "as_dict") else str(report)
    get_audit_trail().record(
        DOCUMENTS_REINDEXED,
        user_id=owner_user_id,
        detail=f"summary={summary}",
    )
    return report


async def query(
    owner_user_id: str,
    query: str,
    candidate_id: str | None = None,
    job_id: str | None = None,
    top_k: int | None = None,
    document_ids: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> PipelineResult:
    await asyncio.to_thread(_check_links, owner_user_id, candidate_id, job_id)

    async def load_result() -> PipelineResult:
        run_kwargs: dict[str, Any] = {
            "top_k": top_k,
            "candidate_id": candidate_id,
            "job_id": job_id,
        }
        if document_ids:
            run_kwargs["document_ids"] = document_ids
        if history:
            run_kwargs["history"] = history
        return await get_rag_pipeline().run(owner_user_id, query, **run_kwargs)

    cache_kwargs: dict[str, Any] = {
        "candidate_id": candidate_id,
        "job_id": job_id,
        "top_k": top_k,
    }
    if document_ids:
        cache_kwargs["document_ids"] = document_ids
    return await get_response_cache().get_or_load(
        owner_user_id,
        query,
        load_result,
        **cache_kwargs,
    )


async def analyze_job(owner_user_id: str, job_id: str) -> dict[str, Any]:
    job = await asyncio.to_thread(_get_job, owner_user_id, job_id)
    results = await get_orchestrator().run(
        ["job_analysis"], {"job_text": _job_text(job)}
    )

    return {
        "job_id": job_id,
        "analysis": _agent_output(results, "job_analysis", owner_user_id),
    }


def _match_resume_fingerprint(
    owner_user_id: str, candidate_id: str, resume_text: str | None
) -> str:
    from app.rag.match_cache import _resume_fingerprint

    return _resume_fingerprint(owner_user_id, candidate_id, resume_text)


def _match_job_fingerprint(job: dict[str, Any]) -> str:
    from app.rag.match_cache import _job_fingerprint

    return _job_fingerprint(job)


async def match_candidate(
    owner_user_id: str,
    candidate_id: str,
    job_id: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    job, candidate = await asyncio.gather(
        asyncio.to_thread(_get_job, owner_user_id, job_id),
        asyncio.to_thread(_get_candidate, owner_user_id, candidate_id),
    )

    resume_text = await asyncio.to_thread(
        _resolve_resume_text, owner_user_id, candidate, candidate_id
    )
    if not resume_text:
        raise RagServiceError(
            "No resume text is available for this candidate. Upload a resume first."
        )

    from app.rag.match_cache import _pipeline_fingerprint, get_match_cache

    cache = get_match_cache()
    resume_fp = _match_resume_fingerprint(owner_user_id, candidate_id, resume_text)
    job_fp = _match_job_fingerprint(job)
    key = cache.make_key(
        owner_user_id,
        candidate_id,
        job_id,
        resume_fp,
        job_fp,
        _pipeline_fingerprint(),
    )

    async def compute() -> dict[str, Any]:
        # Matching is intentionally local-only.  Do not invoke the orchestrator:
        # its job-analysis and resume-parsing agents use the Portkey client.
        try:
            match = await CandidateMatchingAgent().match_locally(
                get_ollama_client(),
                job_text=_job_text(job),
                required_skills=list(job.get("required_skills") or []),
                required_experience=job.get("experience_required"),
                resume_text=resume_text,
                candidate_experience=candidate.get("experience_years"),
            )
        except OllamaError as exc:
            raise RagAgentError(str(exc)) from exc

        # Verify the model output against the resume, complete any skills the
        # model overlooked but that the resume demonstrably contains, and
        # recompute the score deterministically from the validated lists. The
        # model's own score is never trusted as-is.
        match, audit = finalize_match(
            match,
            resume_text,
            required_skills=list(job.get("required_skills") or []),
            required_experience=job.get("experience_required"),
            candidate_experience=candidate.get("experience_years"),
        )
        return {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "match": match,
            "audit": audit,
        }

    result, cache_status = await cache.get_or_load(
        owner_user_id,
        candidate_id,
        job_id,
        key,
        compute,
        force_refresh=force_refresh,
    )
    # Return a copy enriched with cache metadata (do not mutate the cached payload).
    payload = dict(result)
    payload["cache_status"] = cache_status
    payload["cached"] = cache_status == "hit"
    return payload


async def draft_communication(
    owner_user_id: str,
    draft_type: str,
    candidate_id: str | None = None,
    job_id: str | None = None,
    custom_notes: str | None = None,
) -> dict[str, Any]:
    job, candidate = await _load_linked(owner_user_id, job_id, candidate_id)

    context = {
        "draft_type": draft_type,
        "job_text": _job_text(job) if job else "",
        "candidate_text": _candidate_text(candidate) if candidate else "",
        "custom_notes": custom_notes or "",
    }
    results = await get_orchestrator().run(["communication"], context)

    return {
        "candidate_id": candidate_id,
        "job_id": job_id,
        "draft": _agent_output(results, "communication", owner_user_id),
    }


async def schedule_suggestions(
    owner_user_id: str,
    date_start: str,
    date_end: str,
    busy_slots: list[str],
    candidate_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    job, candidate = await _load_linked(owner_user_id, job_id, candidate_id)

    context = {
        "date_start": date_start,
        "date_end": date_end,
        "busy_slots": busy_slots,
        "job_text": _job_text(job) if job else "",
        "candidate_text": _candidate_text(candidate) if candidate else "",
    }
    results = await get_orchestrator().run(["interview_scheduling"], context)

    return {"plan": _agent_output(results, "interview_scheduling", owner_user_id)}


async def _load_linked(
    owner_user_id: str, job_id: str | None, candidate_id: str | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    async def load_job():
        return await asyncio.to_thread(_get_job, owner_user_id, job_id) if job_id else None

    async def load_candidate():
        return (
            await asyncio.to_thread(_get_candidate, owner_user_id, candidate_id)
            if candidate_id
            else None
        )

    return await asyncio.gather(load_job(), load_candidate())


def reset_services() -> None:
    from app.rag.orchestrator import reset_orchestrator
    from app.rag.pipeline import reset_rag_pipeline
    from app.rag.response_cache import reset_response_cache
    from app.rag.vector_store import reset_document_store
    from app.rag.match_cache import reset_match_cache

    reset_document_store()
    reset_rag_pipeline()
    reset_orchestrator()
    reset_response_cache()
    reset_match_cache()


__all__ = [
    "RagAgentError",
    "RagServiceError",
    "RecordNotFoundError",
    "analyze_job",
    "delete_document",
    "draft_communication",
    "get_orchestrator",
    "list_documents",
    "match_candidate",
    "query",
    "reindex",
    "reset_services",
    "save_document",
    "schedule_suggestions",
    "Orchestrator",
]
