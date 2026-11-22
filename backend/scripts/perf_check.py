"""Stage 9 performance measurements.

Lightweight, offline benchmark of the components that do not require
external services. Every number printed is an actual measurement taken
during this run. LLM latency is excluded because it requires real
provider credentials; provider latency therefore stays NOT TESTED.
"""

import statistics
import tempfile
import threading
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from app.core.rate_limit import SlidingWindowRateLimiter
from app.rag.response_cache import CacheSettings, ResponseCache
from app.rag.splitter import split_text
from app.rag.vector_store import LocalVectorStore
from app.schemas.chat import ChatMessageResponse
from tests.rag_helpers import FakeEmbeddingService, make_settings


def percentile(values, pct):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def report(name, values_ms):
    print(
        f"{name}: p50={percentile(values_ms, 50):.2f}ms "
        f"p95={percentile(values_ms, 95):.2f}ms "
        f"mean={statistics.mean(values_ms):.2f}ms n={len(values_ms)}"
    )


def api_overhead():
    from fastapi.testclient import TestClient

    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "id": "11111111-1111-4111-8111-111111111111",
        "email": "audit@example.com",
        "user_metadata": {},
    }
    health_times, notfound_times, unauthorized_times = [], [], []
    with TestClient(app) as client:
        for _ in range(50):
            started = time.perf_counter()
            client.get("/api/health")
            health_times.append((time.perf_counter() - started) * 1000)
        for _ in range(50):
            started = time.perf_counter()
            client.get("/api/definitely-not-a-route")
            notfound_times.append((time.perf_counter() - started) * 1000)
        saved = app.dependency_overrides.pop(get_current_user)
        try:
            for _ in range(50):
                started = time.perf_counter()
                client.get("/api/jobs")
                unauthorized_times.append((time.perf_counter() - started) * 1000)
        finally:
            app.dependency_overrides[get_current_user] = saved
    app.dependency_overrides.clear()
    report("API GET /api/health (framework+middleware overhead)", health_times)
    report("API unknown route 404", notfound_times)
    report("API unauthenticated /api/jobs 401", unauthorized_times)


def splitter_throughput():
    sentences = [
        f"Project {index}: built a Python microservice with FastAPI, "
        f"PostgreSQL, and automated tests for feature area {index % 17}. "
        for index in range(4000)
    ]
    text = " ".join(sentences)
    chunks = split_text(text, 1000, 200)
    started = time.perf_counter()
    split_text(text, 1000, 200)
    elapsed = (time.perf_counter() - started) * 1000
    print(
        f"splitter: {len(text)/1024:.0f}KB varied text -> {len(chunks)} chunks in {elapsed:.2f}ms"
    )


def ingestion_and_retrieval():
    with tempfile.TemporaryDirectory(prefix="perf-rag-") as tmp:
        settings = make_settings(Path(tmp))
        store = LocalVectorStore(settings, FakeEmbeddingService(8))
        owner = "11111111-1111-4111-8111-111111111111"

        document = "Resume text about Python development. " * 2000
        save_times, search_times = [], []
        for index in range(10):
            data = (document + f" variant {index}").encode("utf-8")
            started = time.perf_counter()
            store.save_document(
                owner,
                filename=f"resume-{index}.txt",
                data=data,
                source_type="resume",
                candidate_id="33333333-3333-4333-8333-333333333333",
                content_type="text/plain",
            )
            save_times.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            store.search(owner, query="python developer", top_k=5)
            search_times.append((time.perf_counter() - started) * 1000)

        report("document ingestion save (fake embeddings)", save_times)
        report("vector retrieval search top_k=5", search_times)

        tracemalloc.start()
        store.save_document(
            owner,
            filename="memory-check.txt",
            data=document.encode("utf-8"),
            source_type="resume",
            content_type="text/plain",
        )
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"ingestion memory for {len(document)/1024:.0f}KB text: peak={peak/1024:.0f}KB")


