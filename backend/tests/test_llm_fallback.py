"""Tests for Portkey provider fallback and evidence enforcement during fallback."""

import asyncio

import pytest

from app.rag import llm as llm_module
from app.rag.config import load_settings
from app.rag.llm import (
    LLMClient,
    LLMCredentialsError,
    LLMError,
    LLMResponseError,
    load_llm_settings,
)
from app.rag.pipeline import (
    EVIDENCE_DATA_MARKER_END,
    EVIDENCE_DATA_MARKER_START,
    RagPipeline,
)
from app.rag.retriever import RetrievalResult
from app.rag.vector_store import SearchHit

OWNER_ID = "11111111-1111-4111-8111-111111111111"


def run(coro):
    return asyncio.run(coro)


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


def make_settings(**overrides):
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


def make_hit(**overrides):
    values = {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "chunk_index": 0,
        "content": "Jane Doe has Python experience.",
        "score": 0.62,
        "source_type": "resume",
        "filename": "resume.pdf",
        "candidate_id": None,
        "job_id": None,
        "created_at": "2026-11-14T00:00:00+00:00",
    }
    values.update(overrides)
    return SearchHit(**values)


class FakeRetriever:
    def __init__(self, hits) -> None:
        self.hits = tuple(hits)

    def retrieve(self, owner_user_id, query, top_k, candidate_id, job_id, source_types):
        return RetrievalResult(
            query=query,
            top_k=top_k or 5,
            hits=self.hits,
            has_evidence=bool(self.hits),
        )


def test_primary_provider_success(gateway):
    gateway.queued_responses = [content_response("primary answer")]

    answer = run(LLMClient(make_settings()).complete("system", "user"))

    assert answer == "primary answer"
    assert len(gateway.requests) == 1
    assert gateway.requests[0]["headers"]["x-portkey-provider"] == "@slug-a"
    assert "x-portkey-config" not in gateway.requests[0]["headers"]


def test_primary_timeout_triggers_fallback(gateway):
    gateway.queued_responses = [
        llm_module.httpx.TimeoutException("slow"),
        content_response("fallback answer"),
    ]

    answer = run(LLMClient(make_settings()).complete("system", "user"))

    assert answer == "fallback answer"
    assert len(gateway.requests) == 2
    assert gateway.requests[0]["headers"]["x-portkey-provider"] == "@slug-a"
    assert gateway.requests[1]["headers"]["x-portkey-provider"] == "@slug-b"


def test_primary_responses_timeout_triggers_chat_completions_fallback(gateway):
    gateway.queued_responses = [
        llm_module.httpx.TimeoutException("slow"),
        content_response("fallback answer"),
    ]

    answer = run(
        LLMClient(make_settings(use_responses=True)).complete(
            "system", "user", use_responses=True
        )
    )

    assert answer == "fallback answer"
    assert len(gateway.requests) == 2
    assert gateway.requests[0]["url"] == "https://gateway.test/v1/responses"
    assert gateway.requests[1]["url"] == "https://gateway.test/v1/chat/completions"


def test_primary_rate_limit_triggers_fallback(gateway):
    gateway.queued_responses = [
        FakeResponse(status_code=429),
        content_response("fallback answer"),
    ]

    answer = run(LLMClient(make_settings()).complete("system", "user"))

    assert answer == "fallback answer"
    assert len(gateway.requests) == 2


def test_primary_server_error_triggers_fallback(gateway):
    gateway.queued_responses = [
        FakeResponse(status_code=503),
        content_response("fallback answer"),
    ]

    answer = run(LLMClient(make_settings()).complete("system", "user"))

    assert answer == "fallback answer"
    assert gateway.requests[1]["headers"]["x-portkey-provider"] == "@slug-b"


def test_connect_error_triggers_fallback(gateway):
    gateway.queued_responses = [
        llm_module.httpx.ConnectError("down"),
        content_response("fallback answer"),
    ]

    assert run(LLMClient(make_settings()).complete("system", "user")) == "fallback answer"


def test_authentication_failure_does_not_fallback(gateway):
    gateway.queued_responses = [FakeResponse(status_code=401)]

    with pytest.raises(LLMCredentialsError):
        run(LLMClient(make_settings()).complete("system", "user"))

    assert len(gateway.requests) == 1


