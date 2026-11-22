-- Candidate confirmation email state for scheduled interviews.
-- Kept separate from the 24-hour / 1-hour recruiter reminder statuses.

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS recruiter_email TEXT;

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS confirmation_email_status TEXT NOT NULL DEFAULT 'none'
    CHECK (confirmation_email_status IN ('none', 'pending', 'sending', 'sent', 'failed'));

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS confirmation_email_recipient TEXT;

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS confirmation_email_sent_at TIMESTAMPTZ;

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS confirmation_email_attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS confirmation_email_last_error TEXT;

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS confirmation_email_next_attempt_at TIMESTAMPTZ;

ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS confirmation_email_claimed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_confirmation_due
    ON scheduled_interviews (confirmation_email_status, confirmation_email_next_attempt_at)
    WHERE confirmation_email_status IN ('pending', 'failed', 'sending');
