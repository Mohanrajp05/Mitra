-- Persisted interview scheduling (calendar appointments).
--
-- Stores wall-clock date/time in the recruiter's configured time zone as well
-- as UTC instants used for past-time validation and overlap detection.
-- Historical rows (cancelled / completed / missed) are never deleted.

CREATE TABLE IF NOT EXISTS scheduled_interviews (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL,
    candidate_id     UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    title            TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    interview_date   DATE NOT NULL,
    start_time       TIME NOT NULL,
    end_time         TIME NOT NULL,
    starts_at        TIMESTAMPTZ NOT NULL,
    ends_at          TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 30 CHECK (duration_minutes = 30),
    interview_type   TEXT NOT NULL DEFAULT 'online'
                     CHECK (interview_type IN ('online', 'in_person')),
    meeting_link     TEXT,
    location         TEXT,
    notes            TEXT,
    status           TEXT NOT NULL DEFAULT 'scheduled'
                     CHECK (status IN ('scheduled', 'completed', 'cancelled', 'missed')),
    time_zone        TEXT NOT NULL DEFAULT 'UTC',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at),
    CHECK (
        (interview_type = 'online' AND meeting_link IS NOT NULL AND length(btrim(meeting_link)) > 0)
        OR (interview_type = 'in_person' AND location IS NOT NULL AND length(btrim(location)) > 0)
    )
);

-- Exact duplicate protection; overlap protection is enforced in the service
-- under an advisory transaction lock.
CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_interviews_candidate_start
    ON scheduled_interviews (candidate_id, starts_at) WHERE status <> 'cancelled';

CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_interviews_user_start
    ON scheduled_interviews (user_id, starts_at) WHERE status <> 'cancelled';

CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_user_starts
    ON scheduled_interviews (user_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_candidate_starts
    ON scheduled_interviews (candidate_id, starts_at);

DROP TRIGGER IF EXISTS scheduled_interviews_set_updated_at ON scheduled_interviews;
CREATE TRIGGER scheduled_interviews_set_updated_at
    BEFORE UPDATE ON scheduled_interviews
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
