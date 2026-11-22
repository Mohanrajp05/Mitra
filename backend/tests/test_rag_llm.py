import asyncio
import json

import httpx
import pytest

from app.rag import llm as llm_module
from app.rag.llm import (
    LLMClient,
    LLMCredentialsError,
    LLMError,
    LLMNotConfiguredError,
    LLMResponseError,
    _extract_json,
    get_llm_client,
    load_llm_settings,
    reset_llm_client,
    set_llm_client,
)
from app.schemas.rag import JobAnalysis


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload


class FakeAsyncClient:
    next_response = None
    queued_responses: list = []
    requests: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        FakeAsyncClient.requests.append(
            {"url": url, "headers": headers, "body": json}
        )
        if FakeAsyncClient.queued_responses:
            response = FakeAsyncClient.queued_responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        if isinstance(FakeAsyncClient.next_response, Exception):
            raise FakeAsyncClient.next_response
        return FakeAsyncClient.next_response


def make_settings(**overrides):
    values = {
        "base_url": "https://gateway.test/v1",
        "slug": "test-slug",
        "model": "test-model",
        "api_key": "test-key",
        "timeout": 1.0,
        "max_concurrent": 2,
    }
    values.update(overrides)
    return llm_module.LLMSettings(**values)


def make_client(**overrides):
    return LLMClient(make_settings(**overrides))


def content_response(content):
    return FakeResponse(payload={"choices": [{"message": {"content": content}}]})


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def gateway(monkeypatch):
    FakeAsyncClient.next_response = None
    FakeAsyncClient.queued_responses = []
    FakeAsyncClient.requests = []
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


def test_complete_returns_content(gateway):
    gateway.next_response = content_response("hello")

    answer = run(make_client().complete("system", "user"))

    assert answer == "hello"
    assert gateway.requests[0]["url"] == "https://gateway.test/v1/chat/completions"
    assert gateway.requests[0]["headers"]["x-portkey-api-key"] == "test-key"
    assert gateway.requests[0]["headers"]["x-portkey-provider"] == "@test-slug"
    assert gateway.requests[0]["body"]["model"] == "test-model"
    assert gateway.requests[0]["body"]["messages"][0]["role"] == "system"


def test_json_mode_sets_response_format(gateway):
    gateway.next_response = content_response("{}")

    run(make_client().complete("s", "u", json_mode=True))

    assert gateway.requests[0]["body"]["response_format"] == {"type": "json_object"}


def test_not_configured_raises(gateway):
    with pytest.raises(LLMNotConfiguredError):
        run(make_client(api_key="").complete("system", "user"))


def test_missing_slug_raises(gateway):
    with pytest.raises(LLMNotConfiguredError):
        run(make_client(slug="").complete("system", "user"))


def test_rate_limit_raises_llm_error(gateway):
    gateway.next_response = FakeResponse(status_code=429)

    with pytest.raises(LLMError):
        run(make_client().complete("system", "user"))


def test_server_error_raises_llm_error(gateway):
    gateway.next_response = FakeResponse(status_code=503)

    with pytest.raises(LLMError):
        run(make_client().complete("system", "user"))


def test_bad_credentials_raise_credentials_error(gateway):
    gateway.next_response = FakeResponse(status_code=401)

    with pytest.raises(LLMCredentialsError):
        run(make_client().complete("system", "user"))


def test_forbidden_raises_credentials_error(gateway):
    gateway.next_response = FakeResponse(status_code=403)

    with pytest.raises(LLMCredentialsError):
        run(make_client().complete("system", "user"))


def test_connect_error_raises_llm_error(gateway):
    gateway.next_response = httpx.ConnectError("down")

    with pytest.raises(LLMError):
        run(make_client().complete("system", "user"))


def test_timeout_raises_llm_error(gateway):
    gateway.next_response = httpx.TimeoutException("slow")

    with pytest.raises(LLMError):
        run(make_client().complete("system", "user"))


def test_unexpected_payload_raises_response_error(gateway):
    gateway.next_response = FakeResponse(payload={"choices": []})

    with pytest.raises(LLMResponseError):
        run(make_client().complete("system", "user"))


def test_empty_content_raises_response_error(gateway):
    gateway.next_response = content_response("   ")

    with pytest.raises(LLMResponseError):
        run(make_client().complete("system", "user"))


