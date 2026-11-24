-- ===========================================================================
-- AI Recruitment Agent - PostgreSQL application database (Phase 1)
-- Run this file against the SEPARATE PostgreSQL database, never Supabase.
-- Example:
--   psql -U postgres -d ai_recruitment -f database/schema.sql
-- ===========================================================================

-- Phase 1 tables only. Phase 2 stores embeddings locally with NumPy, so no
-- database extension is required.

-- Keeps updated_at accurate for both tables.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Jobs
-- owner_user_id stores the Supabase Auth user UUID. It is deliberately NOT a
-- foreign key because the application database is separate from Supabase.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id       UUID NOT NULL,
    title               TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    company             TEXT,
    description         TEXT NOT NULL CHECK (length(btrim(description)) > 0),
    required_skills     TEXT[] NOT NULL DEFAULT '{}',
    experience_required NUMERIC(4, 1) CHECK (
                            experience_required IS NULL
                            OR experience_required >= 0
                        ),
    location            TEXT,
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'closed')),
    experience_level    TEXT,
    job_type            TEXT,
    internship_duration_months INTEGER,
    compensation_type   TEXT,
    salary_stipend      TEXT,
    work_mode           TEXT,
    required_documents   TEXT[] NOT NULL DEFAULT '{}',
    application_deadline DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_owner_created
    ON jobs (owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_owner_status
    ON jobs (owner_user_id, status);

CREATE INDEX IF NOT EXISTS idx_jobs_required_skills
    ON jobs USING GIN (required_skills);

DROP TRIGGER IF EXISTS jobs_set_updated_at ON jobs;
CREATE TRIGGER jobs_set_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Candidates
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidates (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id    UUID NOT NULL,
    full_name        TEXT NOT NULL CHECK (length(btrim(full_name)) > 0),
    email            TEXT,
    phone            TEXT,
    skills           TEXT[] NOT NULL DEFAULT '{}',
    experience_years NUMERIC(4, 1) CHECK (
                         experience_years IS NULL
                         OR experience_years >= 0
                     ),
    education        TEXT,
    location         TEXT,
    resume_text      TEXT,
    -- Structured profile extracted from the linked resume (nullable JSONB;
    -- NULL = not extracted yet). See migrations/003_candidate_extracted_profile.sql.
    extracted_profile JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_candidates_owner_created
    ON candidates (owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_candidates_owner_email
    ON candidates (owner_user_id, email);

CREATE INDEX IF NOT EXISTS idx_candidates_skills
    ON candidates USING GIN (skills);

DROP TRIGGER IF EXISTS candidates_set_updated_at ON candidates;
CREATE TRIGGER candidates_set_updated_at
    BEFORE UPDATE ON candidates
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- Phase 2 note:
-- Embeddings are stored locally as NumPy arrays with JSON metadata under
-- backend/data/rag/. No vector column or vector index is added to this schema.

-- ---------------------------------------------------------------------------
-- Mock Interview sessions (Part 1; see migrations/004_interview_sessions.sql)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interview_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    document_id         UUID,
    resume_filename     TEXT,
    candidate_role      TEXT,
    status              TEXT NOT NULL DEFAULT 'awaiting_resume'
                        CHECK (status IN ('awaiting_resume', 'ready', 'in_progress', 'completed')),
    interview_type      TEXT NOT NULL DEFAULT 'Technical + HR',
    difficulty          TEXT NOT NULL DEFAULT 'Adaptive',
    mode                TEXT NOT NULL DEFAULT 'Text-based',
    current_question_number INTEGER NOT NULL DEFAULT 0,
    total_questions     INTEGER NOT NULL DEFAULT 10,
    final_score         NUMERIC(5, 2),
    evaluation_report   JSONB,
    extracted_info      JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_interview_sessions_user_created
    ON interview_sessions (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_interview_sessions_user_status
    ON interview_sessions (user_id, status);

DROP TRIGGER IF EXISTS interview_sessions_set_updated_at ON interview_sessions;
CREATE TRIGGER interview_sessions_set_updated_at
    BEFORE UPDATE ON interview_sessions
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS interview_questions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    user_id          UUID NOT NULL,
    question_number  INTEGER NOT NULL CHECK (question_number > 0),
    question_text    TEXT NOT NULL,
    question_type    TEXT,
    difficulty       TEXT NOT NULL DEFAULT 'Easy',
    answer_text      TEXT,
    evaluation       JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at      TIMESTAMPTZ,
    UNIQUE (session_id, question_number)
);

CREATE INDEX IF NOT EXISTS idx_interview_questions_session
    ON interview_questions (session_id, question_number);

CREATE INDEX IF NOT EXISTS idx_interview_questions_user
    ON interview_questions (user_id);

-- ---------------------------------------------------------------------------
-- Scheduled interviews (calendar appointments; see migrations/006_*.sql)
-- ---------------------------------------------------------------------------
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
    duration_minutes INTEGER NOT NULL DEFAULT 30 CHECK (duration_minutes IN (10, 30)),
    interview_type   TEXT NOT NULL DEFAULT 'online'
                     CHECK (interview_type IN ('online', 'in_person')),
    meeting_link     TEXT,
    location         TEXT,
    notes            TEXT,
    status           TEXT NOT NULL DEFAULT 'scheduled'
                     CHECK (status IN ('scheduled', 'completed', 'cancelled', 'missed')),
    time_zone        TEXT NOT NULL DEFAULT 'UTC',
    recruiter_email  TEXT,
    confirmation_email_status TEXT NOT NULL DEFAULT 'none'
                     CHECK (confirmation_email_status IN ('none', 'pending', 'sending', 'sent', 'failed')),
    confirmation_email_recipient TEXT,
    confirmation_email_sent_at TIMESTAMPTZ,
    confirmation_email_attempts INTEGER NOT NULL DEFAULT 0,
    confirmation_email_last_error TEXT,
    confirmation_email_next_attempt_at TIMESTAMPTZ,
    confirmation_email_claimed_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at),
    CHECK (
        (interview_type = 'online' AND meeting_link IS NOT NULL AND length(btrim(meeting_link)) > 0)
        OR (interview_type = 'in_person' AND location IS NOT NULL AND length(btrim(location)) > 0)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_interviews_candidate_start
    ON scheduled_interviews (candidate_id, starts_at) WHERE status <> 'cancelled';

CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_interviews_user_start
    ON scheduled_interviews (user_id, starts_at) WHERE status <> 'cancelled';

CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_user_starts
    ON scheduled_interviews (user_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_candidate_starts
    ON scheduled_interviews (candidate_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_confirmation_due
    ON scheduled_interviews (confirmation_email_status, confirmation_email_next_attempt_at)
    WHERE confirmation_email_status IN ('pending', 'failed', 'sending');

DROP TRIGGER IF EXISTS scheduled_interviews_set_updated_at ON scheduled_interviews;
CREATE TRIGGER scheduled_interviews_set_updated_at
    BEFORE UPDATE ON scheduled_interviews
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Interview reminders / in-app notifications (see migrations/007_*.sql)
-- ---------------------------------------------------------------------------
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
    read_at           TIMESTAMPTZ,

    -- Gmail delivery state (in-app notification status is unchanged)
    recipient_email      TEXT,
    email_status         TEXT NOT NULL DEFAULT 'none'
                         CHECK (email_status IN ('none', 'pending', 'sending', 'sent', 'failed')),
    email_sent_at        TIMESTAMPTZ,
    email_last_error     TEXT,
    email_attempts       INTEGER NOT NULL DEFAULT 0,
    email_claimed_at     TIMESTAMPTZ,
    email_next_attempt_at TIMESTAMPTZ
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

CREATE INDEX IF NOT EXISTS idx_interview_reminders_email_due
    ON interview_reminders (email_status, email_next_attempt_at)
    WHERE email_status IN ('pending', 'failed', 'sending');
