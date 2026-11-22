-- In-app interview reminders / notifications.
--
-- A reminder row becomes a visible in-app notification once the scheduler
-- claims it and moves it from 'pending' to 'sent'. Cancelled reminders are
-- kept for history; the partial unique index prevents duplicate active
-- reminders for the same interview and notification type.

CREATE TABLE IF NOT EXISTS interview_reminders (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL,
    interview_id      UUID NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL
                      CHECK (notification_type IN ('24_hour', '1_hour')),
    title             TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    message           TEXT NOT NULL CHECK (length(btrim(message)) > 0),
    scheduled_at      TIMESTAMPTZ NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'sent', 'read', 'cancelled')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at           TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_interview_reminders_active
    ON interview_reminders (interview_id, notification_type)
    WHERE status <> 'cancelled';

CREATE INDEX IF NOT EXISTS idx_interview_reminders_user_created
    ON interview_reminders (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_interview_reminders_user_status
    ON interview_reminders (user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_interview_reminders_due
    ON interview_reminders (status, scheduled_at)
    WHERE status = 'pending';
