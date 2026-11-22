"""Gmail SMTP delivery for interview reminders.

Uses only Python's standard library. SMTP credentials come from the existing
settings object and are deliberately excluded from its repr, logs and errors.
Email delivery is tracked separately from in-app notification status so an SMTP
failure can never prevent the in-app notification from being created.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from typing import Any

from app.core.config import settings
from app.database import reminder_queries, scheduling_queries
from app.database.connection import get_connection

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 30


def _transport() -> smtplib.SMTP:
    if settings.smtp_port == 465:
        client = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    else:
        client = smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
        )
        if settings.smtp_use_tls:
            client.starttls(context=ssl.create_default_context())
    return client


def _send_message(message: EmailMessage) -> None:
    """Send one message; SMTP exceptions propagate to the caller."""
    with _transport() as client:
        client.login(settings.smtp_email, settings.smtp_password)
        client.send_message(message)


def build_message(reminder: dict[str, Any]) -> EmailMessage:
    recipient = str(reminder.get("recipient_email") or "").strip()
    title = str(reminder.get("title") or "Interview reminder")
    body = str(reminder.get("message") or "")

    message = EmailMessage()
    message["Subject"] = title
    message["From"] = settings.smtp_email
    message["To"] = recipient
    message.set_content(
        f"{body}\n\n"
        "This is an automated reminder from Mitra. "
        "You can also view it in the Notifications panel."
    )
    return message


def send_test_email(recipient: str, subject: str, body: str) -> None:
    """Send a one-off message using the configured SMTP account."""
    if not settings.smtp_configured:
        raise RuntimeError("SMTP is not configured.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_email
    message["To"] = recipient
    message.set_content(body)
    _send_message(message)


def build_confirmation_message(interview: dict[str, Any]) -> EmailMessage:
    """Build a clean HTML confirmation email for the candidate."""
    recipient = str(interview.get("confirmation_email_recipient") or "").strip()
    candidate = escape(str(interview.get("candidate_name") or "there"))
    title = escape(str(interview.get("title") or "Interview"))
    date_text = escape(str(interview.get("interview_date") or ""))
    start = escape(str(interview.get("start_time") or "")[:5])
    end = escape(str(interview.get("end_time") or "")[:5])
    duration = escape(str(interview.get("duration_minutes") or 30))
    zone = escape(str(interview.get("time_zone") or "UTC"))
    online = interview.get("interview_type") == "online"
    mode = "Online" if online else "In-person"
    meeting_row = ""
    location_row = ""
    if online and interview.get("meeting_link"):
        link = escape(str(interview["meeting_link"]), quote=True)
        meeting_row = (
            '<p style="margin:6px 0"><strong>Meeting link:</strong> '
            f'<a href="{link}">{link}</a></p>'
        )
    if not online and interview.get("location"):
        location_row = (
            "<p style=\"margin:6px 0\"><strong>Location:</strong> "
            f"{escape(str(interview['location']))}</p>"
        )
    recruiter = str(interview.get("recruiter_email") or "").strip()
    recruiter_row = (
        f"<p style=\"margin:6px 0\"><strong>Recruiter:</strong> {escape(recruiter)}</p>"
        if recruiter
        else ""
    )
    company = escape(settings.app_name)

    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f5f8;font-family:Segoe UI,Arial,sans-serif;color:#1c1630">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #ece8f3;border-radius:14px;padding:28px">
    <p style="margin:0 0 6px;color:#6d4dff;font-weight:700;letter-spacing:.04em;font-size:12px">MITRA · INTERVIEW CONFIRMATION</p>
    <h1 style="margin:0 0 12px;font-size:22px">Hello {candidate},</h1>
    <p style="margin:0 0 18px;color:#555">Your interview has been scheduled successfully. Here are the details:</p>
    <div style="background:#f4f1ff;border-radius:10px;padding:16px;margin-bottom:18px">
      <p style="margin:6px 0"><strong>Interview:</strong> {title}</p>
      <p style="margin:6px 0"><strong>Date:</strong> {date_text}</p>
      <p style="margin:6px 0"><strong>Time:</strong> {start} – {end} ({zone})</p>
      <p style="margin:6px 0"><strong>Duration:</strong> {duration} minutes</p>
      <p style="margin:6px 0"><strong>Mode:</strong> {mode}</p>
      {meeting_row}{location_row}{recruiter_row}
    </div>
    <p style="margin:0;color:#777;font-size:12px">This confirmation was sent by {company}. Please contact your recruiter if you need to reschedule.</p>
  </div>
</body></html>"""
    text = (
        f"Hello {candidate},\n\nYour interview has been scheduled.\n"
        f"Interview: {title}\nDate: {date_text}\nTime: {start} - {end} ({zone})\n"
        f"Duration: {duration} minutes\nMode: {mode}\n"
        + (f"Meeting link: {interview['meeting_link']}\n" if meeting_row else "")
        + (f"Location: {interview['location']}\n" if location_row else "")
        + (f"Recruiter: {recruiter}\n" if recruiter_row else "")
    )

    message = EmailMessage()
    message["Subject"] = f"Interview confirmed: {title}"
    message["From"] = settings.smtp_email
    message["To"] = recipient
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


