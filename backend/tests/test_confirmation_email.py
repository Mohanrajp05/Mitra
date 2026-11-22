"""Tests for candidate confirmation emails (mocked SMTP transport)."""

from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.database import scheduling_queries
from app.services import email_service

INTERVIEW_ID = "77777777-7777-4777-8777-777777777777"


class FakeSMTP:
    fail = False
    messages = []

    def __init__(self, host, port, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, **kwargs):
        if FakeSMTP.fail:
            raise OSError("simulated")

    def login(self, user, password):
        if FakeSMTP.fail:
            raise OSError("simulated")

    def send_message(self, message):
        if FakeSMTP.fail:
            raise OSError("simulated")
        FakeSMTP.messages.append(message)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.fail = False
    FakeSMTP.messages = []
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


@pytest.fixture
def queue(monkeypatch):
    calls = {"sent": [], "failed": [], "claimed": 0}
    interview = {
        "id": INTERVIEW_ID,
        "candidate_name": "Test Candidate",
        "candidate_email": "candidate@example.com",
        "confirmation_email_recipient": "candidate@example.com",
        "recruiter_email": "recruiter@example.com",
        "title": "Frontend interview",
        "interview_date": "2026-12-01",
        "start_time": "10:30",
        "end_time": "11:00",
        "duration_minutes": 30,
        "interview_type": "online",
        "meeting_link": "https://meet.example.com/x",
        "location": None,
        "time_zone": "UTC",
    }

    class _Context:
        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(email_service, "get_connection", lambda: _Context())
    monkeypatch.setattr(scheduling_queries, "recover_stale_confirmations", lambda *a: 0)

    def claim(connection, **kwargs):
        calls["claimed"] += 1
        return [interview] if calls["claimed"] == 1 else []

    monkeypatch.setattr(scheduling_queries, "claim_confirmations", claim)
    monkeypatch.setattr(
        scheduling_queries,
        "mark_confirmation_sent",
        lambda connection, interview_id: calls["sent"].append(interview_id) or True,
    )
    monkeypatch.setattr(
        scheduling_queries,
        "mark_confirmation_failed",
        lambda connection, interview_id, error, delay: calls["failed"].append(interview_id) or True,
    )
    return calls


def _interview(**overrides):
    row = {
        "confirmation_email_recipient": "candidate@example.com",
        "candidate_name": "Test Candidate",
        "title": "Frontend interview",
        "interview_date": "2026-12-01",
        "start_time": "10:30",
        "end_time": "11:00",
        "duration_minutes": 30,
        "interview_type": "online",
        "meeting_link": "https://meet.example.com/x",
        "location": None,
        "recruiter_email": "recruiter@example.com",
        "time_zone": "UTC",
    }
    row.update(overrides)
    return row


def test_confirmation_contains_interview_details():
    message = email_service.build_confirmation_message(_interview())
    html = message.get_body(preferencelist=("html",)).get_content()
    assert message["To"] == "candidate@example.com"
    assert message["From"] == str(settings.smtp_email)
    assert "Interview confirmed" in message["Subject"]
    for value in (
        "Test Candidate", "Frontend interview", "2026-12-01", "10:30",
        "30", "Online", "https://meet.example.com/x", "recruiter@example.com",
    ):
        assert value in html


def test_in_person_confirmation_uses_location():
    message = email_service.build_confirmation_message(
        _interview(interview_type="in_person", location="Office 4", meeting_link=None)
    )
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "In-person" in html
    assert "Office 4" in html


def test_successful_confirmation_marks_sent(smtp, queue):
    result = email_service.send_pending_confirmations()
    assert result == {"sent": 1, "failed": 0, "skipped": 0}
    assert queue["sent"] == [INTERVIEW_ID]
    assert smtp.messages


def test_smtp_failure_keeps_interview_and_marks_failed(smtp, queue):
    smtp.fail = True
    result = email_service.send_pending_confirmations()
    assert result["failed"] == 1
    assert queue["failed"] == [INTERVIEW_ID]
    assert queue["sent"] == []


def test_duplicate_confirmation_prevention(smtp, queue):
    email_service.send_pending_confirmations()
    second = email_service.send_pending_confirmations()
    assert second["sent"] == 0
    assert queue["sent"] == [INTERVIEW_ID]


def test_missing_credentials_skips_confirmations(monkeypatch, smtp, queue):
    monkeypatch.setattr(
        type(settings), "smtp_configured", property(lambda self: False)
    )
    assert email_service.send_pending_confirmations() == {
        "sent": 0, "failed": 0, "skipped": 0
    }
    assert queue["claimed"] == 0
    assert smtp.messages == []


def test_claim_query_excludes_sent_and_sending():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{"id": INTERVIEW_ID}]
    cursor.rowcount = 1
    scheduling_queries.claim_confirmations(connection, retry_delay_minutes=15)
    sql = " ".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert "confirmation_email_status IN ('pending', 'failed')" in sql
    assert "confirmation_email_status = 'sending'" in sql
