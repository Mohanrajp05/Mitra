"""Tests for the in-memory RAG response cache and its invalidation hooks."""

import asyncio

import pytest

from app.rag import response_cache
from app.rag.pipeline import PipelineResult
from app.rag.response_cache import (
    CacheSettings,
    ResponseCache,
    load_cache_settings,
)
from app.services import rag_service

OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"

RESULT = PipelineResult(
    query="Who has Python experience?",
    answer="Jane Doe has Python experience.",
    has_evidence=True,
    sources=[
        {
            "document_id": "doc-1",
            "chunk_id": "doc-1-0",
            "chunk_index": 0,
            "score": 0.82,
            "source_type": "resume",
            "filename": "resume.pdf",
        }
    ],
    evidence_text="evidence block",
)


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakePipeline:
    def __init__(self, results: list[PipelineResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple] = []

    async def run(self, owner_user_id, query, top_k=None, candidate_id=None, job_id=None):
        self.calls.append((owner_user_id, query, top_k, candidate_id, job_id))
        return self.results.pop(0)


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def save_document(self, owner_user_id, **kwargs):
        self.calls.append(f"save:{owner_user_id}")
        return {"document_id": "doc-new"}

    def get_document(self, owner_user_id, document_id):
        return None

    def delete_document(self, owner_user_id, document_id):
        self.calls.append(f"delete:{owner_user_id}")
        return True

    def rebuild_index(self, owner_user_id):
        self.calls.append(f"reindex:{owner_user_id}")
        return {"scanned": 1, "rebuilt": 1, "skipped": 0, "removed": 0}


def loader_recording(calls: list, result=RESULT):
    async def loader():
        calls.append(1)
        return result

    return loader


@pytest.mark.asyncio
async def test_first_request_is_a_cache_miss():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []

    result = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))

    assert result.answer == RESULT.answer
    assert len(calls) == 1
    assert cache.stats()["misses"] == 1
    assert cache.stats()["hits"] == 0


@pytest.mark.asyncio
async def test_repeated_identical_request_is_a_cache_hit():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []

    await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))
    second = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))

    assert len(calls) == 1
    assert second.answer == RESULT.answer
    assert cache.stats()["hits"] == 1


@pytest.mark.asyncio
async def test_cached_answer_preserves_sources_and_metadata():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []

    cached = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))

    assert cached.sources == RESULT.sources
    assert cached.sources[0]["filename"] == "resume.pdf"
    assert cached.sources[0]["score"] == 0.82
    assert cached.evidence_text == RESULT.evidence_text


@pytest.mark.asyncio
async def test_cached_entries_are_isolated_copies():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []

    first = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))
    first.sources[0]["filename"] = "mutated.pdf"

    second = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))

    assert second.sources[0]["filename"] == "resume.pdf"


@pytest.mark.asyncio
async def test_different_users_receive_separate_entries():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []

    await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))
    await cache.get_or_load(OWNER_B, "Who has Python?", loader_recording(calls))

    assert len(calls) == 2
    assert cache.stats()["entries"] == 2


@pytest.mark.asyncio
async def test_different_filters_produce_separate_entries():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []

    await cache.get_or_load(
        OWNER_A, "Who has Python?", loader_recording(calls), candidate_id="c-1"
    )
    await cache.get_or_load(
        OWNER_A, "Who has Python?", loader_recording(calls), candidate_id="c-2"
    )
    await cache.get_or_load(
        OWNER_A, "Who has Python?", loader_recording(calls), job_id="j-1"
    )
    await cache.get_or_load(
        OWNER_A, "Who has Python?", loader_recording(calls), top_k=10
    )

    assert len(calls) == 4
    assert cache.stats()["entries"] == 4


@pytest.mark.asyncio
async def test_question_normalization_does_not_split_entries():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []

    await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))
    await cache.get_or_load(OWNER_A, "  who   HAS python?  ", loader_recording(calls))

    assert len(calls) == 1
    assert cache.stats()["entries"] == 1


@pytest.mark.asyncio
async def test_expired_entries_are_not_returned(monkeypatch):
    fake_time = FakeTime()
    monkeypatch.setattr(response_cache, "time", fake_time)
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=300, max_entries=10))
    calls: list = []

    await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))
    fake_time.advance(301)
    second = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))

    assert len(calls) == 2
    assert second.answer == RESULT.answer
    assert cache.stats()["entries"] == 1


