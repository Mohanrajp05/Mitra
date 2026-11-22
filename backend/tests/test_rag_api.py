import pytest
from fastapi.testclient import TestClient

from app.api import rag as rag_api
from app.main import app
from app.rag.llm import LLMCredentialsError, LLMError
from app.schemas.rag import (
    JobAnalysis,
    MatchResult,
    SchedulePlan,
)
from app.services import rag_service
from app.services.rag_service import RecordNotFoundError

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeRecord:
    def __init__(self, **overrides):
        values = {
            "document_id": "doc-1",
            "owner_user_id": TEST_USER_ID,
            "source_type": "resume",
            "candidate_id": None,
            "job_id": None,
            "filename": "resume.txt",
            "mime_type": "text/plain",
            "byte_size": 120,
            "content_hash": "abc123",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dimension": 384,
            "chunk_size": 1000,
            "chunk_overlap": 150,
            "chunk_count": 2,
            "created_at": "2026-11-13T00:00:00+00:00",
            "updated_at": "2026-11-13T00:00:00+00:00",
        }
        values.update(overrides)
        self._values = values

    def summary(self):
        return dict(self._values)


class FakeReport:
    def __init__(self):
        self._values = {"scanned": 3, "rebuilt": 2, "skipped": 1, "removed": 0}

    def as_dict(self):
        return dict(self._values)


def make_document_payload(**overrides):
    record = FakeRecord(**overrides)
    return record.summary()


@pytest.fixture
def service_calls(monkeypatch):
    recorded = {}

    def patch(name, coro_factory):
        async def fake(*args, **kwargs):
            recorded[name] = {"args": args, "kwargs": kwargs}
            return await coro_factory(*args, **kwargs)

        monkeypatch.setattr(rag_service, name, fake)

    return recorded, patch


def auth_headers():
    return {"Authorization": "Bearer fake-token"}


