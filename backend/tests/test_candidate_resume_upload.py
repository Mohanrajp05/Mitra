"""Candidate resume upload lifecycle tests.

Exercises the real FastAPI routes, the real RAG document store (with a fake
embedding service and a temporary data directory) and the candidate service.
Database writes are captured in memory; no PostgreSQL or LLM calls run.
"""

import asyncio
import contextlib

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app
from app.rag import vector_store
from app.rag.config import load_settings
from app.rag.vector_store import LocalVectorStore
from app.services import candidate_portal_service as cps
from app.services import candidate_service, extraction_service, rag_service
from tests.rag_helpers import FakeEmbeddingService, build_docx, build_pdf

CANDIDATE_USER = "22222222-2222-4222-8222-222222222222"
OTHER_USER = "33333333-3333-4333-8333-333333333333"
RECRUITER = "11111111-1111-4111-8111-111111111111"
CANDIDATE_ID = "44444444-4444-4444-8444-444444444444"
RECRUITER_CANDIDATE_ID = "55555555-5555-4555-8555-555555555555"

PDF_TEXT = (
    "Jane Doe is a Python engineer with 6 years of experience building APIs, "
    "PostgreSQL services and AWS infrastructure."
)
DOCX_TEXT = (
    "Jane Doe — Data Engineer. Six years of experience with Python, Airflow "
    "and Snowflake building reliable data pipelines."
)


@pytest.fixture
def profile():
    return {
        "id": CANDIDATE_ID,
        "owner_user_id": CANDIDATE_USER,
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": None,
        "skills": [],
        "experience_years": None,
        "education": None,
        "resume_text": None,
        "extracted_profile": None,
    }


