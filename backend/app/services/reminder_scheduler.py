"""Periodic in-app reminder dispatcher.

Uses the project's existing asyncio-task pattern (no new dependency). Multiple
application workers are safe because reminder claiming is serialized by a
transaction-level PostgreSQL advisory lock with SKIP LOCKED. Set
``REMINDER_SCHEDULER_ENABLED=false`` on worker processes that should not run the
dispatcher.
"""

from __future__ import annotations

import asyncio
import logging
import os

from anyio import to_thread

from app.services import reminder_service

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def _poll_seconds() -> float:
    try:
        return max(5.0, float(os.getenv("REMINDER_POLL_SECONDS", "60")))
    except ValueError:
        return 60.0


def enabled() -> bool:
    return os.getenv("REMINDER_SCHEDULER_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }


async def dispatch_once() -> int:
    claimed = await to_thread.run_sync(reminder_service.process_due_reminders)
    # Email delivery is a best-effort follow-up: a failure here must never
    # affect the in-app notification that was just created above.
    try:
        from app.services import email_service

        await to_thread.run_sync(email_service.send_pending_emails)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - dispatcher must keep running
        logger.warning("Reminder email dispatch failed: %s", type(exc).__name__)
    # Candidate confirmations are a separate queue; a failure here must not
    # affect reminder delivery or in-app notifications.
    try:
        from app.services import email_service

        await to_thread.run_sync(email_service.send_pending_confirmations)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Confirmation email dispatch failed: %s", type(exc).__name__)
    return len(claimed)


async def _dispatch_loop() -> None:
    interval = _poll_seconds()
    while True:
        try:
            count = await dispatch_once()
            if count:
                logger.info("Processed %d due interview reminder(s).", count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - dispatcher must keep running
            logger.warning("Reminder dispatch failed: %s", type(exc).__name__)
        await asyncio.sleep(interval)


def start_scheduler() -> bool:
    """Start one dispatcher per process; returns True when started."""
    global _task
    if not enabled():
        return False
    if _task is not None and not _task.done():
        return False
    _task = asyncio.create_task(_dispatch_loop())
    return True


async def stop_scheduler() -> None:
    global _task
    task = _task
    _task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001
        pass
