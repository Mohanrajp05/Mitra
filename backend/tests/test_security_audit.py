"""Stage 9 security audit tests.

Targeted tests for gaps not already covered by Stage 1-8 suites:
authentication coverage for every protected router, CORS, path-traversal
defense in the document store, SQL-injection parameterization, malformed
bodies, oversized uploads, and the Retry-After contract on the chat route.
"""

from fastapi.testclient import TestClient

from app.core import security
from app.main import app
from app.rag.document_loader import DocumentError, validate_filename
from app.rag.vector_store import LocalVectorStore
from tests.rag_helpers import FakeEmbeddingService, make_settings
from tests.test_chat_service import FakeConnection

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"

JOB_ROW = {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "owner_user_id": TEST_USER_ID,
    "title": "Junior Python Developer",
    "company": "Fictional Demo Company",
    "description": "Build small internal tools with Python and FastAPI.",
    "required_skills": ["Python", "FastAPI"],
    "experience_required": 1.0,
    "location": "Remote",
    "status": "open",
    "created_at": "2026-01-10T10:00:00Z",
    "updated_at": "2026-01-10T10:00:00Z",
}


class TestAuthenticationCoverage:
    def test_every_protected_router_rejects_anonymous_requests(self):
        protected = [
            ("get", "/api/jobs"),
            ("post", "/api/jobs"),
            ("get", "/api/candidates"),
            ("post", "/api/candidates"),
            ("put", "/api/candidates/33333333-3333-4333-8333-333333333333"),
            (
                "delete",
                "/api/candidates/33333333-3333-4333-8333-333333333333",
            ),
            ("get", "/api/candidates/33333333-3333-4333-8333-333333333333/consent"),
            ("get", "/api/chat/sessions"),
            ("post", "/api/chat/sessions"),
            (
                "delete",
                "/api/chat/sessions/44444444-4444-4444-8444-444444444444",
            ),
            (
                "post",
                "/api/chat/sessions/44444444-4444-4444-8444-444444444444/messages",
            ),
            ("get", "/api/rag/documents"),
            ("post", "/api/rag/query"),
            ("delete", "/api/privacy/account-data"),
        ]

        with TestClient(app) as client:
            for method, url in protected:
                kwargs = {"json": {}} if method in ("post", "put") else {}
                response = getattr(client, method)(url, **kwargs)
                assert response.status_code == 401, f"{method.upper()} {url}"

    def test_garbage_bearer_token_is_rejected_everywhere(self, monkeypatch):
        async def fake_fetch(token: str):
            raise security._unauthorized()

        monkeypatch.setattr(security, "_fetch_supabase_user", fake_fetch)

        with TestClient(app) as client:
            response = client.get(
                "/api/jobs", headers={"Authorization": "Bearer not-a-jwt"}
            )

        assert response.status_code == 401

    def test_identity_never_comes_from_the_request_body(self, client, monkeypatch):
        connection = FakeConnection([])
        captured = []

        original_execute = connection.cursor_instance.execute

        def execute(sql, params=None):
            captured.append((sql, params))
            return original_execute(sql, params)

        connection.cursor_instance.execute = execute

        from contextlib import contextmanager

        @contextmanager
        def fake_get_connection():
            yield connection

        monkeypatch.setattr(
            "app.api.jobs.job_service.get_connection", fake_get_connection
        )

        spoofed = "99999999-9999-4999-8999-999999999999"
        response = client.post(
            "/api/jobs",
            json={
                "owner_user_id": spoofed,
                "title": "Backend Engineer",
                "description": "Build APIs.",
            },
        )

        assert response.status_code == 422
        assert captured == []


