"""Tests for persisted interview scheduling: validation, conflicts and API."""

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api import scheduling as scheduling_api
from app.schemas.scheduling import ScheduledInterviewCreate, ScheduledInterviewUpdate
from app.services import scheduling_service as service
from tests.conftest import TEST_USER_ID

CANDIDATE_ID = "22222222-2222-4222-8222-222222222222"
INTERVIEW_ID = "33333333-3333-4333-8333-333333333333"

FUTURE = date.today() + timedelta(days=3)
PAST = date.today() - timedelta(days=1)


def _create_payload(**overrides):
    data = {
        "candidate_id": CANDIDATE_ID,
        "title": "Frontend interview",
        "interview_date": FUTURE,
        "start_time": time(10, 0),
        "time_zone": "UTC",
        "duration_minutes": 30,
        "interview_type": "online",
        "meeting_link": "https://meet.example.com/interview",
        "location": None,
        "notes": None,
    }
    data.update(overrides)
    return ScheduledInterviewCreate(**data)


def _row(**overrides):
    row = {
        "id": INTERVIEW_ID,
        "user_id": TEST_USER_ID,
        "candidate_id": CANDIDATE_ID,
        "candidate_name": "Test Candidate",
        "candidate_email": "candidate@example.com",
        "title": "Frontend interview",
        "interview_date": FUTURE,
        "start_time": time(10, 0),
        "end_time": time(10, 30),
        "starts_at": datetime.combine(FUTURE, time(10, 0), tzinfo=timezone.utc),
        "ends_at": datetime.combine(FUTURE, time(10, 30), tzinfo=timezone.utc),
        "duration_minutes": 30,
        "interview_type": "online",
        "meeting_link": "https://meet.example.com/interview",
        "location": None,
        "notes": None,
        "status": "scheduled",
        "time_zone": "UTC",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.fixture(autouse=True)
def stub_reminder_generation(monkeypatch):
    """Scheduling tests focus on slots; reminder creation is tested separately."""
    monkeypatch.setattr(
        "app.services.scheduling_service.reminder_service.generate_for_interview",
        lambda *args, **kwargs: 2,
    )
    monkeypatch.setattr(
        "app.services.scheduling_service.reminder_service.regenerate_for_interview",
        lambda *args, **kwargs: 2,
    )
    monkeypatch.setattr(
        "app.services.scheduling_service.reminder_service.cancel_for_interview",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "app.services.scheduling_service.email_service.send_pending_confirmations",
        lambda *args, **kwargs: {"sent": 0, "failed": 0, "skipped": 0},
    )


@pytest.fixture
def owned_candidate(monkeypatch):
    monkeypatch.setattr(
        service.candidate_service,
        "get_candidate",
        lambda user_id, candidate_id: {"id": CANDIDATE_ID, "full_name": "Test Candidate", "email": "candidate@example.com"},
    )


def test_time_window_uses_configured_timezone():
    starts_at, ends_at, end_time = service._time_window(
        FUTURE, time(10, 0), 30, "Asia/Kolkata"
    )
    assert starts_at.utcoffset() == timedelta(0)
    assert ends_at - starts_at == timedelta(minutes=30)
    assert end_time == time(10, 30)


def test_unknown_timezone_is_rejected():
    with pytest.raises(service.SchedulingValidationError, match="time zone"):
        service._time_window(FUTURE, time(10, 0), 30, "Not/AZone")


def test_past_slot_is_rejected(owned_candidate, monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(service, "get_connection", lambda: _ConnectionContext(connection))
    with pytest.raises(service.SchedulingValidationError, match="already passed"):
        service.create_interview(TEST_USER_ID, _create_payload(interview_date=PAST))


def test_conflicting_slot_is_rejected(owned_candidate, monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(service, "get_connection", lambda: _ConnectionContext(connection))
    monkeypatch.setattr(
        service.scheduling_queries,
        "find_overlap",
        lambda connection, **kwargs: _row(),
    )
    with pytest.raises(service.SchedulingConflictError):
        service.create_interview(TEST_USER_ID, _create_payload())


def test_online_requires_meeting_link(owned_candidate):
    with pytest.raises(service.SchedulingValidationError, match="meeting link"):
        service.create_interview(TEST_USER_ID, _create_payload(meeting_link=None))


def test_unowned_candidate_is_rejected(monkeypatch):
    monkeypatch.setattr(service.candidate_service, "get_candidate", lambda *args: None)
    with pytest.raises(service.SchedulingNotFoundError):
        service.create_interview(TEST_USER_ID, _create_payload())


def test_completed_interview_cannot_be_rescheduled(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(service, "get_connection", lambda: _ConnectionContext(connection))
    monkeypatch.setattr(service.scheduling_queries, "get_interview", lambda *args: _row(status="completed"))
    with pytest.raises(service.SchedulingValidationError, match="upcoming"):
        service.update_interview(
            TEST_USER_ID,
            INTERVIEW_ID,
            ScheduledInterviewUpdate(interview_date=FUTURE, start_time=time(11, 0)),
        )


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *args):
        return False


def test_create_endpoint_uses_authenticated_owner(client, monkeypatch):
    seen = {}

    def fake_create(user_id, payload, recruiter_email=None):
        seen["user_id"] = user_id
        seen["candidate_id"] = payload.candidate_id
        return _row()

    monkeypatch.setattr(scheduling_api.scheduling_service, "create_interview", fake_create)
    response = client.post(
        "/api/scheduled-interviews",
        json=_create_payload().model_dump(mode="json"),
    )
    assert response.status_code == 201
    assert seen["user_id"] == TEST_USER_ID
    assert response.json()["candidate_id"] == CANDIDATE_ID


def test_conflict_returns_409(client, monkeypatch):
    def conflict(*args, **kwargs):
        raise service.SchedulingConflictError("Slot conflicts with an existing interview.")

    monkeypatch.setattr(scheduling_api.scheduling_service, "create_interview", conflict)
    response = client.post(
        "/api/scheduled-interviews",
        json=_create_payload().model_dump(mode="json"),
    )
    assert response.status_code == 409
    assert "conflicts" in response.json()["detail"]


def test_past_date_returns_422(client, monkeypatch):
    def past(*args, **kwargs):
        raise service.SchedulingValidationError("That time has already passed.")

    monkeypatch.setattr(scheduling_api.scheduling_service, "create_interview", past)
    response = client.post(
        "/api/scheduled-interviews",
        json=_create_payload(interview_date=PAST).model_dump(mode="json"),
    )
    assert response.status_code == 422


def test_unowned_candidate_returns_404(client, monkeypatch):
    def missing(*args, **kwargs):
        raise service.SchedulingNotFoundError("Candidate not found.")

    monkeypatch.setattr(scheduling_api.scheduling_service, "create_interview", missing)
    response = client.post(
        "/api/scheduled-interviews",
        json=_create_payload().model_dump(mode="json"),
    )
    assert response.status_code == 404


def test_list_uses_authenticated_owner(client, monkeypatch):
    seen = {}

    def fake_list(user_id, **kwargs):
        seen["user_id"] = user_id
        return [_row()]

    monkeypatch.setattr(scheduling_api.scheduling_service, "list_interviews", fake_list)
    response = client.get("/api/scheduled-interviews")
    assert response.status_code == 200
    assert seen["user_id"] == TEST_USER_ID


def test_cancel_preserves_history(client, monkeypatch):
    seen = {}

    def fake_update(user_id, interview_id, payload, recruiter_email=None):
        seen.update(user_id=user_id, interview_id=interview_id, status=payload.status)
        return _row(status="cancelled")

    monkeypatch.setattr(scheduling_api.scheduling_service, "update_interview", fake_update)
    response = client.patch(
        f"/api/scheduled-interviews/{INTERVIEW_ID}", json={"status": "cancelled"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert seen == {"user_id": TEST_USER_ID, "interview_id": INTERVIEW_ID, "status": "cancelled"}


def test_availability_uses_owner_and_candidate(client, monkeypatch):
    seen = {}

    def fake_availability(user_id, candidate_id, day):
        seen.update(user_id=user_id, candidate_id=candidate_id, day=day)
        return {"candidate_id": candidate_id, "interview_date": day, "booked_slots": ["10:00"]}

    monkeypatch.setattr(scheduling_api.scheduling_service, "availability", fake_availability)
    response = client.get(
        "/api/scheduled-interviews/availability",
        params={"candidate_id": CANDIDATE_ID, "interview_date": FUTURE.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["booked_slots"] == ["10:00"]
    assert seen["user_id"] == TEST_USER_ID


@pytest.mark.parametrize("minutes", [10, 30])
def test_supported_durations_are_accepted(minutes):
    payload = _create_payload(duration_minutes=minutes).model_dump()
    assert ScheduledInterviewCreate(**payload).duration_minutes == minutes


def test_unsupported_duration_is_rejected():
    payload = {
        "candidate_id": CANDIDATE_ID,
        "title": "Frontend interview",
        "interview_date": FUTURE,
        "start_time": time(10, 0),
        "duration_minutes": 15,
        "interview_type": "online",
        "meeting_link": "https://meet.example.com/interview",
    }
    with pytest.raises(ValidationError):
        ScheduledInterviewCreate(**payload)
