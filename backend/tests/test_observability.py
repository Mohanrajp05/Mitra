"""Tests for Stage 7 observability: metrics, audit logging, and the ops endpoint."""

import asyncio

import pytest

from app.core.audit import AuditTrail
from app.core.metrics import MetricsRegistry
from app.main import app
from app.rag import llm as llm_module
from app.rag.llm import LLMClient
from app.services import chat_service, rag_service
from tests.test_chat_service import install_connection

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
DOCUMENT_ID = "doc-1"

SESSION = {
    "id": SESSION_ID,
    "owner_user_id": TEST_USER_ID,
    "title": "New conversation",
    "created_at": "2026-11-15T10:00:00Z",
    "updated_at": "2026-11-15T10:00:00Z",
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload


class FakeAsyncClient:
    queued_responses: list = []
    requests: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        FakeAsyncClient.requests.append({"url": url, "headers": headers, "body": json})
        response = FakeAsyncClient.queued_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_llm_settings(**overrides):
    values = {
        "base_url": "https://gateway.test/v1",
        "slug": "slug-a",
        "model": "test-model",
        "api_key": "test-key",
        "timeout": 1.0,
        "max_concurrent": 2,
        "fallback_slugs": ("slug-b",),
        "config": "",
    }
    values.update(overrides)
    return llm_module.LLMSettings(**values)


def content_response(content):
    return FakeResponse(payload={"choices": [{"message": {"content": content}}]})


@pytest.fixture
def gateway(monkeypatch):
    FakeAsyncClient.queued_responses = []
    FakeAsyncClient.requests = []
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


class TestRequestMetrics:
    def test_request_count_increments(self, client, fresh_metrics):
        client.get("/api/health")
        client.get("/api/health")

        snapshot = fresh_metrics.snapshot()
        assert snapshot["requests"]["total"] == 2
        assert snapshot["requests"]["success"] == 2
        assert snapshot["requests"]["failed"] == 0

    def test_status_counters_track_codes(self, client, fresh_metrics):
        client.get("/api/health")
        client.get("/api/definitely-not-a-route")

        snapshot = fresh_metrics.snapshot()
        counts = snapshot["requests"]["status_counts"]
        assert counts.get(200) == 1
        assert counts.get(404) == 1
        assert snapshot["requests"]["failed"] == 1

    def test_request_duration_measured(self, client, fresh_metrics):
        client.get("/api/health")

        duration = fresh_metrics.snapshot()["requests"]["duration"]
        assert duration["count"] == 1
        assert duration["max_ms"] >= 0
        assert duration["total_ms"] >= 0

    def test_request_id_preserved_in_slow_request_record(
        self, client, fresh_metrics
    ):
        fresh_metrics.slow_request_ms = 0.01

        response = client.get(
            "/api/health", headers={"X-Request-ID": "trace-abc-123"}
        )

        assert response.headers["X-Request-ID"] == "trace-abc-123"
        slow = fresh_metrics.snapshot()["requests"]["slow"]
        assert slow["total"] >= 1
        record = slow["recent"][-1]
        assert record["request_id"] == "trace-abc-123"
        assert record["path"] == "/api/health"

    def test_metrics_failure_does_not_break_requests(self, client, monkeypatch):
        def broken_metrics():
            raise RuntimeError("metrics down")

        monkeypatch.setattr("app.main.get_metrics", broken_metrics)

        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.headers.get("X-Request-ID")


class TestLLMMetrics:
    def test_llm_success_metrics(self, gateway, fresh_metrics):
        gateway.queued_responses = [content_response("ok")]

        answer = asyncio.run(
            LLMClient(make_llm_settings(fallback_slugs=())).complete("s", "u")
        )

        assert answer == "ok"
        snapshot = fresh_metrics.snapshot()["llm"]
        assert snapshot["calls_total"] == 1
        assert snapshot["calls_success"] == 1
        assert snapshot["calls_failed"] == 0
        assert snapshot["fallback_attempts"] == 0
        assert snapshot["latency"]["count"] == 1

    def test_llm_failure_metrics(self, gateway, fresh_metrics):
        gateway.queued_responses = [FakeResponse(status_code=503)]

        with pytest.raises(llm_module.LLMError):
            asyncio.run(
                LLMClient(make_llm_settings(fallback_slugs=())).complete("s", "u")
            )

        snapshot = fresh_metrics.snapshot()["llm"]
        assert snapshot["calls_total"] == 1
        assert snapshot["calls_failed"] == 1
        assert snapshot["provider_failures"].get("slug-a") == 1

    def test_llm_timeout_metrics(self, gateway, fresh_metrics):
        gateway.queued_responses = [llm_module.httpx.TimeoutException("slow")]

        with pytest.raises(llm_module.LLMError):
            asyncio.run(
                LLMClient(make_llm_settings(fallback_slugs=())).complete("s", "u")
            )

        snapshot = fresh_metrics.snapshot()["llm"]
        assert snapshot["timeouts"] == 1
        assert snapshot["provider_failures"].get("slug-a") == 1

    def test_fallback_metrics_and_audit_event(
        self, gateway, fresh_metrics, fresh_audit_trail
    ):
        gateway.queued_responses = [
            FakeResponse(status_code=503),
            content_response("fallback ok"),
        ]

        answer = asyncio.run(LLMClient(make_llm_settings()).complete("s", "u"))

        assert answer == "fallback ok"
        snapshot = fresh_metrics.snapshot()["llm"]
        assert snapshot["calls_success"] == 1
        assert snapshot["fallback_attempts"] == 1
        assert snapshot["provider_failures"].get("slug-a") == 1
        assert snapshot["provider_failures"].get("slug-b") is None

        fallback_events = [
            event
            for event in fresh_audit_trail.recent()
            if event["event_type"] == "llm_provider_fallback"
        ]
        assert len(fallback_events) == 1
        assert fallback_events[0]["detail"] == "from=slug-a to=slug-b"
        assert fallback_events[0]["status"] == "success"

    def test_llm_metrics_failure_does_not_break_calls(self, gateway, monkeypatch):
        gateway.queued_responses = [content_response("ok")]

        def broken_metrics():
            raise RuntimeError("metrics down")

        monkeypatch.setattr(llm_module, "get_metrics", broken_metrics)

        answer = asyncio.run(
            LLMClient(make_llm_settings(fallback_slugs=())).complete("s", "u")
        )

        assert answer == "ok"


class TestCacheStatsRemainCorrect:
    def test_cache_stats_endpoint_still_works(self, client):
        response = client.get("/api/rag/cache/stats")

        assert response.status_code == 200
        body = response.json()
        # Legacy RAG counters remain at the top level; match cache stats are nested.
        assert {"enabled", "hits", "misses", "evictions", "entries", "match", "rag"} <= set(body)
        assert body["match"]["entries"] == 0


class TestAuditEvents:
    def test_session_lifecycle_events(self, monkeypatch, fresh_audit_trail):
        from app.schemas.chat import ChatSessionRename

        install_connection(monkeypatch, [[], SESSION])
        chat_service.create_session(TEST_USER_ID)

        install_connection(monkeypatch, [SESSION])
        chat_service.rename_session(
            TEST_USER_ID, SESSION_ID, ChatSessionRename(title="Recruiting drive")
        )

        install_connection(monkeypatch, [True])
        chat_service.delete_session(TEST_USER_ID, SESSION_ID)

        events = fresh_audit_trail.recent()
        types = [event["event_type"] for event in events]
        assert types == [
            "chat_session_created",
            "chat_session_renamed",
            "chat_session_deleted",
        ]
        assert all(event["user_id"] == TEST_USER_ID for event in events)
        assert all(event["status"] == "success" for event in events)

    def test_failed_session_action_recorded_as_failure(
        self, monkeypatch, fresh_audit_trail
    ):
        install_connection(monkeypatch, [None])

        with pytest.raises(chat_service.SessionNotFoundError):
            chat_service.delete_session(TEST_USER_ID, SESSION_ID)

        events = fresh_audit_trail.recent()
        assert len(events) == 1
        assert events[0]["event_type"] == "chat_session_deleted"
        assert events[0]["status"] == "failure"
        assert events[0]["detail"] == "session_not_found"

    def test_clear_history_event(self, monkeypatch, fresh_audit_trail):
        install_connection(monkeypatch, [[1, 2, 3]])

        deleted = chat_service.delete_all_sessions(TEST_USER_ID)

        assert deleted == 3
        events = fresh_audit_trail.recent()
        assert events[-1]["event_type"] == "chat_history_cleared"
        assert events[-1]["detail"] == "deleted_count=3"
        assert events[-1]["user_id"] == TEST_USER_ID

    def test_document_events(self, monkeypatch, fresh_audit_trail):
        class FakeStore:
            def save_document(self, owner_user_id, **kwargs):
                return {"document_id": DOCUMENT_ID}

            def get_document(self, owner_user_id, document_id):
                return None

            def delete_document(self, owner_user_id, document_id):
                return True

            def rebuild_index(self, owner_user_id):
                return {"scanned": 1, "rebuilt": 1, "skipped": 0, "removed": 0}

        monkeypatch.setattr(rag_service, "get_document_store", lambda: FakeStore())

        asyncio.run(
            rag_service.save_document(
                TEST_USER_ID, filename="resume.pdf", data=b"x", source_type="resume"
            )
        )
        asyncio.run(rag_service.delete_document(TEST_USER_ID, DOCUMENT_ID))
        asyncio.run(rag_service.reindex(TEST_USER_ID))

        events = fresh_audit_trail.recent()
        types = [event["event_type"] for event in events]
        assert types == [
            "document_uploaded",
            "document_deleted",
            "documents_reindexed",
        ]
        assert all(event["user_id"] == TEST_USER_ID for event in events)
        assert events[0]["resource_id"] == DOCUMENT_ID

    def test_failed_document_deletion_recorded(self, monkeypatch, fresh_audit_trail):
        class FakeStore:
            def get_document(self, owner_user_id, document_id):
                return None

            def delete_document(self, owner_user_id, document_id):
                return False

        monkeypatch.setattr(rag_service, "get_document_store", lambda: FakeStore())

        with pytest.raises(rag_service.RecordNotFoundError):
            asyncio.run(rag_service.delete_document(TEST_USER_ID, "missing-doc"))

        events = fresh_audit_trail.recent()
        assert events[-1]["event_type"] == "document_deleted"
        assert events[-1]["status"] == "failure"
        assert events[-1]["resource_id"] == "missing-doc"

    def test_rate_limit_exceeded_event(self, client, monkeypatch, fresh_audit_trail):
        from app.api import chat as chat_module

        async def fake_send(*args, **kwargs):
            return {}

        monkeypatch.setattr(chat_module.chat_service, "send_message", fake_send)
        limiter = chat_module.get_rate_limiter()
        limiter.max_requests = 1

        url = f"/api/chat/sessions/{SESSION_ID}/messages"
        client.post(url, json={"content": "Who has Python experience?"})
        second = client.post(url, json={"content": "Who has Python experience?"})

        assert second.status_code == 429

        rate_events = [
            event
            for event in fresh_audit_trail.recent()
            if event["event_type"] == "rate_limit_exceeded"
        ]
        assert len(rate_events) == 1
        assert rate_events[0]["user_id"] == TEST_USER_ID
        assert rate_events[0]["status"] == "failure"

    def test_audit_never_contains_message_content(
        self, client, monkeypatch, fresh_audit_trail
    ):
        from app.services import rag_service

        install_connection(monkeypatch, [[], SESSION])
        response = client.post("/api/chat/sessions", json={"title": "PII check"})
        assert response.status_code == 201

        def fail_check(owner, session):
            return None

        async def fake_query(owner_user_id, content):
            from app.rag.pipeline import PipelineResult

            return PipelineResult(
                query=content,
                answer="answer",
                has_evidence=True,
                sources=[],
            )

        def fake_persist(owner, session, content, result):
            return {
                "user_message": {
                    "id": "11111111-2222-4333-8444-555555555555",
                    "session_id": SESSION_ID,
                    "owner_user_id": TEST_USER_ID,
                    "role": "user",
                    "content": "sent",
                    "sources": [],
                    "has_evidence": True,
                    "created_at": "2026-11-15T10:01:00Z",
                },
                "assistant_message": {
                    "id": "66666666-7777-4888-8999-000000000000",
                    "session_id": SESSION_ID,
                    "owner_user_id": TEST_USER_ID,
                    "role": "assistant",
                    "content": "reply",
                    "sources": [],
                    "has_evidence": True,
                    "created_at": "2026-11-15T10:01:05Z",
                },
            }

        monkeypatch.setattr(chat_service, "_check_session", fail_check)
        monkeypatch.setattr(rag_service, "query", fake_query)
        monkeypatch.setattr(chat_service, "_persist_exchange", fake_persist)

        message_response = client.post(
            f"/api/chat/sessions/{SESSION_ID}/messages",
            json={"content": "Contact jane.doe@example.com about token abc123"},
        )

        assert message_response.status_code == 200
        dumped = "\n".join(str(event) for event in fresh_audit_trail.recent())
        assert fresh_audit_trail.recent()
        assert "jane.doe@example.com" not in dumped
        assert "abc123" not in dumped
        assert "Contact jane.doe" not in dumped

    def test_audit_ownership_from_authenticated_user(
        self, client, monkeypatch, fresh_audit_trail
    ):
        install_connection(monkeypatch, [[], SESSION])

        response = client.post("/api/chat/sessions", json={"title": "Spoofed"})

        assert response.status_code == 201
        created = [
            event
            for event in fresh_audit_trail.recent()
            if event["event_type"] == "chat_session_created"
        ]
        assert len(created) == 1
        assert created[0]["user_id"] == TEST_USER_ID
        assert created[0]["resource_id"] == SESSION_ID


class TestMonitoringEndpoint:
    def test_metrics_endpoint_requires_authentication(self):
        from fastapi.testclient import TestClient

        with TestClient(app) as anonymous:
            response = anonymous.get("/api/ops/metrics")

        assert response.status_code == 401

    def test_metrics_endpoint_returns_aggregates_only(self, client, fresh_metrics):
        client.get("/api/health")

        response = client.get("/api/ops/metrics")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "generated_at",
            "started_at",
            "slow_request_threshold_ms",
            "requests",
            "llm",
        }
        assert body["requests"]["total"] >= 1
        assert "events" not in body
        assert "audit" not in body

    def test_cache_stats_endpoint_requires_authentication(self):
        from fastapi.testclient import TestClient

        with TestClient(app) as anonymous:
            response = anonymous.get("/api/rag/cache/stats")

        assert response.status_code == 401