class TestCorsConfiguration:
    def test_allowed_origin_preflight_is_accepted(self, client):
        response = client.options(
            "/api/jobs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == (
            "http://localhost:5173"
        )

    def test_loopback_alias_is_accepted_for_local_vite(self, client):
        response = client.options(
            "/api/jobs",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == (
            "http://127.0.0.1:5173"
        )

    def test_disallowed_origin_is_not_granted_access(self, client):
        response = client.options(
            "/api/jobs",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.headers.get("access-control-allow-origin") is None

    def test_response_carries_cors_headers_for_allowed_origin(self, client):
        response = client.get(
            "/api/health", headers={"Origin": "http://localhost:5173"}
        )

        assert response.status_code == 200
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:5173"
        )


class TestInputHardening:
    def test_malformed_json_body_is_rejected_cleanly(self, client):
        response = client.post(
            "/api/jobs",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
        assert "Traceback" not in response.text

    def test_unknown_fields_are_rejected(self, client):
        response = client.post(
            "/api/jobs",
            json={
                "title": "Backend Engineer",
                "description": "Build APIs.",
                "is_admin": True,
            },
        )

        assert response.status_code == 422

    def test_file_too_large_error_maps_to_413(self, client, monkeypatch):
        class FakeStore:
            def save_document(self, owner_user_id, **kwargs):
                from app.rag.document_loader import FileTooLargeError

                raise FileTooLargeError("The file exceeds the 5 MB limit.")

        monkeypatch.setattr("app.api.rag.rag_service._get_document_store", lambda: FakeStore())

        response = client.post(
            "/api/rag/documents",
            files={"file": ("big.txt", b"x" * 100, "text/plain")},
            data={"source_type": "resume"},
        )

        assert response.status_code == 413

    def test_path_traversal_filename_is_rejected(self):
        for malicious in ("../evil.txt", "..\\evil.txt", "a/b.txt", ".."):
            with __import__("pytest").raises(DocumentError):
                validate_filename(malicious)

    def test_document_store_never_writes_outside_its_directory(self, rag_dir):
        settings = make_settings(rag_dir)
        store = LocalVectorStore(settings, FakeEmbeddingService(8))

        import pytest

        from app.rag.document_loader import DocumentError

        with pytest.raises(DocumentError):
            store.save_document(
                TEST_USER_ID,
                filename="../escape.txt",
                data=b"content",
                source_type="resume",
            )

        assert not (rag_dir.parent / "escape.txt").exists()
        assert not (rag_dir / "escape.txt").exists()


class TestSqlInjectionHardening:
    def test_user_input_is_always_a_bound_parameter(self, client, monkeypatch):
        connection = FakeConnection([JOB_ROW])

        from contextlib import contextmanager

        @contextmanager
        def fake_get_connection():
            yield connection

        monkeypatch.setattr(
            "app.api.jobs.job_service.get_connection", fake_get_connection
        )

        payload = "Robert'); DROP TABLE jobs;--"
        response = client.post(
            "/api/jobs",
            json={"title": payload, "description": payload},
        )

        assert response.status_code == 201
        executed = connection.cursor_instance.executed
        assert executed, "the request never reached the query layer"
        for sql, params in executed:
            assert payload not in sql
            assert any(payload == part or payload in str(part) for part in params)

    def test_job_title_with_quotes_survives_as_data(self, client, monkeypatch):
        connection = FakeConnection([JOB_ROW])

        from contextlib import contextmanager

        @contextmanager
        def fake_get_connection():
            yield connection

        monkeypatch.setattr(
            "app.api.jobs.job_service.get_connection", fake_get_connection
        )

        response = client.post(
            "/api/jobs",
            json={
                "title": "O'Brien's Team; DELETE FROM candidates",
                "description": "x",
            },
        )

        assert response.status_code == 201
        sql, params = connection.cursor_instance.executed[-1]
        assert "DELETE FROM candidates" not in sql
        assert params[1] == "O'Brien's Team; DELETE FROM candidates"


class TestRateLimitHeaders:
    def test_chat_429_includes_retry_after(self, client, monkeypatch):
        from app.api import chat as chat_module
        from app.schemas.chat import ChatMessageResponse
        from datetime import datetime, timezone

        async def fake_send(*args, **kwargs):
            return {
                "user_message": {
                    "id": "55555555-5555-4555-8555-555555555555",
                    "session_id": "44444444-4444-4444-8444-444444444444",
                    "owner_user_id": TEST_USER_ID,
                    "role": "user",
                    "content": "sent",
                    "sources": [],
                    "has_evidence": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                "assistant_message": {
                    "id": "66666666-6666-4666-8666-666666666666",
                    "session_id": "44444444-4444-4444-8444-444444444444",
                    "owner_user_id": TEST_USER_ID,
                    "role": "assistant",
                    "content": "reply",
                    "sources": [],
                    "has_evidence": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            }

        monkeypatch.setattr(chat_module.chat_service, "send_message", fake_send)
        limiter = chat_module.get_rate_limiter()
        limiter.max_requests = 1

        url = "/api/chat/sessions/44444444-4444-4444-8444-444444444444/messages"
        client.post(url, json={"content": "Who has Python experience?"})
        blocked = client.post(url, json={"content": "Who has Python experience?"})

        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert int(blocked.headers["Retry-After"]) >= 1
