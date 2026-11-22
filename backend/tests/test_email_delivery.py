
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core import config as config_module
from app.core.config import settings
from app.database import reminder_queries
from app.services import email_service
from tests.conftest import TEST_USER_ID

REMINDER_ID = "66666666-6666-4666-8666-666666666666"


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *args):
        return False


class FakeSMTP:
    instances = []
    fail = False

    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, **kwargs):
        if FakeSMTP.fail:
            raise OSError("simulated TLS failure")

    def login(self, user, password):
        if FakeSMTP.fail:
            raise OSError("simulated auth failure")

    def send_message(self, message):
        if FakeSMTP.fail:
            raise OSError("simulated send failure")
        self.messages.append(message)


def _reminder():
    return {
        "id": REMINDER_ID,
        "user_id": TEST_USER_ID,
        "notification_type": "1_hour",
        "title": "Interview reminder: Test Candidate",
        "message": "Your interview is in 1 hour.",
        "recipient_email": "recruiter@example.com",
        "status": "sent",
    }


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail = False
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


@pytest.fixture
def email_mocks(monkeypatch):
    calls = {"sent": [], "failed": [], "claimed": 0}

    monkeypatch.setattr(email_service, "get_connection", lambda: _ConnectionContext(MagicMock()))
    monkeypatch.setattr(reminder_queries, "recover_stale_sending", lambda *a: 0)

    def claim(connection, **kwargs):
        calls["claimed"] += 1
        return [_reminder()] if calls["claimed"] == 1 else []

    monkeypatch.setattr(reminder_queries, "claim_emails", claim)
    monkeypatch.setattr(
        reminder_queries,
        "mark_email_sent",
        lambda connection, reminder_id: calls["sent"].append(reminder_id) or True,
    )
    monkeypatch.setattr(
        reminder_queries,
        "mark_email_failed",
        lambda connection, reminder_id, error, delay: calls["failed"].append(reminder_id) or True,
    )
    return calls


def test_missing_credentials_skips_delivery(monkeypatch, email_mocks, smtp):
    monkeypatch.setattr(
        type(settings), "smtp_configured", property(lambda self: False)
    )
    result = email_service.send_pending_emails()
    assert result == {"sent": 0, "failed": 0, "skipped": 0}
    assert email_mocks["claimed"] == 0
    assert smtp.instances == []


def test_successful_delivery_marks_email_sent(email_mocks, smtp):
    result = email_service.send_pending_emails()
    assert result == {"sent": 1, "failed": 0, "skipped": 0}
    assert email_mocks["sent"] == [REMINDER_ID]
    assert email_mocks["failed"] == []
    assert len(smtp.instances[-1].messages) == 1
    message = smtp.instances[-1].messages[0]
    assert message["To"] == "recruiter@example.com"
    assert "Interview reminder" in message["Subject"]


def test_smtp_failure_does_not_mark_delivered(email_mocks, smtp):
    smtp.fail = True
    result = email_service.send_pending_emails()
    assert result["sent"] == 0
    assert result["failed"] == 1
    assert email_mocks["failed"] == [REMINDER_ID]
    assert email_mocks["sent"] == []


def test_duplicate_prevention_claim_excludes_already_sent():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{"id": REMINDER_ID}]
    cursor.rowcount = 1
    reminder_queries.claim_emails(connection, retry_delay_minutes=15)
    sql = " ".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert "email_status IN ('pending', 'failed')" in sql
    assert "SET email_status = 'sending'" in sql
    assert "recipient_email IS NOT NULL" in sql


def test_mark_sent_requires_sending_state():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1
    reminder_queries.mark_email_sent(connection, REMINDER_ID)
    sql = str(cursor.execute.call_args.args[0])
    assert "email_status = 'sending'" in sql


def test_settings_load_smtp_without_exposing_secret():
    assert settings.smtp_host == "smtp.gmail.com"
    assert settings.smtp_port in (465, 587)
    assert settings.smtp_configured is True
    assert "smtp_password" not in repr(settings)
    assert "smtp_email" not in repr(settings)


def test_build_message_uses_recruiter_recipient():
    message = email_service.build_message(_reminder())
    assert message["To"] == "recruiter@example.com"
    assert message["From"] == str(settings.smtp_email)
