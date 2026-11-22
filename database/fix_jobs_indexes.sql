-- Safe repair script for missing indexes on the existing jobs table.
--
-- This script only adds indexes with CREATE INDEX IF NOT EXISTS.
-- It never drops, recreates, or alters a table, and it does not touch data.
--
-- Run it from the project root:
--   psql -U postgres -d recuirement_agent -f .\database\fix_jobs_indexes.sql
-- or, if psql is not on PATH:
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d recuirement_agent -f .\database\fix_jobs_indexes.sql

CREATE INDEX IF NOT EXISTS idx_jobs_owner_created
    ON jobs (owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_owner_status
    ON jobs (owner_user_id, status);

CREATE INDEX IF NOT EXISTS idx_jobs_required_skills
    ON jobs USING GIN (required_skills);
