"""Tests for structured candidate profile extraction (Stage 2).

Covers: deterministic extraction and persistence, manual-field protection
(never overwrite, never fill with unsupported values), verified Ollama
fallback for unstructured resumes, failure containment, the upload hook and
the non-destructive migration guard.
"""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services import extraction_service
from app.services import rag_service
from app.schemas.rag import CandidateProfile

OWNER = "owner-extract"
CANDIDATE_ID = "cand-extract"

STRUCTURED_RESUME = (
    "Jane Doe\nSenior Cloud Engineer\njane.doe@example.com\n\n"
    "Summary\nCloud engineer with 8 years of experience across AWS and Azure.\n\n"
    "Professional Experience\nSenior Cloud Engineer at Acme Corp, 2019 - Present\n\n"
    "Skills: AWS, Azure, Docker, Kubernetes, Terraform, Python\n\n"
    "Education\nB.Tech Computer Science, NIT Trichy, 2014\n"
)

UNSTRUCTURED_RESUME = (
    "Jane Doe builds web applications with React and Node.js and has "
    "shipped several production projects for clients over the last few "
    "years, covering dashboards, reports and internal tools. She also "
    "enjoys mentoring junior developers at her current company."
)


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    def cursor(self):
        return FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@contextmanager
def fake_connection():
    yield FakeConnection()


def make_queries_recording(changes: list):
    class FakeQueries:
        @staticmethod
        def update_candidate(connection, owner, candidate_id, change_dict):
            changes.append((owner, candidate_id, change_dict))
            return {"id": candidate_id, **change_dict}

    return FakeQueries


def run(coroutine):
    return asyncio.run(coroutine)


def patch_candidate_and_text(monkeypatch, candidate, resume_text):
    from app.services import rag_service as rs

    monkeypatch.setattr(rs, "_get_candidate", lambda owner, cand_id: candidate)
    monkeypatch.setattr(
        rs, "_resolve_resume_text", lambda owner, cand, cand_id: resume_text
    )


def test_deterministic_extraction_stores_profile(monkeypatch):
    stored = {}
    monkeypatch.setattr(extraction_service, "store_extracted_profile",
                        lambda owner, cand_id, profile: stored.setdefault("profile", profile))
    monkeypatch.setattr(extraction_service, "_fill_manual_fields", lambda *a: None)
    patch_candidate_and_text(
        monkeypatch, {"id": CANDIDATE_ID, "skills": [], "education": None}, STRUCTURED_RESUME
    )

    profile = run(
        extraction_service.extract_profile_for_candidate(OWNER, CANDIDATE_ID)
    )

    assert stored["profile"] is profile
    assert profile["extraction_method"] == "deterministic"
    assert profile["skills"] == ["AWS", "Azure", "Docker", "Kubernetes", "Terraform", "Python"]
    assert profile["experience"] == [
        {"title": "Senior Cloud Engineer", "company": "Acme Corp", "period": "2019 - Present"}
    ]
    assert profile["summary"].startswith("Cloud engineer with 8 years")
    assert profile["total_years"] == 8.0
    assert profile["contact"]["email"] == "jane.doe@example.com"
    assert profile["extracted_at"]


def test_manual_fields_are_filled_only_when_empty(monkeypatch):
    changes = []
    monkeypatch.setattr(extraction_service, "queries", make_queries_recording(changes))
    monkeypatch.setattr(extraction_service, "get_connection", fake_connection)

    empty = {"id": CANDIDATE_ID, "skills": [], "education": None}
    extraction_service._fill_manual_fields(
        OWNER, empty, {"skills": ["AWS", "Terraform"], "education": ["B.Tech CS"]}
    )
    filled = changes[-1][2]
    assert filled == {"skills": ["AWS", "Terraform"], "education": "B.Tech CS"}

    # Existing manual values are never overwritten, not even with other
    # extracted values.
    changes.clear()
    manual = {"id": CANDIDATE_ID, "skills": ["Java"], "education": "MBA"}
    extraction_service._fill_manual_fields(
        OWNER, manual, {"skills": ["AWS"], "education": ["B.Tech CS"]}
    )
    assert changes == []


def test_empty_or_unsupported_values_never_fill_manual_fields(monkeypatch):
    changes = []
    monkeypatch.setattr(extraction_service, "queries", make_queries_recording(changes))
    monkeypatch.setattr(extraction_service, "get_connection", fake_connection)

    extraction_service._fill_manual_fields(
        OWNER, {"id": CANDIDATE_ID, "skills": [], "education": None}, {}
    )
    assert changes == []