def send_pending_confirmations(limit: int = 20) -> dict[str, int]:
    """Deliver candidate confirmations; failures stay queued for retry."""
    result = {"sent": 0, "failed": 0, "skipped": 0}
    if not settings.smtp_configured:
        logger.warning("SMTP is not configured; confirmation delivery skipped.")
        return result

    with get_connection() as connection:
        scheduling_queries.recover_stale_confirmations(
            connection, settings.email_claim_timeout_minutes
        )
        rows = scheduling_queries.claim_confirmations(
            connection,
            retry_delay_minutes=settings.email_retry_delay_minutes,
            limit=limit,
        )

    for row in rows:
        try:
            _send_message(build_confirmation_message(row))
        except Exception as exc:  # noqa: BLE001 - never roll back the interview
            with get_connection() as connection:
                scheduling_queries.mark_confirmation_failed(
                    connection,
                    row["id"],
                    f"{type(exc).__name__}: {exc}",
                    settings.email_retry_delay_minutes,
                )
            logger.warning(
                "Confirmation email failed interview=%s error=%s",
                row["id"],
                type(exc).__name__,
            )
            result["failed"] += 1
        else:
            with get_connection() as connection:
                scheduling_queries.mark_confirmation_sent(connection, row["id"])
            logger.info("Confirmation email sent interview=%s", row["id"])
            result["sent"] += 1
    return result


def send_pending_emails(limit: int = 20) -> dict[str, int]:
    """Deliver emails for in-app notifications that are already created."""
    result = {"sent": 0, "failed": 0, "skipped": 0}
    if not settings.smtp_configured:
        logger.warning("SMTP is not configured; reminder email delivery skipped.")
        return result

    with get_connection() as connection:
        reminder_queries.recover_stale_sending(
            connection, settings.email_claim_timeout_minutes
        )
        rows = reminder_queries.claim_emails(
            connection,
            retry_delay_minutes=settings.email_retry_delay_minutes,
            limit=limit,
        )

    for row in rows:
        try:
            _send_message(build_message(row))
        except Exception as exc:  # noqa: BLE001 - never block in-app notifications
            with get_connection() as connection:
                reminder_queries.mark_email_failed(
                    connection,
                    row["id"],
                    f"{type(exc).__name__}: {exc}",
                    settings.email_retry_delay_minutes,
                )
            logger.warning(
                "Reminder email failed reminder=%s error=%s",
                row["id"],
                type(exc).__name__,
            )
            result["failed"] += 1
        else:
            with get_connection() as connection:
                reminder_queries.mark_email_sent(connection, row["id"])
            logger.info("Reminder email sent reminder=%s", row["id"])
            result["sent"] += 1
    return result
