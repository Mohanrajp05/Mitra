"""Tests for interview reminder generation and notification APIs."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.api import notifications as notification_api
from app.services import reminder_scheduler, reminder_service
from tests.conftest import TEST_USER_ID

INTERVIEW_ID = "44444444-4444-4444-8444-444444444444"
REMINDER_ID = "55555555-5555-4555-8555-555555555555"


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *args):
        return False


def _interview(hours_ahead: float):
    start = reminder_service.utcnow() + timedelta(hours=hours_ahead)
    return {
        "id": INTERVIEW_ID,
        "user_id": TEST_USER_ID,
        "starts_at": start,
        "interview_date": start.date(),
        "start_time": start.time().replace(microsecond=0),
        "candidate_name": "Test Candidate",
    }


@pytest.fixture
def fake_connection(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(reminder_service, "get_connection", lambda: _ConnectionContext(connection))
    return connection


def _capture_inserts(monkeypatch):
    calls = []

    def fake_insert(connection, values):
        calls.append(values)
        return True

    monkeypatch.setattr(reminder_service.reminder_queries, "insert_reminder", fake_insert)
    return calls


def test_two_reminders_for_future_interview(monkeypatch, fake_connection):
    calls = _capture_inserts(monkeypatch)
    created = reminder_service.generate_for_interview(TEST_USER_ID, _interview(48))
    assert created == 2
    assert [item["notification_type"] for item in calls] == ["24_hour", "1_hour"]
    assert calls[0]["scheduled_at"] < calls[1]["scheduled_at"]


def test_only_applicable_reminder_for_short_notice(monkeypatch, fake_connection):
    calls = _capture_inserts(monkeypatch)
    created = reminder_service.generate_for_interview(TEST_USER_ID, _interview(2))
    assert created == 1
    assert [item["notification_type"] for item in calls] == ["1_hour"]


def test_expired_reminders_are_skipped(monkeypatch, fake_connection):
    calls = _capture_inserts(monkeypatch)
    created = reminder_service.generate_for_interview(TEST_USER_ID, _interview(0.5))
    assert created == 0
    assert calls == []


def test_regenerate_cancels_old_pending(monkeypatch, fake_connection):
    calls = _capture_inserts(monkeypatch)
    cancelled = []

    def fake_cancel(connection, user_id, interview_id):
        cancelled.append((user_id, interview_id))
        return 2

    monkeypatch.setattr(reminder_service.reminder_queries, "cancel_pending", fake_cancel)
    reminder_service.regenerate_for_interview(TEST_USER_ID, _interview(48))
    assert cancelled == [(TEST_USER_ID, INTERVIEW_ID)]
    assert len(calls) == 2


def test_claim_due_is_delegated_once(monkeypatch, fake_connection):
    rows = [{"id": REMINDER_ID, "status": "sent"}]
    monkeypatch.setattr(
        reminder_service.reminder_queries, "claim_due", lambda connection, limit=50: rows
    )
    assert reminder_service.process_due_reminders() == rows


def test_scheduler_starts_only_once(monkeypatch):
    async def scenario():
        monkeypatch.setenv("REMINDER_SCHEDULER_ENABLED", "true")
        monkeypatch.setattr(reminder_scheduler, "dispatch_once", lambda: _noop())
        first = reminder_scheduler.start_scheduler()
        second = reminder_scheduler.start_scheduler()
        await reminder_scheduler.stop_scheduler()
        return first, second

    async def _noop():
        return 0

    first, second = asyncio_run(scenario())
    assert (first, second) == (True, False)


def asyncio_run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


def test_list_endpoint_uses_authenticated_owner(client, monkeypatch):
    seen = {}

    def fake_list(user_id, limit=100):
        seen["user_id"] = user_id
        return [_notification()]

    monkeypatch.setattr(notification_api.reminder_service, "list_notifications", fake_list)
    response = client.get("/api/notifications")
    assert response.status_code == 200
    assert seen["user_id"] == TEST_USER_ID
    assert response.json()[0]["notification_type"] == "1_hour"


def test_unread_count_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        notification_api.reminder_service, "unread_count", lambda user_id: 3
    )
    response = client.get("/api/notifications/unread-count")
    assert response.status_code == 200
    assert response.json() == {"count": 3}


def test_mark_read_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        notification_api.reminder_service,
        "mark_read",
        lambda user_id, reminder_id: _notification(status="read"),
    )
    response = client.patch(f"/api/notifications/{REMINDER_ID}/read")
    assert response.status_code == 200
    assert response.json()["status"] == "read"


def test_mark_read_returns_404_for_another_users_notification(client, monkeypatch):
    def missing(user_id, reminder_id):
        raise reminder_service.ReminderNotFoundError("Notification not found.")

    monkeypatch.setattr(notification_api.reminder_service, "mark_read", missing)
    response = client.patch(f"/api/notifications/{REMINDER_ID}/read")
    assert response.status_code == 404


def test_read_all_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        notification_api.reminder_service, "mark_all_read", lambda user_id: 2
    )
    monkeypatch.setattr(
        notification_api.reminder_service, "unread_count", lambda user_id: 0
    )
    response = client.patch("/api/notifications/read-all")
    assert response.status_code == 200
    assert response.json() == {"count": 0}


def _notification(**overrides):
    row = {
        "id": REMINDER_ID,
        "user_id": TEST_USER_ID,
        "interview_id": INTERVIEW_ID,
        "notification_type": "1_hour",
        "title": "Interview reminder: Test Candidate",
        "message": "Your 1 hour reminder.",
        "scheduled_at": datetime.now(timezone.utc),
        "status": "sent",
        "created_at": datetime.now(timezone.utc),
        "read_at": None,
        "interview_date": datetime.now(timezone.utc).date(),
        "start_time": datetime.now(timezone.utc).time().replace(microsecond=0),
        "candidate_name": "Test Candidate",
    }
    row.update(overrides)
    return row
