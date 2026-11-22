-- Interview question difficulty progression (Easy -> Medium -> Hard).
-- Non-destructive: adds one defaulted column; existing questions default to Easy.

ALTER TABLE interview_questions
    ADD COLUMN IF NOT EXISTS difficulty TEXT NOT NULL DEFAULT 'Easy';
