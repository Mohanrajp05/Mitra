"""Structured candidate profile extraction from the linked resume.

Deterministic parsing (app.rag.resume_profile) is always tried first. The
local Ollama model is only consulted when the resume is long enough but the
deterministic parser found nothing (unstructured resumes), and every value
the model returns is verified against the resume text before it is stored:
a claim that does not appear in the resume is dropped, never invented.

Results are stored in ``candidates.extracted_profile`` (nullable JSONB).
Manual candidate fields are never overwritten; on the upload path, empty
manual skills/education may be filled from deterministic extraction only.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from app.core.audit import CANDIDATE_UPDATED, get_audit_trail
from app.database import queries
from app.database.connection import get_connection
from app.rag import resume_profile
from app.rag.agents.matching_postcheck import normalize_text, skill_in_text
from app.rag.agents.resume_parsing_agent import ResumeParsingAgent
from app.rag.ollama import OllamaError, get_ollama_client
from app.schemas.rag import CandidateProfile

# Same threshold rag_service uses to separate a hand-typed placeholder from
# real resume text.
MIN_TEXT_CHARS = 200

_EXPERIENCE_KEYS = ("title", "company", "period")


def _clean_str(value: Any, limit: int) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if text else None


def _contains_normalized(needle: Any, haystack_normalized: str, limit: int) -> str | None:
    """Return the cleaned string only when it appears in the resume text."""
    cleaned = _clean_str(needle, limit)
    if not cleaned:
        return None
    if normalize_text(cleaned) and normalize_text(cleaned) in haystack_normalized:
        return cleaned
    return None


def _is_sparse(profile: dict) -> bool:
    return not (
        profile["skills"]
        or profile["experience"]
        or profile["education"]
        or profile["certifications"]
        or profile["summary"]
    )


def _validate_llm_profile(
    parsed: CandidateProfile, resume_text: str
) -> dict:
    """Keep only model output that literally appears in the resume text."""
    normalized_text = normalize_text(resume_text)
    skills = []
    for skill in parsed.skills:
        cleaned = _clean_str(skill, 80)
        if cleaned and skill_in_text(cleaned, normalized_text) and cleaned not in skills:
            skills.append(cleaned)
    education = _contains_normalized(parsed.education, normalized_text, 500)
    certifications = []
    for item in parsed.certifications:
        cleaned = _contains_normalized(item, normalized_text, 300)
        if cleaned and cleaned not in certifications:
            certifications.append(cleaned)
    return {
        "full_name": _contains_normalized(parsed.full_name, normalized_text, 200),
        "email": _contains_normalized(parsed.email, normalized_text, 254),
        "phone": _contains_normalized(parsed.phone, normalized_text, 30),
        "summary": _contains_normalized(parsed.experience_summary, normalized_text, 2_000),
        "skills": skills[: resume_profile.MAX_SKILLS],
        "education": [education] if education else [],
        "certifications": certifications[: resume_profile.MAX_CERTIFICATIONS],
        "experience": [],
    }


async def _llm_extract(resume_text: str) -> CandidateProfile | None:
    """Parse an unstructured resume with the local Ollama model. Fails soft.

    Uses the ResumeParsingAgent prompt (which forbids inventing details) but
    runs on the local Ollama client, like candidate matching, so no external
    LLM tokens are spent on resume parsing.
    """
    try:
        return await get_ollama_client().complete_structured(
            CandidateProfile,
            ResumeParsingAgent.system_prompt,
            f"Resume text:\n{resume_text}",
        )
    except (OllamaError, ValueError):
        return None


def _merge_profiles(deterministic: dict, llm_fields: dict | None) -> dict:
    """Deterministic sections win; verified model output fills the gaps."""
    merged = dict(deterministic)
    if not llm_fields:
        return merged
    for key in ("summary", "email", "phone", "full_name"):
        if not merged.get(key):
            merged[key] = llm_fields.get(key)
    if not merged["skills"]:
        merged["skills"] = llm_fields["skills"]
    if not merged["education"]:
        merged["education"] = llm_fields["education"]
    if not merged["certifications"]:
        merged["certifications"] = llm_fields["certifications"]
    # Structured experience entries are never taken from the model: the
    # deterministic parser is the only source for title/company/period.
    return merged


def _store_shape(merged: dict, method: str) -> dict:
    experience = []
    for entry in merged.get("experience") or []:
        cleaned = {key: _clean_str(entry.get(key), 120) for key in _EXPERIENCE_KEYS}
        if any(cleaned.values()):
            experience.append(cleaned)
    return {
        "summary": merged.get("summary"),
        "skills": merged.get("skills") or [],
        "experience": experience,
        "education": merged.get("education") or [],
        "certifications": merged.get("certifications") or [],
        "total_years": merged.get("total_years"),
        "contact": {"email": merged.get("email"), "phone": merged.get("phone")},
        "extraction_method": method,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def store_extracted_profile(
    owner_user_id: str, candidate_id: str, profile: dict | None
) -> dict | None:
    value = Jsonb(profile) if profile is not None else None
    with get_connection() as connection:
        return queries.update_candidate(
            connection,
            owner_user_id,
            candidate_id,
            {"extracted_profile": value},
        )


def _fill_manual_fields(owner_user_id: str, candidate: dict, deterministic: dict) -> None:
    """Fill EMPTY manual fields from deterministic extraction only.

    Existing manual values are never overwritten; unsupported/empty extracted
    values never reach the manual record.
    """
    changes: dict[str, Any] = {}
    if not (candidate.get("skills") or []) and deterministic.get("skills"):
        changes["skills"] = deterministic["skills"][:50]
    if not (candidate.get("education") or "").strip() and deterministic.get("education"):
        changes["education"] = " | ".join(deterministic["education"])[:500]
    if not changes:
        return
    with get_connection() as connection:
        updated = queries.update_candidate(
            connection, owner_user_id, str(candidate.get("id")), changes
        )
    if updated is not None:
        get_audit_trail().record(
            CANDIDATE_UPDATED,
            user_id=owner_user_id,
            resource_id=str(candidate.get("id")),
            detail=f"fields={','.join(sorted(changes))} (extracted from resume)",
        )


def extract_profile_deterministic(
    owner_user_id: str, candidate: dict, resume_text: str | None
) -> dict | None:
    """Deterministic-only extraction, persisted; safe to call from GET paths."""
    text = resume_text or ""
    if len(text.strip()) < MIN_TEXT_CHARS:
        return None
    sections = resume_profile.extract_profile_sections(text)
    profile = _store_shape(sections, "deterministic")
    stored = store_extracted_profile(owner_user_id, str(candidate.get("id")), profile)
    if stored is None:
        return None
    _fill_manual_fields(owner_user_id, candidate, sections)
    return profile


async def extract_profile_for_candidate(
    owner_user_id: str,
    candidate_id: str,
    *,
    candidate: dict[str, Any] | None = None,
    resume_text: str | None = None,
    allow_llm: bool = True,
) -> dict | None:
    """Full extraction: deterministic first, local model only when needed.

    Called after a resume upload links a document to the candidate.
    Never raises: extraction problems must not fail the upload.
    """
    from app.services import rag_service  # deferred import avoids a cycle

    if candidate is None:
        candidate = await asyncio.to_thread(
            rag_service._get_candidate, owner_user_id, candidate_id
        )
    if not candidate:
        return None
    if resume_text is None:
        resume_text = await asyncio.to_thread(
            rag_service._resolve_resume_text,
            owner_user_id,
            candidate,
            candidate_id,
        )
    text = resume_text or ""
    if len(text.strip()) < MIN_TEXT_CHARS:
        return None

    sections = resume_profile.extract_profile_sections(text)
    method = "deterministic"
    llm_fields = None
    if _is_sparse(sections) and allow_llm:
        parsed = await _llm_extract(text)
        if parsed is not None:
            llm_fields = _validate_llm_profile(parsed, text)
            if any(
                llm_fields[key]
                for key in ("summary", "skills", "education", "certifications")
            ):
                method = "ollama_assisted"
            else:
                llm_fields = None

    merged = _merge_profiles(sections, llm_fields)
    profile = _store_shape(merged, method)
    stored = await asyncio.to_thread(
        store_extracted_profile, owner_user_id, str(candidate.get("id")), profile
    )
    if stored is None:
        return None
    await asyncio.to_thread(_fill_manual_fields, owner_user_id, candidate, sections)
    return profile