def test_upload_document(client, service_calls):
    recorded, patch = service_calls

    async def fake_save(owner, **kwargs):
        return FakeRecord(filename=kwargs["filename"])

    patch("save_document", fake_save)

    response = client.post(
        "/api/rag/documents",
        headers=auth_headers(),
        files={"file": ("resume.txt", b"Python developer resume", "text/plain")},
        data={"source_type": "resume"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == "doc-1"
    assert body["filename"] == "resume.txt"
    assert body["embedding_dimension"] == 384
    assert recorded["save_document"]["args"][0] == TEST_USER_ID
    assert recorded["save_document"]["kwargs"]["source_type"] == "resume"


def test_upload_document_rejects_bad_source_type(client, service_calls):
    response = client.post(
        "/api/rag/documents",
        headers=auth_headers(),
        files={"file": ("resume.txt", b"text", "text/plain")},
        data={"source_type": "invoice"},
    )

    assert response.status_code == 422


def test_list_documents_shape(client, service_calls):
    recorded, patch = service_calls

    async def fake_list(owner):
        return [make_document_payload(document_id="doc-1")]

    patch("list_documents", fake_list)

    response = client.get("/api/rag/documents", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["documents"][0]["document_id"] == "doc-1"
    assert recorded["list_documents"]["args"][0] == TEST_USER_ID


def test_delete_document_returns_204(client, service_calls):
    recorded, patch = service_calls

    async def fake_delete(owner, document_id):
        recorded["delete"] = (owner, document_id)

    patch("delete_document", fake_delete)

    response = client.delete("/api/rag/documents/doc-1", headers=auth_headers())

    assert response.status_code == 204
    assert recorded["delete"] == (TEST_USER_ID, "doc-1")


def test_delete_document_unknown_returns_404(client, service_calls):
    _, patch = service_calls

    async def fake_delete(owner, document_id):
        raise RecordNotFoundError("Document not found.")

    patch("delete_document", fake_delete)

    response = client.delete("/api/rag/documents/missing", headers=auth_headers())

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_reindex(client, service_calls):
    _, patch = service_calls

    async def fake_reindex(owner):
        return FakeReport()

    patch("reindex", fake_reindex)

    response = client.post("/api/rag/documents/reindex", headers=auth_headers())

    assert response.status_code == 200
    assert response.json() == {"scanned": 3, "rebuilt": 2, "skipped": 1, "removed": 0}


def test_query(client, service_calls):
    recorded, patch = service_calls

    class FakeResult:
        query = "Who knows Python?"
        has_evidence = True
        answer = "Jane Doe knows Python."
        sources = [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "chunk_index": 0,
                "score": 0.5,
                "source_type": "resume",
                "filename": "resume.txt",
            }
        ]

    async def fake_query(owner, query, candidate_id=None, job_id=None, top_k=None):
        return FakeResult()

    patch("query", fake_query)

    response = client.post(
        "/api/rag/query",
        headers=auth_headers(),
        json={"query": "Who knows Python?", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Who knows Python?"
    assert body["has_evidence"] is True
    assert body["answer"] == "Jane Doe knows Python."
    assert body["sources"][0]["filename"] == "resume.txt"
    assert recorded["query"]["args"] == (TEST_USER_ID, "Who knows Python?")


def test_query_requires_text(client, service_calls):
    response = client.post(
        "/api/rag/query",
        headers=auth_headers(),
        json={"query": "   "},
    )

    assert response.status_code == 422


def test_job_analysis(client, service_calls):
    recorded, patch = service_calls

    analysis = JobAnalysis(
        title="Backend Engineer",
        required_skills=["Python"],
        summary="Builds APIs.",
    )

    async def fake_analyze(owner, job_id):
        return {"job_id": job_id, "analysis": analysis}

    patch("analyze_job", fake_analyze)

    response = client.post(
        "/api/rag/jobs/job-1/analysis", headers=auth_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "job-1"
    assert body["analysis"]["title"] == "Backend Engineer"
    assert body["analysis"]["required_skills"] == ["Python"]
    assert recorded["analyze_job"]["args"] == (TEST_USER_ID, "job-1")


def test_match_candidate(client, service_calls):
    recorded, patch = service_calls

    match = MatchResult(
        matched_skills=["Python"],
        missing_skills=["SQL"],
        unverified_skills=[],
        relevance="moderate",
        relevance_score=0.6,
        explanation="Partial overlap.",
    )

    async def fake_match(owner, candidate_id, job_id, force_refresh=False):
        return {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "match": match,
            "cache_status": "refresh" if force_refresh else "miss",
            "cached": False,
        }

    patch("match_candidate", fake_match)

    response = client.post(
        "/api/rag/candidates/cand-1/match",
        headers=auth_headers(),
        json={"job_id": "job-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == "cand-1"
    assert body["job_id"] == "job-1"
    assert body["match"]["relevance"] == "moderate"
    assert body["match"]["missing_skills"] == ["SQL"]
    assert recorded["match_candidate"]["args"] == (TEST_USER_ID, "cand-1", "job-1")


def test_communication_draft(client, service_calls):
    recorded, patch = service_calls

    draft = {
        "draft_type": "interview_invitation",
        "subject": "Interview invitation",
        "body": "Would next week work?",
        "requires_approval": True,
    }

    async def fake_draft(owner, draft_type, **kwargs):
        return {
            "candidate_id": kwargs.get("candidate_id"),
            "job_id": kwargs.get("job_id"),
            "draft": draft,
        }

    patch("draft_communication", fake_draft)

    response = client.post(
        "/api/rag/communication",
        headers=auth_headers(),
        json={
            "draft_type": "interview_invitation",
            "candidate_id": "cand-1",
            "job_id": "job-1",
            "custom_notes": "Be friendly.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["subject"] == "Interview invitation"
    assert body["draft"]["requires_approval"] is True
    assert recorded["draft_communication"]["args"] == (
        TEST_USER_ID,
        "interview_invitation",
    )
    assert recorded["draft_communication"]["kwargs"]["custom_notes"] == "Be friendly."


def test_communication_rejects_unknown_draft_type(client):
    response = client.post(
        "/api/rag/communication",
        headers=auth_headers(),
        json={"draft_type": "newsletter"},
    )

    assert response.status_code == 422


def test_schedule_suggestions(client, service_calls):
    recorded, patch = service_calls

    plan = SchedulePlan(
        suggestions=[
            {"date": "2026-11-16", "time": "09:00-10:00", "status": "suggested"},
        ],
        conflicts=[],
    )

    async def fake_schedule(owner, date_start, date_end, busy_slots, **kwargs):
        return {"plan": plan}

    patch("schedule_suggestions", fake_schedule)

    response = client.post(
        "/api/rag/interview-schedule",
        headers=auth_headers(),
        json={
            "date_start": "2026-11-16",
            "date_end": "2026-11-18",
            "busy_slots": ["2026-11-16 11:00-12:00"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["suggestions"][0]["date"] == "2026-11-16"
    assert body["plan"]["suggestions"][0]["status"] == "suggested"
    assert recorded["schedule_suggestions"]["args"] == (
        TEST_USER_ID,
        "2026-11-16",
        "2026-11-18",
        ["2026-11-16 11:00-12:00"],
    )


def test_schedule_rejects_bad_dates(client, service_calls):
    response = client.post(
        "/api/rag/interview-schedule",
        headers=auth_headers(),
        json={
            "date_start": "16/11/2026",
            "date_end": "2026-11-18",
        },
    )

    assert response.status_code == 422


def test_schedule_rejects_reversed_dates(client, service_calls):
    response = client.post(
        "/api/rag/interview-schedule",
        headers=auth_headers(),
        json={
            "date_start": "2026-11-20",
            "date_end": "2026-11-16",
        },
    )

    assert response.status_code == 422


def test_query_rate_limited_returns_502(client, service_calls):
    _, patch = service_calls

    async def fake_query(owner, query, candidate_id=None, job_id=None, top_k=None):
        raise LLMError("The AI service is rate limited. Please retry shortly.")

    patch("query", fake_query)

    response = client.post(
        "/api/rag/query", headers=auth_headers(), json={"query": "Who knows Python?"}
    )

    assert response.status_code == 502
    assert "rate limited" in response.json()["detail"]


def test_query_invalid_ai_credentials_returns_503(client, service_calls):
    _, patch = service_calls

    async def fake_query(owner, query, candidate_id=None, job_id=None, top_k=None):
        raise LLMCredentialsError("The AI service credentials are invalid.")

    patch("query", fake_query)

    response = client.post(
        "/api/rag/query", headers=auth_headers(), json={"query": "Who knows Python?"}
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "not configured correctly" in detail
    assert "PORTKEY" not in detail


def test_rag_endpoints_require_auth(service_calls):
    _, patch = service_calls

    async def fake_list(owner):
        return []

    patch("list_documents", fake_list)

    with TestClient(app) as anonymous:
        response = anonymous.get("/api/rag/documents")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token."


def test_download_document_streams_stored_file(client, monkeypatch, tmp_path):
    file_path = tmp_path / "resume.txt"
    file_path.write_bytes(b"resume-bytes")

    seen = {}

    def fake_open(owner, document_id):
        seen["owner"] = owner
        seen["document_id"] = document_id
        return (file_path, "text/plain", "resume.txt")

    monkeypatch.setattr(rag_service, "open_document_file", fake_open)

    response = client.get(
        "/api/rag/documents/doc-1/file", headers=auth_headers()
    )

    assert response.status_code == 200
    assert seen["owner"] == TEST_USER_ID
    assert seen["document_id"] == "doc-1"
    assert response.content == b"resume-bytes"
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "resume.txt" in disposition


def test_download_document_404_when_not_owned(client, monkeypatch):
    def fake_open(owner, document_id):
        return None

    monkeypatch.setattr(rag_service, "open_document_file", fake_open)

    response = client.get(
        "/api/rag/documents/foreign-doc/file", headers=auth_headers()
    )

    assert response.status_code == 404