@pytest.mark.asyncio
async def test_capacity_and_eviction_work():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=2))
    calls: list = []

    await cache.get_or_load(OWNER_A, "question one", loader_recording(calls))
    await cache.get_or_load(OWNER_A, "question two", loader_recording(calls))
    await cache.get_or_load(OWNER_A, "question three", loader_recording(calls))

    stats = cache.stats()
    assert stats["entries"] == 2
    assert stats["evictions"] == 1

    oldest = await cache.get_or_load(OWNER_A, "question one", loader_recording(calls))
    assert len(calls) == 4
    assert oldest.answer == RESULT.answer


@pytest.mark.asyncio
async def test_failed_loader_is_not_cached():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    attempts: list = []

    async def failing_loader():
        attempts.append(1)
        raise RuntimeError("LLM failed")

    with pytest.raises(RuntimeError):
        await cache.get_or_load(OWNER_A, "Who has Python?", failing_loader)

    result = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(attempts))

    assert len(attempts) == 2
    assert result.answer == RESULT.answer
    assert cache.stats()["entries"] == 1


@pytest.mark.asyncio
async def test_weak_evidence_responses_are_not_cached():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    weak = PipelineResult(
        query="Who has Python?",
        answer="No relevant information found.",
        has_evidence=False,
        sources=[],
    )
    calls: list = []

    first = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls, weak))
    second = await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls, weak))

    assert len(calls) == 2
    assert first.answer == weak.answer
    assert second.answer == weak.answer
    assert cache.stats()["entries"] == 0


@pytest.mark.asyncio
async def test_disabled_cache_never_stores_or_hits():
    cache = ResponseCache(CacheSettings(enabled=False, ttl_seconds=60, max_entries=10))
    calls: list = []

    await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))
    await cache.get_or_load(OWNER_A, "Who has Python?", loader_recording(calls))

    assert len(calls) == 2
    assert cache.stats()["entries"] == 0


@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_share_one_loader_call():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))
    calls: list = []
    release = asyncio.Event()

    async def loader():
        calls.append(1)
        await release.wait()
        return RESULT

    first_task = asyncio.create_task(cache.get_or_load(OWNER_A, "Who has Python?", loader))
    await asyncio.sleep(0)
    second_task = asyncio.create_task(cache.get_or_load(OWNER_A, "Who has Python?", loader))
    await asyncio.sleep(0)
    release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert len(calls) == 1
    assert first.answer == second.answer == RESULT.answer
    assert cache.stats()["entries"] == 1


def test_invalidate_user_only_clears_that_user():
    cache = ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))

    cache.set("key-a", RESULT, OWNER_A)
    cache.set("key-b", RESULT, OWNER_B)
    removed = cache.invalidate_user(OWNER_A)

    assert removed == 1
    assert cache._entries.get("key-a") is None
    assert cache._entries.get("key-b") is not None


def test_cache_settings_validation():
    with pytest.raises(ValueError):
        CacheSettings(enabled=True, ttl_seconds=0, max_entries=10)
    with pytest.raises(ValueError):
        CacheSettings(enabled=True, ttl_seconds=60, max_entries=0)


def test_load_cache_settings_reads_env(monkeypatch):
    monkeypatch.setenv("RAG_CACHE_ENABLED", "true")
    monkeypatch.setenv("RAG_CACHE_TTL_SECONDS", "120")
    monkeypatch.setenv("RAG_CACHE_MAX_ENTRIES", "25")

    settings = load_cache_settings()

    assert settings.enabled is True
    assert settings.ttl_seconds == 120
    assert settings.max_entries == 25


def test_load_cache_settings_rejects_bad_boolean(monkeypatch):
    monkeypatch.setenv("RAG_CACHE_ENABLED", "maybe")

    with pytest.raises(ValueError):
        load_cache_settings()


