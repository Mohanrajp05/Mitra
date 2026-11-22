-- Structured candidate profile extracted from the linked resume.
-- Non-destructive: adds one nullable JSONB column. Existing records are not
-- modified; NULL means the profile has not been extracted yet.

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS extracted_profile JSONB;
