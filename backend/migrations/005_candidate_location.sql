-- Phase 5: Candidate profile location.
-- The candidate profile form has always collected a location, but the column
-- did not exist on `candidates`, so the value was silently dropped. Add it
-- now so location persists like every other profile field.
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location TEXT;