@pytest.mark.asyncio
async def test_document_upload_invalidates_user_cache(monkeypatch):
    cache = response_cache.get_response_cache()
    cache.settings = CacheSettings(enabled=True, ttl_seconds=300, max_entries=10)
    calls: list = []
    pipeline = FakePipeline([RESULT, RESULT])
    store = FakeStore()
    monkeypatch.setattr(rag_service, "get_rag_pipeline", lambda: pipeline)
    monkeypatch.setattr(rag_service, "get_document_store", lambda: store)

    await rag_service.query(OWNER_A, "Who has Python?")
    assert len(pipeline.calls) == 1

    await rag_service.save_document(
        OWNER_A, filename="new.pdf", data=b"x", source_type="resume"
    )
    assert cache.stats()["entries"] == 0

    await rag_service.query(OWNER_A, "Who has Python?")
    assert len(pipeline.calls) == 2
    assert store.calls == [f"save:{OWNER_A}"]


@pytest.mark.asyncio
async def test_document_deletion_invalidates_only_that_user(monkeypatch):
    cache = response_cache.get_response_cache()
    cache.settings = CacheSettings(enabled=True, ttl_seconds=300, max_entries=10)
    pipeline = FakePipeline([RESULT])
    store = FakeStore()
    monkeypatch.setattr(rag_service, "get_rag_pipeline", lambda: pipeline)
    monkeypatch.setattr(rag_service, "get_document_store", lambda: store)
    await rag_service.query(OWNER_A, "Who has Python?")

    await rag_service.delete_document(OWNER_B, "doc-1")

    assert store.calls == [f"delete:{OWNER_B}"]
    assert cache.stats()["entries"] == 1

    await rag_service.delete_document(OWNER_A, "doc-1")
    assert cache.stats()["entries"] == 0


@pytest.mark.asyncio
async def test_reindex_invalidates_user_cache(monkeypatch):
    cache = response_cache.get_response_cache()
    cache.settings = CacheSettings(enabled=True, ttl_seconds=300, max_entries=10)
    calls: list = []
    pipeline = FakePipeline([RESULT, RESULT])
    store = FakeStore()
    monkeypatch.setattr(rag_service, "get_rag_pipeline", lambda: pipeline)
    monkeypatch.setattr(rag_service, "get_document_store", lambda: store)

    await rag_service.query(OWNER_A, "Who has Python?")
    report = await rag_service.reindex(OWNER_A)

    assert report == {"scanned": 1, "rebuilt": 1, "skipped": 0, "removed": 0}
    assert cache.stats()["entries"] == 0

    refreshed = await rag_service.query(OWNER_A, "Who has Python?")
    assert len(pipeline.calls) == 2
    assert refreshed.sources == RESULT.sources


@pytest.mark.asyncio
async def test_invalidation_prevents_stale_source_references(monkeypatch):
    cache = response_cache.get_response_cache()
    cache.settings = CacheSettings(enabled=True, ttl_seconds=300, max_entries=10)
    fresh = PipelineResult(
        query="Who has Python?",
        answer="Updated answer.",
        has_evidence=True,
        sources=[
            {
                "document_id": "doc-2",
                "chunk_id": "doc-2-0",
                "chunk_index": 0,
                "score": 0.7,
                "source_type": "resume",
                "filename": "updated-resume.pdf",
            }
        ],
    )
    pipeline = FakePipeline([RESULT, fresh])
    store = FakeStore()
    monkeypatch.setattr(rag_service, "get_rag_pipeline", lambda: pipeline)
    monkeypatch.setattr(rag_service, "get_document_store", lambda: store)

    cached = await rag_service.query(OWNER_A, "Who has Python?")
    assert cached.sources[0]["document_id"] == "doc-1"

    await rag_service.save_document(
        OWNER_A, filename="updated.pdf", data=b"x", source_type="resume"
    )
    updated = await rag_service.query(OWNER_A, "Who has Python?")

    assert updated.sources[0]["document_id"] == "doc-2"
    assert updated.sources[0]["filename"] == "updated-resume.pdf"


def test_cache_stats_endpoint_requires_authentication():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anonymous:
        response = anonymous.get("/api/rag/cache/stats")

    assert response.status_code == 401
    assert "detail" in response.json()


def test_cache_stats_endpoint_returns_counts_only(client):
    response = client.get("/api/rag/cache/stats")

    assert response.status_code == 200
    body = response.json()
    # Legacy RAG counters remain at the top level; match cache stats are nested.
    assert {"enabled", "hits", "misses", "evictions", "entries", "match", "rag"} <= set(body)
    assert body["entries"] == 0
    assert body["match"]["entries"] == 0
