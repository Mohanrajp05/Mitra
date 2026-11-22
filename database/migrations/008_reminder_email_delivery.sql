-- Gmail/email delivery state for interview reminders.
-- In-app notification status is unchanged ('sent' still means delivered in-app).
-- Email delivery is tracked separately so SMTP failures never block notifications.

ALTER TABLE interview_reminders
    ADD COLUMN IF NOT EXISTS recipient_email TEXT;

ALTER TABLE interview_reminders
    ADD COLUMN IF NOT EXISTS email_status TEXT NOT NULL DEFAULT 'none'
    CHECK (email_status IN ('none', 'pending', 'sending', 'sent', 'failed'));

ALTER TABLE interview_reminders
    ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMPTZ;

ALTER TABLE interview_reminders
    ADD COLUMN IF NOT EXISTS email_last_error TEXT;

ALTER TABLE interview_reminders
    ADD COLUMN IF NOT EXISTS email_attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE interview_reminders
    ADD COLUMN IF NOT EXISTS email_claimed_at TIMESTAMPTZ;

ALTER TABLE interview_reminders
    ADD COLUMN IF NOT EXISTS email_next_attempt_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_interview_reminders_email_due
    ON interview_reminders (email_status, email_next_attempt_at)
    WHERE email_status IN ('pending', 'failed', 'sending');
