-- AI Recruitment Agent - Mock Interview sessions (Part 1)
-- Non-destructive: creates new tables and indexes only.

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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

-- Structure reserved for Part 2 (question generation, answers, evaluation).
CREATE TABLE IF NOT EXISTS interview_questions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    user_id          UUID NOT NULL,
    question_number  INTEGER NOT NULL CHECK (question_number > 0),
    question_text    TEXT NOT NULL,
    question_type    TEXT,
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
