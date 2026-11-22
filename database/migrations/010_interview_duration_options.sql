-- Allow 10-minute and 30-minute interview durations.
-- Existing rows are all 30 minutes, so no data migration is needed.

ALTER TABLE scheduled_interviews
    DROP CONSTRAINT IF EXISTS scheduled_interviews_duration_minutes_check;

ALTER TABLE scheduled_interviews
    ADD CONSTRAINT scheduled_interviews_duration_minutes_check
    CHECK (duration_minutes IN (10, 30));
