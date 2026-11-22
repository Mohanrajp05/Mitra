-- Stage 8: candidate consent records for resume/personal-data processing.
-- Non-destructive: creates a new table and indexes only. The existing jobs,
-- candidates, and chat tables and their records are not modified.

CREATE TABLE IF NOT EXISTS candidate_consents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id  UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    owner_user_id UUID NOT NULL,
    consent_type  TEXT NOT NULL DEFAULT 'resume_processing'
                  CHECK (consent_type IN ('resume_processing')),
    status        TEXT NOT NULL
                  CHECK (status IN ('granted', 'withdrawn')),
    decided_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_consents_candidate_type
    ON candidate_consents (candidate_id, consent_type);

CREATE INDEX IF NOT EXISTS idx_candidate_consents_owner
    ON candidate_consents (owner_user_id, decided_at DESC);

DROP TRIGGER IF EXISTS candidate_consents_set_updated_at ON candidate_consents;
CREATE TRIGGER candidate_consents_set_updated_at
    BEFORE UPDATE ON candidate_consents
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