@pytest.fixture
def resume_store(tmp_path, monkeypatch, profile):
    settings = load_settings(
        base_dir=tmp_path,
        embedding_model=FakeEmbeddingService.model_name,
        embedding_dimension=8,
        max_upload_bytes=1024 * 1024,
        max_text_chars=100_000,
    )
    store = LocalVectorStore(
        settings=settings, embedding_service=FakeEmbeddingService()
    )
    vector_store.set_document_store(store)

    def get_profile(uid):
        return profile if uid == CANDIDATE_USER else None

    def update_candidate(connection, owner_user_id, candidate_id, changes):
        assert owner_user_id == CANDIDATE_USER
        assert candidate_id == CANDIDATE_ID
        for key, value in changes.items():
            profile[key] = value
        return dict(profile)

    monkeypatch.setattr(cps, "get_profile", get_profile)
    monkeypatch.setattr(cps, "get_connection", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(rag_service, "get_connection", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(rag_service.queries, "update_candidate", update_candidate)
    monkeypatch.setattr(rag_service, "_check_links", lambda *args, **kwargs: None)

    async def no_extraction(*args, **kwargs):
        return None

    monkeypatch.setattr(
        extraction_service, "extract_profile_for_candidate", no_extraction
    )
    try:
        yield store, profile
    finally:
        vector_store.reset_document_store()


@pytest.fixture
def client(monkeypatch, resume_store):
    app.dependency_overrides[get_current_user] = lambda: {
        "id": CANDIDATE_USER,
        "email": "jane@example.com",
    }
    monkeypatch.setattr(cps, "is_candidate", lambda uid: uid == CANDIDATE_USER)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_user, None)


def post_resume(client, data, filename, content_type):
    return client.post(
        "/api/candidate/resume",
        files={"file": (filename, data, content_type)},
    )


def test_pdf_upload_persists_extracted_text_and_metadata(client, resume_store):
    store, profile = resume_store

    response = post_resume(client, build_pdf(PDF_TEXT), "jane-doe.pdf", "application/pdf")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["has_resume"] is True
    assert body["file"]["filename"] == "jane-doe.pdf"
    assert body["file"]["mime_type"] == "application/pdf"
    assert "Jane Doe" in body["resume_text"]

    # Extracted text is persisted to the candidate row so the profile,
    # recruiter applicant views and matching all see it.
    assert "Jane Doe" in profile["resume_text"]
    documents = store.list_documents(CANDIDATE_USER)
    assert len(documents) == 1
    assert documents[0]["filename"] == "jane-doe.pdf"

    state = client.get("/api/candidate/resume").json()
    assert state["status"] == "uploaded"
    assert state["file"]["filename"] == "jane-doe.pdf"


def test_docx_upload_works(client, resume_store):
    store, profile = resume_store

    response = post_resume(
        client,
        build_docx([DOCX_TEXT]),
        "jane-doe.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["file"]["filename"] == "jane-doe.docx"
    assert "Data Engineer" in body["resume_text"]
    assert "Data Engineer" in profile["resume_text"]
    assert len(store.list_documents(CANDIDATE_USER)) == 1


@pytest.mark.parametrize(
    "filename, data, expected",
    [
        ("resume.txt", b"plain text resume", 415),
        ("resume.exe", b"MZ\x90\x00", 415),
        ("resume.pdf", b"this is not a pdf", 422),
        ("resume.docx", b"not a zip archive", 422),
        # Path traversal / unsafe names are rejected by the loader.
        ("../resume.pdf", build_pdf(PDF_TEXT), 422),
        ("bad\\name.pdf", build_pdf(PDF_TEXT), 422),
    ],
)
def test_invalid_files_are_rejected(client, resume_store, filename, data, expected):
    store, profile = resume_store

    response = post_resume(client, data, filename, "application/octet-stream")

    assert response.status_code == expected
    assert store.list_documents(CANDIDATE_USER) == []
    assert profile["resume_text"] is None


def test_oversized_resume_is_rejected(client, resume_store, monkeypatch):
    import app.api.candidate_portal as candidate_api

    store, profile = resume_store
    monkeypatch.setattr(
        candidate_api, "rag_settings", type("S", (), {"max_upload_bytes": 1024})()
    )

    response = post_resume(
        client, b"%PDF-1.4" + b"0" * 2000, "huge.pdf", "application/pdf"
    )

    assert response.status_code == 413
    assert store.list_documents(CANDIDATE_USER) == []
    assert profile["resume_text"] is None


def test_upload_without_candidate_role_is_forbidden(client, monkeypatch):
    monkeypatch.setattr(cps, "is_candidate", lambda uid: False)

    response = post_resume(
        client, build_pdf(PDF_TEXT), "jane-doe.pdf", "application/pdf"
    )

    assert response.status_code == 403


def test_resume_replacement_removes_previous_file(client, resume_store):
    store, profile = resume_store

    first = post_resume(client, build_pdf(PDF_TEXT), "old-resume.pdf", "application/pdf")
    assert first.status_code == 200

    second = post_resume(
        client, build_pdf("Completely new resume text with Rust and Go."),
        "new-resume.pdf", "application/pdf",
    )
    assert second.status_code == 200
    body = second.json()
    assert body["file"]["filename"] == "new-resume.pdf"

    documents = store.list_documents(CANDIDATE_USER)
    assert len(documents) == 1
    assert documents[0]["filename"] == "new-resume.pdf"
    assert "Rust and Go" in profile["resume_text"]
    assert "Python engineer" not in profile["resume_text"]


def test_resume_removal_clears_file_and_text(client, resume_store):
    store, profile = resume_store

    uploaded = post_resume(client, build_pdf(PDF_TEXT), "jane-doe.pdf", "application/pdf")
    assert uploaded.status_code == 200

    response = client.delete("/api/candidate/resume")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "missing"
    assert body["has_resume"] is False
    assert body["file"] is None
    assert store.list_documents(CANDIDATE_USER) == []
    assert profile["resume_text"] is None
    assert profile["extracted_profile"] is None


def test_pasted_resume_is_still_supported(client, monkeypatch):
    monkeypatch.setattr(
        cps,
        "update_profile",
        lambda uid, changes: {"id": CANDIDATE_ID, **changes},
    )

    response = client.put(
        "/api/candidate/me", json={"resume_text": "Pasted resume text."}
    )

    assert response.status_code == 200
    assert response.json()["resume_text"] == "Pasted resume text."


def test_other_candidate_cannot_read_uploaded_resume(client, resume_store):
    store, _profile = resume_store
    uploaded = post_resume(client, build_pdf(PDF_TEXT), "jane-doe.pdf", "application/pdf")
    assert uploaded.status_code == 200

    # Store access is scoped to the owner.
    assert (
        store.document_text_for(
            OTHER_USER, candidate_id=CANDIDATE_ID, source_type="resume"
        )
        is None
    )
    # Another authenticated candidate has no profile, so the endpoint is 404.
    assert cps.get_resume(OTHER_USER) is None


def test_recruiter_sees_resume_through_authorized_candidate_detail(
    monkeypatch, tmp_path
):
    settings = load_settings(
        base_dir=tmp_path,
        embedding_model=FakeEmbeddingService.model_name,
        embedding_dimension=8,
        max_upload_bytes=1024 * 1024,
    )
    store = LocalVectorStore(
        settings=settings, embedding_service=FakeEmbeddingService()
    )
    vector_store.set_document_store(store)
    try:
        # Simulate a resume linked to a recruiter-owned candidate by the
        # existing recruiter upload flow.
        store.save_document(
            RECRUITER,
            filename="candidate-resume.pdf",
            data=build_pdf(PDF_TEXT),
            source_type="resume",
            candidate_id=RECRUITER_CANDIDATE_ID,
            content_type="application/pdf",
        )
        candidate = {
            "id": RECRUITER_CANDIDATE_ID,
            "owner_user_id": RECRUITER,
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": None,
            "skills": [],
            "experience_years": None,
            "education": None,
            "resume_text": None,
            "extracted_profile": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        monkeypatch.setattr(candidate_service, "get_candidate", lambda uid, cid: candidate)
        monkeypatch.setattr(cps, "is_candidate", lambda uid: False)
        monkeypatch.setattr(
            extraction_service, "extract_profile_deterministic",
            lambda *args, **kwargs: None,
        )

        app.dependency_overrides[get_current_user] = lambda: {
            "id": RECRUITER, "email": "recruiter@example.com"
        }
        try:
            with TestClient(app) as client:
                response = client.get(f"/api/candidates/{RECRUITER_CANDIDATE_ID}")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 200
        body = response.json()
        assert body["resume_documents"][0]["filename"] == "candidate-resume.pdf"
        assert "Jane Doe" in body["resume_text"]

        # A different recruiter cannot access the candidate at all.
        monkeypatch.setattr(
            candidate_service, "get_candidate", lambda uid, cid: None
        )
        app.dependency_overrides[get_current_user] = lambda: {
            "id": OTHER_USER, "email": "other@example.com"
        }
        try:
            with TestClient(app) as other_client:
                denied = other_client.get(f"/api/candidates/{RECRUITER_CANDIDATE_ID}")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert denied.status_code == 404
    finally:
        vector_store.reset_document_store()


def test_service_upload_rejects_when_profile_missing(monkeypatch):
    from app.services.candidate_portal_service import ResumeProfileNotFoundError

    monkeypatch.setattr(cps, "get_profile", lambda uid: None)

    async def call():
        return await cps.upload_resume(
            OTHER_USER, filename="jane.pdf", data=b"%PDF-1.4"
        )

    with pytest.raises(ResumeProfileNotFoundError):
        asyncio.run(call())