def test_authorization_failure_does_not_fallback(gateway):
    gateway.queued_responses = [FakeResponse(status_code=403)]

    with pytest.raises(LLMCredentialsError):
        run(LLMClient(make_settings()).complete("system", "user"))

    assert len(gateway.requests) == 1


def test_bad_request_does_not_fallback(gateway):
    gateway.queued_responses = [FakeResponse(status_code=422)]

    with pytest.raises(LLMResponseError):
        run(LLMClient(make_settings()).complete("system", "user"))

    assert len(gateway.requests) == 1


def test_invalid_response_does_not_fallback(gateway):
    gateway.queued_responses = [FakeResponse(payload={"choices": []})]

    with pytest.raises(LLMResponseError):
        run(LLMClient(make_settings()).complete("system", "user"))

    assert len(gateway.requests) == 1


def test_all_providers_failing_returns_safe_error(gateway):
    gateway.queued_responses = [
        FakeResponse(status_code=503),
        llm_module.httpx.TimeoutException("slow"),
    ]

    with pytest.raises(LLMError):
        run(LLMClient(make_settings()).complete("system", "user"))

    assert len(gateway.requests) == 2


def test_no_fallback_configured_raises_after_single_attempt(gateway):
    gateway.queued_responses = [FakeResponse(status_code=503)]

    with pytest.raises(LLMError):
        run(LLMClient(make_settings(fallback_slugs=())).complete("system", "user"))

    assert len(gateway.requests) == 1


def test_portkey_config_header_sent_when_configured(gateway):
    gateway.queued_responses = [content_response("ok")]

    run(LLMClient(make_settings(config="cfg-123")).complete("system", "user"))

    assert gateway.requests[0]["headers"]["x-portkey-config"] == "cfg-123"


def test_load_llm_settings_parses_fallback_slugs(monkeypatch):
    monkeypatch.setenv("PORTKEY_SLUGS", "slug-a, slug-b, slug-c")
    monkeypatch.setenv("PORTKEY_AI_API", "key")

    settings = load_llm_settings()

    assert settings.slug == "slug-a"
    assert settings.fallback_slugs == ("slug-b", "slug-c")
    assert settings.providers == ("slug-a", "slug-b", "slug-c")


def test_load_llm_settings_reads_portkey_config(monkeypatch):
    monkeypatch.setenv("PORTKEY_SLUGS", "slug-a")
    monkeypatch.setenv("PORTKEY_AI_API", "key")
    monkeypatch.setenv("PORTKEY_CONFIG", "fallback-config")

    settings = load_llm_settings()

    assert settings.config == "fallback-config"


@pytest.mark.asyncio
async def test_pipeline_fallback_preserves_evidence_restriction(gateway):
    gateway.queued_responses = [
        FakeResponse(status_code=503),
        content_response("Jane Doe has Python experience."),
    ]
    client = LLMClient(make_settings())
    pipeline = RagPipeline(
        retriever=FakeRetriever([make_hit()]),
        llm_client=client,
        settings=load_settings(),
    )

    result = await pipeline.run(OWNER_ID, "Who has Python experience?")

    assert result.has_evidence is True
    assert result.answer == "Jane Doe has Python experience."
    assert result.sources[0]["filename"] == "resume.pdf"
    assert result.sources[0]["document_id"] == "doc-1"
    assert len(gateway.requests) == 2
    sent_messages = gateway.requests[1]["body"]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "untrusted data" in sent_messages[0]["content"]
    assert EVIDENCE_DATA_MARKER_START in sent_messages[1]["content"]
    assert EVIDENCE_DATA_MARKER_END in sent_messages[1]["content"]


@pytest.mark.asyncio
async def test_pipeline_all_providers_failing_returns_safe_error(gateway):
    gateway.queued_responses = [
        FakeResponse(status_code=503),
        FakeResponse(status_code=503),
    ]
    client = LLMClient(make_settings())
    pipeline = RagPipeline(
        retriever=FakeRetriever([make_hit()]),
        llm_client=client,
        settings=load_settings(),
    )

    with pytest.raises(LLMError):
        await pipeline.run(OWNER_ID, "Who has Python experience?")

    assert len(gateway.requests) == 2