def real_embedding_if_available():
    try:
        from app.rag.embeddings import EmbeddingService, EmbeddingError
        from app.rag.config import rag_settings
    except Exception as exc:
        print(f"real embeddings: NOT TESTED ({type(exc).__name__})")
        return

    service = EmbeddingService(
        rag_settings.embedding_model,
        rag_settings.embedding_dimension,
        rag_settings.embedding_batch_size,
        allow_download=False,
    )
    try:
        texts = [f"chunk {i}: python fastapi postgresql experience" for i in range(16)]
        started = time.perf_counter()
        service.embed_texts(texts)
        elapsed = (time.perf_counter() - started) * 1000
        print(
            f"real embeddings ({rag_settings.embedding_model}, offline cache): "
            f"16 texts in {elapsed:.0f}ms"
        )
        started = time.perf_counter()
        service.embed_texts(texts)
        print(
            f"real embeddings second call: "
            f"{(time.perf_counter() - started) * 1000:.0f}ms"
        )
    except Exception as exc:
        print(f"real embeddings: NOT TESTED ({type(exc).__name__}, model not cached offline)")


def cache_hit_miss():
    cache = ResponseCache(
        CacheSettings(enabled=True, ttl_seconds=60, max_entries=100)
    )
    misses, hits = [], []
    from app.rag.pipeline import PipelineResult

    result = PipelineResult(
        query="q", answer="a", has_evidence=True, sources=[]
    )
    for index in range(50):
        async_value = None

        async def loader():
            return result

        import asyncio

        started = time.perf_counter()
        asyncio.run(
            cache.get_or_load("owner", f"unique-query-{index}", loader)
        )
        misses.append((time.perf_counter() - started) * 1000)
    import asyncio

    async def loader_slow():
        return result

    for _ in range(50):
        started = time.perf_counter()
        asyncio.run(
            cache.get_or_load("owner", "unique-query-0", loader_slow)
        )
        hits.append((time.perf_counter() - started) * 1000)
    report("cache miss (first request per query)", misses)
    report("cache hit (repeated query)", hits)


def large_history_serialization():
    messages = [
        {
            "id": f"55555555-5555-4555-8555-{index:012d}",
            "session_id": "44444444-4444-4444-8444-444444444444",
            "owner_user_id": "11111111-1111-4111-8111-111111111111",
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"message body {index} " * 20,
            "sources": [],
            "has_evidence": index % 2 == 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for index in range(5000)
    ]
    started = time.perf_counter()
    validated = [ChatMessageResponse.model_validate(m) for m in messages]
    elapsed = (time.perf_counter() - started) * 1000
    print(
        f"large history: validated {len(validated)} messages in {elapsed:.1f}ms "
        f"({elapsed / len(validated) * 1000:.1f}us per message)"
    )


def concurrency_and_rate_limit():
    limiter = SlidingWindowRateLimiter(30, 60.0)
    allowed = []
    lock = threading.Lock()
    barrier = threading.Barrier(100)

    def worker():
        barrier.wait()
        ok, _ = limiter.acquire("user")
        with lock:
            allowed.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(100)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = (time.perf_counter() - started) * 1000
    print(
        f"rate limiter under 100 concurrent threads: {sum(allowed)}/100 allowed "
        f"(limit=30) in {elapsed:.1f}ms"
    )
    assert sum(allowed) == 30, "rate limiter admitted more than max_requests"


def database_timings():
    try:
        from app.database import queries
        from app.database.connection import close_pool, get_connection, open_pool

        open_pool()
    except Exception as exc:
        print(f"database timings: NOT TESTED ({type(exc).__name__})")
        return

    try:
        job_times, candidate_times = [], []
        with get_connection() as connection:
            for _ in range(20):
                started = time.perf_counter()
                queries.list_jobs(connection, "11111111-1111-4111-8111-111111111111")
                job_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter()
                queries.list_candidates(
                    connection, "11111111-1111-4111-8111-111111111111"
                )
                candidate_times.append((time.perf_counter() - started) * 1000)
        report("DB list_jobs (pooled, local PostgreSQL)", job_times)
        report("DB list_candidates (pooled, local PostgreSQL)", candidate_times)
    except Exception as exc:
        print(f"database timings: NOT TESTED ({type(exc).__name__})")
    finally:
        try:
            close_pool()
        except Exception:
            pass


if __name__ == "__main__":
    import logging

    logging.disable(logging.INFO)
    print("=== Stage 9 performance measurements (offline) ===")
    api_overhead()
    splitter_throughput()
    ingestion_and_retrieval()
    real_embedding_if_available()
    cache_hit_miss()
    large_history_serialization()
    concurrency_and_rate_limit()
    database_timings()
