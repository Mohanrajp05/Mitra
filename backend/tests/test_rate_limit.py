"""Rate-limit tests: limiter unit behavior and chat API enforcement."""

import pytest

from app.api import chat as chat_api
from app.core import rate_limit
from app.core.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter
from app.main import app
from tests.conftest import TEST_USER_ID

SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
MESSAGE_URL = f"/api/chat/sessions/{SESSION_ID}/messages"

EXCHANGE = {
    "user_message": {
        "id": "11111111-2222-4333-8444-555555555555",
        "session_id": SESSION_ID,
        "owner_user_id": TEST_USER_ID,
        "role": "user",
        "content": "Who has Python experience?",
        "sources": [],
        "has_evidence": True,
        "created_at": "2026-11-14T10:01:00Z",
    },
    "assistant_message": {
        "id": "66666666-7777-4888-8999-000000000000",
        "session_id": SESSION_ID,
        "owner_user_id": TEST_USER_ID,
        "role": "assistant",
        "content": "Jane Doe has Python experience.",
        "sources": [],
        "has_evidence": True,
        "created_at": "2026-11-14T10:01:05Z",
    },
}


async def fake_send(*args, **kwargs):
    return EXCHANGE


class TestSlidingWindowLimiter:
    def test_allows_up_to_limit(self):
        limiter = SlidingWindowRateLimiter(3, 60.0)
        for _ in range(3):
            allowed, retry_after = limiter.acquire("user-1")
            assert allowed is True
            assert retry_after == 0.0

    def test_blocks_over_limit(self):
        limiter = SlidingWindowRateLimiter(2, 60.0)
        limiter.acquire("user-1")
        limiter.acquire("user-1")
        allowed, retry_after = limiter.acquire("user-1")
        assert allowed is False
        assert retry_after >= 1.0

    def test_keys_are_independent(self):
        limiter = SlidingWindowRateLimiter(1, 60.0)
        allowed, _ = limiter.acquire("user-1")
        allowed_other, _ = limiter.acquire("user-2")
        assert allowed is True
        assert allowed_other is True

    def test_clear_resets_all_windows(self):
        limiter = SlidingWindowRateLimiter(1, 60.0)
        limiter.acquire("user-1")
        limiter.clear()
        allowed, _ = limiter.acquire("user-1")
        assert allowed is True

    def test_invalid_configuration_rejected(self):
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(0, 60.0)
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(5, 0)


class TestChatApiRateLimit:
    def test_rate_limit_returns_429_with_retry_after(self, client, monkeypatch):
        monkeypatch.setattr(
            chat_api.chat_service,
            "send_message",
            fake_send,
        )
        limiter = rate_limit.get_rate_limiter()
        limiter.max_requests = 2

        first = client.post(MESSAGE_URL, json={"content": "Who has Python experience?"})
        second = client.post(MESSAGE_URL, json={"content": "Who has Python experience?"})
        third = client.post(MESSAGE_URL, json={"content": "Who has Python experience?"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert "Retry-After" in third.headers
        assert third.headers["Retry-After"] >= "1"
        assert "too many" in third.json()["detail"].lower()
        assert third.headers.get("X-Request-ID")

    def test_rate_limit_is_per_user(self, client, monkeypatch):
        monkeypatch.setattr(
            chat_api.chat_service,
            "send_message",
            fake_send,
        )
        limiter = rate_limit.get_rate_limiter()
        limiter.max_requests = 1

        first = client.post(MESSAGE_URL, json={"content": "Who has Python experience?"})
        assert first.status_code == 200

        app.dependency_overrides[chat_api.get_current_user] = lambda: {
            "id": "33333333-3333-4333-8333-333333333333",
            "email": "other@example.com",
            "user_metadata": {},
        }
        try:
            other = client.post(
                MESSAGE_URL, json={"content": "Who has Python experience?"}
            )
            assert other.status_code == 200
        finally:
            app.dependency_overrides[chat_api.get_current_user] = lambda: {
                "id": TEST_USER_ID,
                "email": "student@example.com",
                "user_metadata": {},
            }

    def test_rate_limit_applies_before_service_call(self, client, monkeypatch):
        def fail_send(*args, **kwargs):
            raise AssertionError("service must not run when rate limited")

        monkeypatch.setattr(chat_api.chat_service, "send_message", fail_send)
        limiter = rate_limit.get_rate_limiter()
        limiter.max_requests = 1

        client.post(MESSAGE_URL, json={"content": "Who has Python experience?"})
        blocked = client.post(MESSAGE_URL, json={"content": "Who has Python experience?"})

        assert blocked.status_code == 429

    def test_rate_limit_error_carries_retry_after(self):
        error = RateLimitExceeded(7.4)
        assert error.retry_after == 7
