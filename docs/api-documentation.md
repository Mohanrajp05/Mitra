# AI Recruitment Agent — API Documentation

Base URL in development: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

All request and response bodies use JSON. Protected endpoints require:

```http
Authorization: Bearer <supabase_access_token>
```

The backend verifies the token with Supabase Auth and derives the user ID from
the verified response. Sending an `owner_user_id` in a request body returns
`422` because request schemas reject unknown fields.

## Status codes

| Code | Meaning |
| --- | --- |
| 200 | Successful read or update |
| 201 | Record created |
| 204 | Record deleted (no response body) |
| 401 | Missing, invalid, or expired bearer token |
| 404 | Record missing or not owned by the authenticated user |
| 422 | Request validation failed |
| 500 | Safe generic database/server error |
| 503 | Authentication or database configuration unavailable |

Error shape:

```json
{ "detail": "Job not found." }
```

Validation error shape:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "title"],
      "msg": "String should have at least 1 character",
      "input": ""
    }
  ]
}
```

---

## Health

### `GET /api/health`

No authentication. Does not query the database.

Response `200`:

```json
{
  "status": "ok",
  "service": "AI Recruitment Agent API",
  "version": "1.0.0",
  "database_configured": true,
  "auth_configured": true
}
```

The two boolean fields report whether environment variables are present. They
never expose their values.

### `GET /api/health/db`

No authentication. Runs a real query against the application database. It
returns `200` only when the pool is open and the query succeeds.

Response `200`:

```json
{
  "status": "ok",
  "database": "connected",
  "database_name": "recuirement_agent",
  "database_user": "postgres",
  "server_version": "PostgreSQL 18.6 on x86_64-windows"
}
```

Response `503` when the pool is unavailable, the query fails, or
`DATABASE_URL` is not configured:

```json
{
  "status": "error",
  "database": "unavailable",
  "detail": "Could not connect to the application database."
}
```

The error detail is generic; the real exception is logged only on the server.

---

## Authentication

### `GET /api/auth/me`

Requires a bearer token.

Response `200`:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "email": "student@example.com",
  "user_metadata": {
    "full_name": "Demo Student"
  }
}
```

Errors:

- `401` — missing or invalid token.
- `503` — Supabase Auth is not configured or temporarily unreachable.

---

## Jobs

### `GET /api/jobs`

Returns only jobs owned by the authenticated user, newest first.

Response `200`:

```json
[
  {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "owner_user_id": "11111111-1111-4111-8111-111111111111",
    "title": "Junior Python Developer",
    "company": "Fictional Demo Company",
    "description": "Build small internal tools with Python and FastAPI.",
    "required_skills": ["Python", "FastAPI"],
    "experience_required": 1.0,
    "location": "Remote",
    "status": "open",
    "created_at": "2026-01-10T10:00:00+00:00",
    "updated_at": "2026-01-10T10:00:00+00:00"
  }
]
```

### `POST /api/jobs`

Request:

```json
{
  "title": "Junior Python Developer",
  "company": "Fictional Demo Company",
  "description": "Build small internal tools with Python and FastAPI.",
  "required_skills": ["Python", "FastAPI"],
  "experience_required": 1,
  "location": "Remote",
  "status": "open"
}
```

Rules:

- `title` and `description` are required.
- `status` must be `open` or `closed`.
- `experience_required` must be between 0 and 60 if provided.
- Skills are trimmed and de-duplicated.
- `owner_user_id` is assigned from the verified token.

Response `201`: the created job, including `id`, `owner_user_id`,
`created_at`, and `updated_at`.

### `GET /api/jobs/{job_id}`

Response `200`: one job.

Errors: `404` when the job does not exist **or belongs to another user**.

### `PUT /api/jobs/{job_id}`

Partial update: send only the fields to change.

```json
{
  "status": "closed",
  "location": "Hybrid"
}
```

Response `200`: the updated job.

Errors: `404` when inaccessible; `422` for invalid values. Non-nullable fields
(`title`, `description`, `status`, `required_skills`) cannot be set to `null`.

### `DELETE /api/jobs/{job_id}`

Response `204` with no body.

Errors: `404` when inaccessible.

---

## Candidates

### `GET /api/candidates`

Returns only candidates owned by the authenticated user, newest first.

Response `200`:

```json
[
  {
    "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "owner_user_id": "11111111-1111-4111-8111-111111111111",
    "full_name": "Asha Demo",
    "email": "asha.demo@example.com",
    "phone": "+91 90000 00000",
    "skills": ["Python", "SQL"],
    "experience_years": 2.0,
    "education": "B.Sc. Computer Science",
    "resume_text": "Fictional resume used for demonstration only.",
    "created_at": "2026-01-11T09:30:00+00:00",
    "updated_at": "2026-01-11T09:30:00+00:00"
  }
]
```

### `POST /api/candidates`

Request:

```json
{
  "full_name": "Ravi Demo",
  "email": "ravi.demo@example.com",
  "phone": "+91 90000 00002",
  "skills": ["React", "JavaScript"],
  "experience_years": 1,
  "education": "B.Tech Information Technology",
  "resume_text": "Fictional candidate profile."
}
```

Rules:

- `full_name` is required.
- `email` is optional but must be valid when provided.
- `experience_years` must be between 0 and 60 if provided.
- Skills are trimmed and de-duplicated.
- `owner_user_id` is assigned from the verified token.

Response `201`: the created candidate.

### `GET /api/candidates/{candidate_id}`

Response `200`: one candidate.

Errors: `404` when the candidate does not exist **or belongs to another user**.

### `PUT /api/candidates/{candidate_id}`

Partial update: send only the fields to change.

```json
{
  "education": "M.Sc. Computer Science"
}
```

Response `200`: the updated candidate.

Errors: `404` when inaccessible; `422` for invalid values. `full_name` and
`skills` cannot be set to `null`.

### `DELETE /api/candidates/{candidate_id}`

Response `204` with no body.

Errors: `404` when inaccessible.

---

## Quick manual checks

Health:

```powershell
curl.exe http://localhost:8000/api/health
```

Protected request (replace the token):

```powershell
curl.exe http://localhost:8000/api/auth/me `
  -H "Authorization: Bearer YOUR_SUPABASE_ACCESS_TOKEN"
```

The easiest way to obtain a token for manual testing is to log in through the
frontend, open the browser developer tools, and inspect the Supabase session in
`localStorage`. Never paste a service-role key anywhere in the frontend.
