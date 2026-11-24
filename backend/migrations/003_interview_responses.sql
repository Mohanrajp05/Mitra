-- Phase 3: Candidate interview responses
ALTER TABLE scheduled_interviews
    ADD COLUMN IF NOT EXISTS candidate_response TEXT NOT NULL DEFAULT 'awaiting'
        CHECK (candidate_response IN ('awaiting','accepted','declined','reschedule_requested','rescheduled')),
    ADD COLUMN IF NOT EXISTS response_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS decline_reason TEXT,
    ADD COLUMN IF NOT EXISTS reschedule_requested_date DATE,
    ADD COLUMN IF NOT EXISTS reschedule_requested_start_time TIME,
    ADD COLUMN IF NOT EXISTS reschedule_reason TEXT,
    ADD COLUMN IF NOT EXISTS reschedule_status TEXT
        CHECK (reschedule_status IS NULL OR reschedule_status IN ('pending','approved','rejected')),
    ADD COLUMN IF NOT EXISTS reschedule_decided_at TIMESTAMPTZ;