def test_complete_responses_returns_output_text(gateway):
    gateway.next_response = FakeResponse(
        payload={
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "KIE answer"}],
                }
            ]
        }
    )

    answer = run(
        make_client(use_responses=True).complete("system", "user", use_responses=True)
    )

    assert answer == "KIE answer"
    assert gateway.requests[0]["url"] == "https://gateway.test/v1/responses"
    assert gateway.requests[0]["body"]["model"] == "test-model"
    assert gateway.requests[0]["body"]["input"][0]["role"] == "system"
    assert gateway.requests[0]["body"]["input"][1]["content"] == "user"


def test_complete_responses_sse_stream_returns_output_text(gateway):
    gateway.next_response = FakeResponse(
        text=(
            "event: response.created\n"
            'data: {"type": "response.created", "response": {"id": "resp_1"}}\n\n'
            "event: response.completed\n"
            'data: {"type": "response.completed", "response": {"output": [{"type": "message", "content": [{"type": "output_text", "text": "KIE streamed answer"}]}]}}\n\n'
        )
    )

    answer = run(
        make_client(use_responses=True).complete("system", "user", use_responses=True)
    )

    assert answer == "KIE streamed answer"


def test_complete_responses_uses_json_text_extraction(gateway):
    gateway.next_response = FakeResponse(
        payload={
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": '{"required_skills": ["Python"], "summary": "ok"}'}
                    ],
                }
            ]
        }
    )

    result = run(
        make_client(use_responses=True).complete_structured(
            JobAnalysis, "system", "user", use_responses=True
        )
    )

    assert result.required_skills == ["Python"]


def test_complete_responses_empty_output_raises(gateway):
    gateway.next_response = FakeResponse(payload={"output": []})

    with pytest.raises(LLMResponseError):
        run(
            make_client(use_responses=True).complete("system", "user", use_responses=True)
        )


def test_extract_json_variants():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('prefix {"a": {"b": 2}} suffix') == {"a": {"b": 2}}

    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_complete_structured_validates(gateway):
    gateway.next_response = content_response(
        json.dumps(
            {
                "title": "Backend Engineer",
                "required_skills": ["Python"],
                "summary": "Builds services.",
            }
        )
    )

    result = run(make_client().complete_structured(JobAnalysis, "system", "user"))

    assert result.title == "Backend Engineer"
    assert result.required_skills == ["Python"]


def test_complete_structured_retries_invalid_json(gateway):
    gateway.queued_responses = [
        content_response("not json"),
        content_response(json.dumps({"required_skills": ["Python"], "summary": "ok"})),
    ]

    result = run(make_client().complete_structured(JobAnalysis, "system", "user"))

    assert result.required_skills == ["Python"]
    assert len(gateway.requests) == 2


def test_complete_structured_gives_up_after_retries(gateway):
    gateway.next_response = content_response("still not json")

    with pytest.raises(LLMResponseError):
        run(make_client().complete_structured(JobAnalysis, "system", "user"))

    assert len(gateway.requests) == 3


def test_load_llm_settings_reads_only_env(monkeypatch):
    monkeypatch.setenv("PORTKEY_SLUGS", "slug-a, slug-b")
    monkeypatch.setenv("PORTKEY_AI_API", "key")
    monkeypatch.setenv("PORTKEY_MODEL", "custom-model")

    settings = load_llm_settings()

    assert settings.configured is True
    assert settings.slug == "slug-a"
    assert settings.model == "custom-model"


def test_load_llm_settings_default_model(monkeypatch):
    monkeypatch.setenv("PORTKEY_SLUGS", "slug-a")
    monkeypatch.setenv("PORTKEY_AI_API", "key")
    monkeypatch.delenv("PORTKEY_MODEL", raising=False)

    settings = load_llm_settings()

    assert settings.model == llm_module.DEFAULT_MODEL


def test_load_llm_settings_reports_missing(monkeypatch):
    monkeypatch.setenv("PORTKEY_SLUGS", "")
    monkeypatch.delenv("PORTKEY_AI_API", raising=False)

    settings = load_llm_settings()

    assert settings.configured is False
    assert "PORTKEY_AI_API" in settings.missing_configuration
    assert "PORTKEY_SLUGS" in settings.missing_configuration


def test_llm_client_singleton():
    reset_llm_client()
    first = get_llm_client()
    second = get_llm_client()

    assert first is second

    set_llm_client(make_client())
    assert get_llm_client() is not first

    reset_llm_client()


def test_base_agent_resolves_the_global_llm_client():
    from app.rag.agent import BaseAgent

    fake = make_client()
    set_llm_client(fake)
    try:
        assert BaseAgent().client is fake
    finally:
        reset_llm_client()