def test_ollama_fallback_for_unstructured_resume_and_invention_filter(monkeypatch):
    class FakeOllama:
        async def complete_structured(self, model_cls, system_prompt, user_prompt):
            assert model_cls is CandidateProfile
            assert "never invent" in system_prompt.lower()
            assert "React" in user_prompt
            # One real skill, one invented, one fabricated summary.
            return CandidateProfile(
                full_name="Jane Doe",
                skills=["React", "Kubernetes clusters on Mars"],
                experience_summary=" builds web applications with React and Node.js",
                education="PhD from Atlantis University",
                certifications=[],
            )

    stored = {}
    monkeypatch.setattr(extraction_service, "store_extracted_profile",
                        lambda owner, cand_id, profile: stored.setdefault("profile", profile))
    monkeypatch.setattr(extraction_service, "_fill_manual_fields", lambda *a: None)
    monkeypatch.setattr(extraction_service, "get_ollama_client", lambda: FakeOllama())
    patch_candidate_and_text(
        monkeypatch, {"id": CANDIDATE_ID, "skills": [], "education": None}, UNSTRUCTURED_RESUME
    )

    profile = run(
        extraction_service.extract_profile_for_candidate(OWNER, CANDIDATE_ID)
    )

    assert profile["extraction_method"] == "ollama_assisted"
    # Only the skill that appears in the resume survives.
    assert profile["skills"] == ["React"]
    # The summary quotes the resume almost verbatim, so it is kept
    # (evidence-backed); a fabricated summary would be dropped instead.
    assert profile["summary"] == "builds web applications with React and Node.js"
    # Fabricated education never enters the profile.
    assert profile["education"] == []


def test_ollama_failure_is_contained(monkeypatch):
    from app.rag.ollama import OllamaError

    class BrokenOllama:
        async def complete_structured(self, *args, **kwargs):
            raise OllamaError("Ollama is unavailable.")

    stored = {}
    monkeypatch.setattr(extraction_service, "store_extracted_profile",
                        lambda owner, cand_id, profile: stored.setdefault("profile", profile))
    monkeypatch.setattr(extraction_service, "_fill_manual_fields", lambda *a: None)
    monkeypatch.setattr(extraction_service, "get_ollama_client", lambda: BrokenOllama())
    patch_candidate_and_text(
        monkeypatch, {"id": CANDIDATE_ID, "skills": [], "education": None}, UNSTRUCTURED_RESUME
    )

    profile = run(
        extraction_service.extract_profile_for_candidate(OWNER, CANDIDATE_ID)
    )

    assert profile["extraction_method"] == "deterministic"


def test_placeholder_text_is_never_extracted(monkeypatch):
    stored = []
    monkeypatch.setattr(extraction_service, "store_extracted_profile",
                        lambda *a: stored.append(a))
    patch_candidate_and_text(
        monkeypatch, {"id": CANDIDATE_ID}, "Short hand-typed placeholder."
    )

    assert run(extraction_service.extract_profile_for_candidate(OWNER, CANDIDATE_ID)) is None
    assert stored == []


def test_extraction_never_fails_the_upload(monkeypatch):
    """The save_document hook swallows extraction errors."""
    saved = iter([{"document_id": "doc-new", "source_type": "resume",
                   "candidate_id": CANDIDATE_ID, "content_hash": "h1"}])

    class SaveStore:
        def save_document(self, owner_user_id, **kwargs):
            return next(saved)

        def list_documents(self, owner_user_id):
            return []

        def delete_document(self, owner_user_id, document_id):
            return True

    async def broken_extraction(*args, **kwargs):
        raise RuntimeError("extraction exploded")

    monkeypatch.setattr(rag_service, "_get_document_store", lambda: SaveStore())
    monkeypatch.setattr(rag_service, "_check_links", lambda *a, **k: None)
    monkeypatch.setattr(
        rag_service,
        "get_audit_trail",
        lambda: type("A", (), {"record": staticmethod(lambda *a, **k: None)})(),
    )
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: SimpleNamespace(
        invalidate_user=lambda *a, **k: None))
    from app.services import extraction_service as es
    monkeypatch.setattr(es, "extract_profile_for_candidate", broken_extraction)

    record = run(
        rag_service.save_document(
            OWNER,
            filename="resume.pdf",
            data=b"resume",
            source_type="resume",
            candidate_id=CANDIDATE_ID,
        )
    )

    assert record["document_id"] == "doc-new"


def test_lazy_deterministic_backfill_stores_once(monkeypatch):
    stored = {}
    monkeypatch.setattr(extraction_service, "store_extracted_profile",
                        lambda owner, cand_id, profile: stored.setdefault("profile", profile))
    monkeypatch.setattr(extraction_service, "_fill_manual_fields", lambda *a: None)

    profile = extraction_service.extract_profile_deterministic(
        OWNER, {"id": CANDIDATE_ID, "skills": [], "education": None}, STRUCTURED_RESUME
    )

    assert profile is stored["profile"]
    assert profile["extraction_method"] == "deterministic"


def test_lazy_backfill_skips_short_text():
    assert (
        extraction_service.extract_profile_deterministic(
            OWNER, {"id": CANDIDATE_ID}, "tiny"
        )
        is None
    )


def test_migration_003_is_allowed_and_destructive_statements_are_refused():
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import apply_migration

    migration_sql = (
        Path(__file__).resolve().parents[2]
        / "database"
        / "migrations"
        / "003_candidate_extracted_profile.sql"
    ).read_text(encoding="utf-8")
    assert not apply_migration.FORBIDDEN.search(migration_sql)

    for bad in (
        "DROP TABLE candidates;",
        "DELETE FROM candidates;",
        "TRUNCATE candidates;",
        "ALTER TABLE candidates DROP COLUMN resume_text;",
        "ALTER TABLE candidates ALTER COLUMN skills TYPE text;",
    ):
        assert apply_migration.FORBIDDEN.search(bad), bad
