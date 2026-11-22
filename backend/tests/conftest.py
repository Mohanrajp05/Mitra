

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def rag_dir():
    directory = Path(tempfile.mkdtemp(prefix="rag-test-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(autouse=True)
def disable_database_pool(monkeypatch):
    """Prevent real PostgreSQL connections during the test suite."""
    monkeypatch.setattr("app.main.open_pool", lambda: None)
    monkeypatch.setattr("app.main.close_pool", lambda: None)


@pytest.fixture(autouse=True)
def fresh_rate_limiter():
    """Give every test a clean in-process rate limiter."""
    from app.core import rate_limit

    saved = rate_limit.get_rate_limiter()
    limiter = rate_limit.SlidingWindowRateLimiter(30, 60.0)
    rate_limit.set_rate_limiter(limiter)
    try:
        yield limiter
    finally:
        rate_limit.set_rate_limiter(saved)


@pytest.fixture(autouse=True)
def fresh_response_cache():
    """Give every test a clean in-process response cache."""
    from app.rag import response_cache

    saved = response_cache.get_response_cache()
    cache = response_cache.ResponseCache(response_cache.load_cache_settings())
    response_cache.set_response_cache(cache)
    try:
        yield cache
    finally:
        response_cache.set_response_cache(saved)


@pytest.fixture(autouse=True)
def fresh_match_cache():
    """Give every test a clean in-process match-result cache."""
    from app.rag import match_cache

    saved = match_cache.get_match_cache()
    cache = match_cache.MatchCache(match_cache.load_match_cache_settings())
    match_cache.set_match_cache(cache)
    try:
        yield cache
    finally:
        match_cache.set_match_cache(saved)


@pytest.fixture(autouse=True)
def fresh_metrics():
    """Give every test a clean in-memory metrics registry."""
    from app.core import metrics

    saved = metrics.get_metrics()
    registry = metrics.MetricsRegistry()
    metrics.set_metrics(registry)
    try:
        yield registry
    finally:
        metrics.set_metrics(saved)


@pytest.fixture(autouse=True)
def fresh_audit_trail():
    """Give every test a clean in-memory audit trail."""
    from app.core import audit

    saved = audit.get_audit_trail()
    trail = audit.AuditTrail()
    audit.set_audit_trail(trail)
    try:
        yield trail
    finally:
        audit.set_audit_trail(saved)


@pytest.fixture(autouse=True)
def disable_llm_intent_check(monkeypatch):
    """Keep chat tests offline: the hybrid intent check fails open."""

    async def undecided(text, client=None):
        return None

    monkeypatch.setattr(
        "app.services.chat_service.classify_unclear_message", undecided
    )


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: {
        "id": TEST_USER_ID,
        "email": "student@example.com",
        "user_metadata": {},
    }
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
