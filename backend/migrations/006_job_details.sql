-- Phase 6: Extended job details for candidate Browse Jobs.
-- All columns are nullable / have defaults so existing jobs keep working.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS experience_level TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_type TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS internship_duration_months INTEGER;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS compensation_type TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_stipend TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS work_mode TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS required_documents TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_deadline DATE;