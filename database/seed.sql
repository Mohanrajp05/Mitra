-- ===========================================================================
-- FICTIONAL DEMONSTRATION DATA ONLY
-- No real people, companies, emails, or phone numbers are represented here.
--
-- The rows belong to the placeholder owner UUID below. Because every API query
-- is filtered by the authenticated Supabase user, you will not see these rows
-- in the UI until you assign them to your own Supabase user ID:
--
--   UPDATE jobs
--   SET owner_user_id = '<your-supabase-user-uuid>'
--   WHERE owner_user_id = '00000000-0000-4000-8000-000000000001';
--
--   UPDATE candidates
--   SET owner_user_id = '<your-supabase-user-uuid>'
--   WHERE owner_user_id = '00000000-0000-4000-8000-000000000001';
--
-- Get your user UUID from the Supabase dashboard (Authentication > Users) or
-- from GET /api/auth/me after logging in.
-- ===========================================================================

INSERT INTO jobs (
    id, owner_user_id, title, company, description,
    required_skills, experience_required, location, status
) VALUES
(
    '11111111-1111-4111-8111-111111111111',
    '00000000-0000-4000-8000-000000000001',
    'Junior Python Developer',
    'Fictional Demo Company',
    'Maintain small internal tools and REST APIs using Python and FastAPI. '
    || 'This is fictional sample data for a college demonstration.',
    ARRAY['Python', 'FastAPI', 'PostgreSQL'],
    1.0,
    'Remote',
    'open'
),
(
    '22222222-2222-4222-8222-222222222222',
    '00000000-0000-4000-8000-000000000001',
    'Frontend Developer (React)',
    'Example College Lab',
    'Build accessible React interfaces for a student project dashboard. '
    || 'This is fictional sample data.',
    ARRAY['React', 'JavaScript', 'CSS'],
    0.5,
    'On campus',
    'open'
),
(
    '33333333-3333-4333-8333-333333333333',
    '00000000-0000-4000-8000-000000000001',
    'Data Analyst Intern',
    'Sample Analytics Studio',
    'Assist with SQL reporting and simple data visualisation. '
    || 'This is fictional sample data.',
    ARRAY['SQL', 'Excel', 'Python'],
    NULL,
    'Hybrid',
    'closed'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO candidates (
    id, owner_user_id, full_name, email, phone,
    skills, experience_years, education, resume_text
) VALUES
(
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '00000000-0000-4000-8000-000000000001',
    'Asha Demo',
    'asha.demo@example.com',
    '+91 90000 00001',
    ARRAY['Python', 'SQL', 'FastAPI'],
    2.0,
    'B.Sc. Computer Science',
    'Fictional candidate resume. Built two student web applications using '
    || 'Python, FastAPI, and PostgreSQL. Interested in backend development.'
),
(
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    '00000000-0000-4000-8000-000000000001',
    'Ravi Demo',
    'ravi.demo@example.com',
    '+91 90000 00002',
    ARRAY['React', 'JavaScript', 'CSS'],
    1.0,
    'B.Tech Information Technology',
    'Fictional candidate resume. Created responsive React interfaces and '
    || 'completed a frontend internship at a pretend company.'
),
(
    'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    '00000000-0000-4000-8000-000000000001',
    'Meera Demo',
    'meera.demo@example.com',
    NULL,
    ARRAY['SQL', 'Excel', 'Python'],
    0.5,
    'B.Com. with Computer Applications',
    'Fictional candidate resume. Comfortable with SQL queries, spreadsheets, '
    || 'and basic Python scripts for reporting.'
)
ON CONFLICT (id) DO NOTHING;
