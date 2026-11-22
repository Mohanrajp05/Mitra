# AI Recruitment Agent — Project Overview

## 1. Purpose

AI Recruitment Agent is a college-level full-stack project. Phase 1 builds a
secure, runnable foundation for managing job posts and candidate profiles.
It deliberately contains **no AI features yet**: no embeddings, no RAG, no
LLM calls, and no vector search. Those belong to Phase 2.

## 2. Phase 1 scope

Implemented:

- Email/password registration and login with Supabase Auth.
- Logout and session restoration in the React frontend.
- Protected frontend routes.
- Job create, list, view, update, and delete.
- Candidate create, list, view, update, and delete.
- FastAPI REST API with Pydantic validation.
- Separate PostgreSQL application database without any vector extension.
- Per-user record ownership enforced in SQL.
- Loading, empty, validation, and error states in the UI.

Not implemented:

- Resume file upload or parsing.
- Embeddings, vector similarity search, RAG, or AI matching.
- Email notifications, background jobs, Redis, or microservices.
- Supabase database tables, Supabase Storage, or Supabase Row Level Security
  for application data.

## 3. Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ Browser: React + JavaScript + Vite                           │
│                                                              │
│  Supabase JS client ──────────────► Supabase Auth            │
│    signup / login / logout / session                         │
│                                                              │
│  fetch() + Authorization: Bearer <access_token>              │
└──────────────────────────┬───────────────────────────────────┘
                           │ JSON over REST
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ FastAPI backend (Python)                                     │
│                                                              │
│  1. Verify bearer token with Supabase Auth                   │
│  2. Derive user ID from the verified Supabase response       │
│  3. Validate input with Pydantic                             │
│  4. Run parameterized SQL with psycopg                       │
└──────────────────────────┬───────────────────────────────────┘
                           │ psycopg (backend only)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Separate PostgreSQL database                                 │
│  - jobs                                                      │
│  - candidates                                                │
│  - no vector extension (Phase 2 stores embeddings locally)   │
└──────────────────────────────────────────────────────────────┘
```

Supabase Auth and the application PostgreSQL database are independent.
There is no foreign key from `jobs.owner_user_id` or
`candidates.owner_user_id` to `auth.users`. The user UUID is stored as a plain
UUID and is always taken from a verified access token.

## 4. Authentication flow

1. The user registers or logs in through the Supabase JavaScript client.
2. Supabase returns a session containing an access token (JWT).
3. `src/services/api.js` reads the current session and sends:
   `Authorization: Bearer <access_token>`.
4. FastAPI calls `GET {SUPABASE_URL}/auth/v1/user` with the bearer token and the
   publishable key.
5. FastAPI accepts the user ID from Supabase's response only. A user ID sent in
   a request body is rejected because request schemas forbid extra fields.
6. The verified user ID is passed to every jobs/candidates query.

The frontend never receives `DATABASE_URL` or a Supabase service-role key.

## 5. Ownership model

Every jobs and candidates query contains an ownership condition:

```sql
WHERE owner_user_id = %s
```

Create operations take `owner_user_id` from the verified token, not from the
request body. Update and delete operations include both the record ID and the
owner ID. A record owned by another user returns **404 Not Found**, which avoids
revealing whether the record exists.

## 6. Data model

### jobs

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID | Primary key |
| owner_user_id | UUID | Supabase Auth user ID |
| title | TEXT | Required |
| company | TEXT | Optional |
| description | TEXT | Required |
| required_skills | TEXT[] | Defaults to empty array |
| experience_required | NUMERIC(4,1) | Optional, non-negative |
| location | TEXT | Optional |
| status | TEXT | `open` or `closed` |
| created_at | TIMESTAMPTZ | Defaults to now |
| updated_at | TIMESTAMPTZ | Updated by trigger |

### candidates

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID | Primary key |
| owner_user_id | UUID | Supabase Auth user ID |
| full_name | TEXT | Required |
| email | TEXT | Optional, validated when provided |
| phone | TEXT | Optional |
| skills | TEXT[] | Defaults to empty array |
| experience_years | NUMERIC(4,1) | Optional, non-negative |
| education | TEXT | Optional |
| resume_text | TEXT | Optional plain text |
| created_at | TIMESTAMPTZ | Defaults to now |
| updated_at | TIMESTAMPTZ | Updated by trigger |

Indexes cover owner/date access, owner/status, owner/email, and GIN indexes on
skill arrays.

## 7. Configuration

Backend (`backend/.env`):

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Separate PostgreSQL connection string |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Public publishable (or legacy anon) key |
| `FRONTEND_ORIGIN` | Allowed CORS origin, default `http://localhost:5173` |

Frontend (`frontend/.env`):

| Variable | Purpose |
| --- | --- |
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Public publishable (or legacy anon) key |
| `VITE_API_BASE_URL` | FastAPI base URL, default `http://localhost:8000` |

## 8. Security decisions

- Environment variables hold all credentials; `.env` files are gitignored.
- Pydantic validates request bodies and rejects unknown fields.
- SQL is parameterized; column names in dynamic updates come from a whitelist.
- CORS allows only the configured frontend origin.
- Database errors are logged server-side and returned as generic messages.
- Supabase handles authentication only; it stores no application tables.
- The frontend cannot connect to PostgreSQL directly.

## 9. Phase 2 placeholder

Phase 2 stores embeddings locally as NumPy arrays with JSON metadata under
`backend/data/rag/`. `database/schema.sql` creates only the `jobs` and
`candidates` tables, and no PostgreSQL extension or vector column is required.
