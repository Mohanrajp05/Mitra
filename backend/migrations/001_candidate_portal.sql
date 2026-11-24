-- Phase 1: Candidate Portal
-- Minimum schema change: map an authenticated Supabase user to a candidate profile
-- and record their application role. Existing recruiter-owned candidates are
-- untouched (owner_user_id keeps pointing at the recruiter).

CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('recruiter', 'candidate')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A candidate self-account owns its own candidate record (owner_user_id = user_id).
-- No new candidate table is introduced; we reuse the existing `candidates` table.
-- The mapping is implicit: a candidate account is the owner of (at least) one
-- candidate row whose owner_user_id equals the authenticated user id.

CREATE INDEX IF NOT EXISTS idx_candidates_owner_user_id ON candidates (owner_user_id);
