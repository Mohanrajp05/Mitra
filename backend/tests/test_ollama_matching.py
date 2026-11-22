import asyncio

import httpx
import pytest

from app.rag.ollama import (
    OllamaClient,
    OllamaResponseError,
    OllamaSettings,
    OllamaUnavailableError,
    load_ollama_settings,
)
from app.schemas.rag import MatchResult


def run(coro):
    return asyncio.run(coro)


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class Client:
    response = None
    error = None
    requests = []

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        Client.requests.append((url, json))
        if Client.error:
            raise Client.error
        return Client.response


@pytest.fixture
def ollama(monkeypatch):
    Client.response = None
    Client.error = None
    Client.requests = []
    monkeypatch.setattr("app.rag.ollama.httpx.AsyncClient", Client)
    return OllamaClient(OllamaSettings("http://localhost:11434", "llama3.1:8b", 10))


def payload(score=82):
    return {
        "message": {"content": __import__("json").dumps({
            "match_score": score,
            "matched_skills": ["Python"],
            "partial_skills": ["Docker"],
            "missing_skills": ["Kubernetes"],
            "unverified_skills": ["Docker"],
            "relevance": "strong",
            "relevance_score": score / 100,
            "experience_comparison": "Candidate meets the experience target.",
            "explanation": "Python is supported by the resume.",
            "evidence": [{"quote": "Python developer", "source": "resume"}],
        })}
    }


def test_ollama_matching_posts_to_local_chat_endpoint(ollama):
    Client.response = Response(payload())

    result = run(ollama.complete_structured(MatchResult, "system", "job and resume"))

    assert result.match_score == 82
    url, request = Client.requests[0]
    assert url == "http://localhost:11434/api/chat"
    assert request["model"] == "llama3.1:8b"
    assert request["stream"] is False
    assert request["format"] == "json"
    assert request["options"]["num_ctx"] == 8192
    assert request["keep_alive"] == "30m"
    assert "match_score" in request["messages"][1]["content"]


def test_ollama_rejects_malformed_match_json(ollama):
    Client.response = Response({"message": {"content": "not json"}})

    with pytest.raises(OllamaResponseError):
        run(ollama.complete_structured(MatchResult, "system", "prompt"))


def test_ollama_unavailable_is_reported(ollama):
    Client.error = httpx.ConnectError("offline")

    with pytest.raises(OllamaUnavailableError):
        run(ollama.complete_structured(MatchResult, "system", "prompt"))


def test_ollama_settings_bound_context_window(monkeypatch):
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    settings = load_ollama_settings()
    assert settings.num_ctx == 8192
    assert settings.keep_alive == "30m"

    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    settings = load_ollama_settings()
    assert settings.num_ctx == 4096
    assert settings.keep_alive == "10m"
