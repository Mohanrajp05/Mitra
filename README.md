# AI Recruitment Agent

A college-level full-stack project that manages job posts and candidate
profiles. **Phase 1** is the secure application foundation: React frontend,
FastAPI REST API, a separate PostgreSQL database, and Supabase Auth for user
authentication.

**Phase 2 (in progress)** adds a local RAG foundation: PDF/DOCX/text loading,
text splitting, local Sentence Transformers embeddings (`all-MiniLM-L6-v2`,
384 dimensions), NumPy embedding storage, and cosine-similarity retrieval.
No pgvector, Docker, MSVC build tools, or extra database server is required.

---

## 1. Overview and architecture

```text
React + Vite (JavaScript)
  │
  ├── Supabase JS client ──► Supabase Auth (signup, login, logout, session)
  │
  └── fetch JSON + Bearer token ──► FastAPI
                                      │
                                      ├── verifies token with Supabase Auth
                                      ├── validates input with Pydantic
                                      └── psycopg parameterized SQL
                                                │
                                                ▼
                                      PostgreSQL
                                      (separate application database)
```

Key rules:

- Supabase is used **only for authentication**.
- The application database is a **separate PostgreSQL database**.
- Only FastAPI connects to PostgreSQL. The browser never receives database
  credentials.
- Every jobs/candidates query is filtered by the user ID from the verified
  Supabase token.
- No TypeScript, Node/Express backend, Supabase tables, Supabase Storage,
  LangChain, LangGraph, Redis, or RAG in Phase 1.

Detailed notes:

- [`docs/project-overview.md`](docs/project-overview.md)
- [`docs/api-documentation.md`](docs/api-documentation.md)

---

## 2. Folder structure

```text
AI-Recruitment-Agent/
├── frontend/
│   ├── public/
│   │   └── favicon.svg
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   │   ├── Navbar.jsx
│   │   │   ├── Sidebar.jsx
│   │   │   ├── JobCard.jsx
│   │   │   ├── CandidateCard.jsx
│   │   │   └── Loading.jsx
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Register.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Jobs.jsx
│   │   │   ├── CreateJob.jsx
│   │   │   ├── JobDetails.jsx
│   │   │   ├── Candidates.jsx
│   │   │   ├── CreateCandidate.jsx
│   │   │   └── CandidateDetails.jsx
│   │   ├── services/
│   │   │   ├── api.js
│   │   │   ├── auth.js
│   │   │   ├── jobs.js
│   │   │   └── candidates.js
│   │   ├── styles/
│   │   │   ├── global.css
│   │   │   ├── auth.css
│   │   │   ├── dashboard.css
│   │   │   └── forms.css
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── jobs.py
│   │   │   ├── candidates.py
│   │   │   └── health.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── database/
│   │   │   ├── connection.py
│   │   │   └── queries.py
│   │   ├── schemas/
│   │   │   ├── job.py
│   │   │   └── candidate.py
│   │   ├── services/
│   │   │   ├── job_service.py
│   │   │   └── candidate_service.py
│   │   ├── utils/
│   │   │   └── validators.py
│   │   └── main.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_database.py
│   │   ├── test_health_db.py
│   │   ├── test_jobs.py
│   │   └── test_candidates.py
│   ├── .env.example
│   ├── pytest.ini
│   └── requirements.txt
├── database/
│   ├── schema.sql
│   ├── seed.sql
│   ├── fix_jobs_indexes.sql
│   └── migrations/
│       └── README.md
├── docs/
│   ├── project-overview.md
│   └── api-documentation.md
├── .gitignore
└── README.md
```

`CreateCandidate.jsx` is included because candidate creation needs its own
form page; it follows the same pattern as `CreateJob.jsx`.

---

## 3. Required software

Install these on Windows:

| Software | Version | Notes |
| --- | --- | --- |
| Node.js | 20 LTS or newer | Includes npm |
| Python | 3.11 or newer | 3.11 or 3.12 recommended |
| PostgreSQL | 18 recommended | 14 or newer also works |
| Git | Any recent | Optional but useful |
| Supabase account | Free tier is fine | Authentication only |
| Docker Desktop | Optional | Not required for Phase 2 |

Check versions in PowerShell:

```powershell
node --version
npm --version
python --version
```

> If `python` opens the Microsoft Store, install Python from python.org and
> enable **Add python.exe to PATH** during installation.

---

## 4. Create the separate PostgreSQL database

Choose **one** option. Both create a database named `recuirement_agent`.

### Option A — Docker (optional)

Install Docker Desktop, open PowerShell, and run:

```powershell
docker run --name ai-recruitment-db `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=recuirement_agent `
  -p 5432:5432 `
  -d postgres:18
```

Wait a few seconds, then check:

```powershell
docker ps
```

This image already contains the `vector` extension. If port `5432` is already
used, change the host side to `5433` and use port `5433` in `DATABASE_URL`.

Useful Docker commands:

```powershell
# Start again after a reboot
docker start ai-recruitment-db

# Open psql inside the container
docker exec -it ai-recruitment-db psql -U postgres -d recuirement_agent

# Stop the container
docker stop ai-recruitment-db
```

### Option B — Native Windows PostgreSQL

1. Download and install PostgreSQL 16 from the official installer
   (EnterpriseDB). Remember the password for the `postgres` user.
2. Add the PostgreSQL `bin` folder to PATH, for example:
   `C:\Program Files\PostgreSQL\16\bin`.
3. Open a **new** PowerShell window and check:

```powershell
psql --version
```

4. Create the database:

```powershell
psql -U postgres -c "CREATE DATABASE recuirement_agent;"
```

You will be asked for the `postgres` password.

If `psql` is still not found, use the full path:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE recuirement_agent;"
```

> No PostgreSQL extension is required. `schema.sql` only creates the `jobs` and
> `candidates` tables.

---

## 5. Vector storage (no database extension)

Phase 2 does not use pgvector. Embeddings are stored locally:

```text
backend/data/rag/
├── embeddings/   NumPy arrays, one file per document
├── metadata/     JSON metadata, one file per document
└── documents/    Original uploaded files
```

This folder is created automatically on first use and is ignored by Git. Nothing
has to be compiled or installed in PostgreSQL.

Python packages for Phase 2:

```powershell
cd .\backend
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The default model is `all-MiniLM-L6-v2` (384 dimensions). It is downloaded once
and then reused from the local Hugging Face cache. To force a download, set
`RAG_ALLOW_MODEL_DOWNLOAD=1`; otherwise the service runs in offline mode.

---

## 6. Run the schema and seed data

Open PowerShell in the project root (the folder containing this README). Confirm
you are in the right place:

```powershell
Get-ChildItem .\database\schema.sql
```

### With native `psql`

```powershell
psql -U postgres -d recuirement_agent -f .\database\schema.sql
psql -U postgres -d recuirement_agent -f .\database\seed.sql
```

### With Docker

Copy the SQL files into the container and run them:

```powershell
docker cp .\database\schema.sql ai-recruitment-db:/tmp/schema.sql
docker cp .\database\seed.sql ai-recruitment-db:/tmp/seed.sql
docker exec -it ai-recruitment-db psql -U postgres -d recuirement_agent -f /tmp/schema.sql
docker exec -it ai-recruitment-db psql -U postgres -d recuirement_agent -f /tmp/seed.sql
```

Verify:

```powershell
docker exec -it ai-recruitment-db psql -U postgres -d recuirement_agent -c "\dt"
```

You should see the `jobs` and `candidates` tables.

### Repair missing `jobs` indexes (safe)

The API works without them, but these indexes keep owner-filtered queries fast.
If `\d jobs` does not show `idx_jobs_owner_created`, `idx_jobs_owner_status`,
and `idx_jobs_required_skills`, run the repair script. It only uses
`CREATE INDEX IF NOT EXISTS` and never drops or alters a table:

```powershell
psql -U postgres -d recuirement_agent -f .\database\fix_jobs_indexes.sql
```

With Docker, copy the file into the container first:

```powershell
docker cp .\database\fix_jobs_indexes.sql ai-recruitment-db:/tmp/fix_jobs_indexes.sql
docker exec -it ai-recruitment-db psql -U postgres -d recuirement_agent -f /tmp/fix_jobs_indexes.sql
```

### About the seed data

The sample jobs and candidates are **fictional demonstration data**. They belong
to the placeholder owner:

```text
00000000-0000-4000-8000-000000000001
```

Because the API filters records by the logged-in user, seeded rows are not
visible in the UI until you assign them to your own Supabase user ID. Get your
ID from the Supabase dashboard (**Authentication → Users**) or from
`GET /api/auth/me`, then run:

```powershell
psql -U postgres -d recuirement_agent -c "UPDATE jobs SET owner_user_id = 'YOUR-USER-UUID' WHERE owner_user_id = '00000000-0000-4000-8000-000000000001';"
psql -U postgres -d recuirement_agent -c "UPDATE candidates SET owner_user_id = 'YOUR-USER-UUID' WHERE owner_user_id = '00000000-0000-4000-8000-000000000001';"
```

With Docker, put the same SQL inside:

```powershell
docker exec -it ai-recruitment-db psql -U postgres -d recuirement_agent -c "UPDATE jobs SET owner_user_id = 'YOUR-USER-UUID' WHERE owner_user_id = '00000000-0000-4000-8000-000000000001';"
```

### Verify that the database is working

The commands below use `recuirement_agent`, the database name currently
configured in this workspace. If you created `recuirement_agent`, use that name
instead.

First check the service and port:

```powershell
Get-Service *postgres*
Get-NetTCPConnection -LocalPort 5432 -State Listen
```

If `psql` is not on PATH, use the full path (adjust the version if needed):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d recuirement_agent -c "SELECT current_database(), current_user;"
```

Check tables and row counts:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d recuirement_agent -c "\dt"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d recuirement_agent -c "SELECT COUNT(*) FROM jobs;"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d recuirement_agent -c "SELECT COUNT(*) FROM candidates;"
```

Check the connection using the backend's own configuration (from the project
root):

```powershell
cd .\backend
.\.venv\Scripts\Activate.ps1
@'
from app.database.connection import open_pool, get_connection, close_pool

open_pool()
try:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            print(cur.fetchone())
finally:
    close_pool()
'@ | python -
```

> `GET /api/health` only reports whether `DATABASE_URL` is present
> (`database_configured`). It does **not** prove that PostgreSQL is reachable.
> `GET /api/health/db` runs a real query and is the authoritative check.

---

## 7. Configure Supabase Auth

1. Create a project at <https://supabase.com>.
2. Open **Authentication → Providers** and make sure **Email** is enabled.
3. For a quick classroom demo, you can disable **Confirm email** under the
   Email provider settings. If you leave it enabled, users must click the
   confirmation link before logging in.
4. Open **Authentication → URL Configuration**:
   - **Site URL:** `http://localhost:5173`
   - **Redirect URLs:** add `http://localhost:5173/**` and
     `http://localhost:5173/login`.
5. Open **Project Settings → API** and copy:
   - **Project URL**
   - **Publishable key** (`sb_publishable_...`) or, on older projects, the
     **anon public** key.

Use only the publishable/anon public key. **Never** copy the `service_role`
secret key into the frontend or into this project.

Supabase is not used for application tables or file storage in this project.

---

## 8. Create the environment files

From the project root:

```powershell
Copy-Item .\backend\.env.example .\backend\.env
Copy-Item .\frontend\.env.example .\frontend\.env.local
notepad .\backend\.env
notepad .\frontend\.env.local
```

### `backend/.env`

```env
DATABASE_URL=postgresql://postgres:CHANGE_ME@localhost:5432/recuirement_agent
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key_here
FRONTEND_ORIGIN=http://localhost:5173
```

- Replace the database password if yours is different.
- If your password contains special characters such as `@`, `#`, or `:`,
  URL-encode them in `DATABASE_URL`.
- If you used Docker port `5433`, change `5432` to `5433`.
- `SUPABASE_URL` must not end with a slash (the backend removes one if present).

### `frontend/.env.local`

```env
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key_here
VITE_API_BASE_URL=http://localhost:8000
```

Restart Vite after changing any frontend environment variable.

`.env.local` is ignored by Git, so real local values are not committed. Only
`.env.example` is committed.

> **If `frontend/.env.local` already exists, do not overwrite it.** Keep the
> existing Supabase URL and publishable key, and make sure
> `VITE_API_BASE_URL` points to FastAPI (`http://localhost:8000` by default).
> Vite only loads `.env.local` (and mode-specific variants) — never a file
> named `frontend.env`. The legacy `frontend/frontend.env` duplicate was
> removed in the security cleanup.

> **If `backend/.env` already exists, do not overwrite it.** Add the missing
> `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `FRONTEND_ORIGIN`, and
> `DATABASE_URL` entries. For compatibility, the backend also accepts
> `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` as fallbacks, but the
> documented `SUPABASE_*` names take priority.

---

## 9. Install frontend dependencies

```powershell
cd .\frontend
npm install
```

Dependencies are limited to React, React Router, the Supabase JavaScript client,
Vite, and the React Vite plugin.

---

## 10. Create and activate the Python virtual environment (Windows PowerShell)

From the project root:

```powershell
cd .\backend
python -m venv .venv
```

If PowerShell blocks activation scripts:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Activate:

```powershell
.\.venv\Scripts\Activate.ps1
```

Your prompt should start with `(.venv)`.

To deactivate later:

```powershell
deactivate
```

---

## 11. Install backend requirements

With the virtual environment active:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Packages: FastAPI, Uvicorn, Pydantic, psycopg (binary), psycopg_pool,
python-dotenv, HTTPX, and Pytest.

---

## 12. Run the application

Use **two PowerShell terminals**.

### Terminal 1 — backend

From the project root, in the first terminal:

```powershell
cd .\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Check:

- API: <http://localhost:8000/api/health>
- Database health: <http://localhost:8000/api/health/db>
- Interactive docs: <http://localhost:8000/docs>

`database_configured` and `auth_configured` should both be `true` once your
`.env` is filled in. `/api/health/db` runs a real `SELECT` against PostgreSQL;
it returns `200` only when the query succeeds and `503` when the pool cannot
reach the database. Startup still succeeds if PostgreSQL is down, but database
endpoints will report `503` instead of pretending the connection works.

### Terminal 2 — frontend

```powershell
cd .\frontend
npm run dev
```

Open <http://localhost:5173>.

The app redirects to `/login` when there is no Supabase session. After login it
opens `/dashboard`. Protected routes are:

- `/dashboard`
- `/jobs`, `/jobs/new`, `/jobs/:id`, `/jobs/:id/edit`
- `/candidates`, `/candidates/new`, `/candidates/:id`,
  `/candidates/:id/edit`

### First run

1. Open `/register` and create an account.
2. If email confirmation is enabled, confirm your email first.
3. Log in. A successful login opens the dashboard.
4. Create a job, open its details, edit it, then delete it after confirming.
5. Add a candidate, open the candidate details, edit it, then delete it.
6. Refresh the browser to confirm the Supabase session is restored.
7. Log out and confirm you are returned to the login page.
8. Open the browser developer tools → Network. API requests go to
   `http://localhost:8000/api/...` and include `Authorization: Bearer ...`.
   There are no direct browser requests to PostgreSQL.

### Email and password rules

The registration form validates input before calling Supabase, and shows
inline messages plus a live checklist. The rules are intentionally close to the
guidance used by Google and other large sign-up forms.

**Email address**

- Required.
- Trimmed before validation and sign-up.
- At most 254 characters.
- Exactly one `@` symbol.
- A domain that contains a dot, such as `example.com`.
- No spaces.
- At most 64 characters before the `@`.
- No leading dot, trailing dot, or consecutive dots in the local part.

The candidate form uses the same email validator whenever an optional candidate
email is supplied.

**Password (registration)**

- Required, 8 to 64 characters.
- At least one uppercase letter.
- At least one lowercase letter.
- At least one number.
- At least one special character.
- No spaces.
- Must match the confirm-password field.
- A live checklist marks each rule as met, and a strength meter shows
  Very weak / Weak / Fair / Good / Strong.
- The eye button in both password fields toggles visibility.

**Password (login)**

- Login only checks that the email is well formed and the password is not
  empty. It deliberately does not apply the registration complexity rules, so
  existing accounts with older passwords can still sign in.

These are client-side usability checks. Supabase Auth remains the authority for
account creation and sign-in. If you change the password policy in the Supabase
dashboard, keep these rules aligned with it.

---

## 13. REST endpoints

| Method | Endpoint | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/health` | No | Health and configuration status |
| GET | `/api/health/db` | No | Real database query and connectivity status |
| GET | `/api/auth/me` | Yes | Verified Supabase user identity |
| GET | `/api/jobs` | Yes | List the user's jobs |
| POST | `/api/jobs` | Yes | Create a job |
| GET | `/api/jobs/{job_id}` | Yes | Get one owned job |
| PUT | `/api/jobs/{job_id}` | Yes | Update an owned job |
| DELETE | `/api/jobs/{job_id}` | Yes | Delete an owned job |
| GET | `/api/candidates` | Yes | List the user's candidates |
| POST | `/api/candidates` | Yes | Create a candidate |
| GET | `/api/candidates/{candidate_id}` | Yes | Get one owned candidate |
| PUT | `/api/candidates/{candidate_id}` | Yes | Update an owned candidate |
| DELETE | `/api/candidates/{candidate_id}` | Yes | Delete an owned candidate |

All protected requests need:

```http
Authorization: Bearer <supabase_access_token>
```

Requests for another user's record return `404`, not `403`, so record existence
is not disclosed. Full request/response examples are in
[`docs/api-documentation.md`](docs/api-documentation.md).

---

## 14. Run the tests

The backend tests use a fake authenticated user and mock the service layer, so
they do not need Supabase or PostgreSQL.

```powershell
cd .\backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

They check:

- Health endpoint and configuration flags.
- Database health endpoint: successful query, `503` when the pool is
  unavailable, `503` when the query fails, and `503` when the database is not
  configured.
- Pool lifespan: open on startup, close on shutdown, and the API still starts
  when the pool cannot be initialized.
- Missing, invalid, and valid bearer tokens.
- Ownership propagation from the verified user to services.
- Rejection of client-supplied `owner_user_id`.
- Pydantic validation errors.
- 404 and 204 behavior for missing records.

The suite patches the lifespan so it never opens a real pool. Live database
checks were run separately (see section 16). Real Supabase login still has to be
checked manually with your own credentials.

### Frontend production build

```powershell
cd .\frontend
npm install
npm run build
```

The output is written to `frontend/dist/` (ignored by Git).

Frontend checks performed:

- `npm run build` completed with Vite 6.
- `npm run dev` served the app at `http://localhost:5173` with HTTP `200`.
- The built bundle uses `http://localhost:8000` as the API base URL.
- The shared validation module passed 24 direct checks: valid and invalid email
  formats, weak and strong passwords, and matching/mismatching confirmation
  fields.
- The production bundle contains the email error copy, the password checklist,
  the strength meter, and the password visibility toggle styles.
- No `.ts`, `.tsx`, or `tsconfig*.json` files exist in `frontend/src` or the
  frontend root.
- No PostgreSQL URL, database password, or service-role key is present in the
  frontend source.

Login, logout, session restoration, and live job/candidate CRUD through the UI
require a real Supabase user and a running FastAPI server. Those flows are
implemented but were not executed here because no test account password was
available.

---

## 15. Common setup errors and solutions

### `psql` is not recognized

Add `C:\Program Files\PostgreSQL\16\bin` to PATH, open a new PowerShell window,
or call `psql.exe` with its full path.

### The embedding model cannot be downloaded

- The service runs offline by default and reuses the local Hugging Face cache.
- If the model is not cached yet, set `RAG_ALLOW_MODEL_DOWNLOAD=1` for the first
  run, then unset it.
- If the download still fails, check your network or proxy settings.

### `relation "jobs" does not exist`

Run `database/schema.sql` against `recuirement_agent`, not against another
database and not against Supabase.

### Backend returns 503 "database is not configured"

- `backend/.env` is missing or `DATABASE_URL` is empty.
- You edited `.env` but did not restart Uvicorn.
- The PostgreSQL container/service is not running.

### `/api/health/db` returns 503

- PostgreSQL is not running, or the host/port in `DATABASE_URL` is wrong.
- The database name or password is wrong.
- The connection pool could not open during startup. Check the Uvicorn log for
  a `Database connection pool could not be initialized` warning.
- The pool is small (`min_size=1`, `max_size=5`); a long-running query can make
  other requests wait. Check the server log for the underlying error.

### Frontend shows "Supabase is not configured"

- `frontend/.env.local` is missing, or it does not contain both
  `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
- The file is named `frontend.env` instead of `.env.local`. Vite only loads
  `.env`, `.env.local`, and mode-specific variants. (This legacy file was
  removed in the security cleanup — use `.env.local` only.)
- You edited the file but did not restart `npm run dev`.
- Never put the Supabase service-role key in the frontend.

### Backend returns 401 for every request

- The user is not logged in, or the Supabase session expired. Log out and log in
  again.
- `SUPABASE_URL` or `SUPABASE_PUBLISHABLE_KEY` is wrong in `backend/.env`.
- The frontend is using a different Supabase project than the backend.
- Restart both servers after changing environment variables.

### Browser shows a CORS error

- `FRONTEND_ORIGIN` must exactly match the browser origin, for example
  `http://localhost:5173` (no trailing slash).
- If Vite runs on another port, update `FRONTEND_ORIGIN` and restart FastAPI.
- Do not use `*` for CORS with credentials.

### Registration succeeds but login says "Email not confirmed"

Supabase's default email confirmation is enabled. Confirm through the email, or
disable **Confirm email** in the Supabase Email provider settings for a demo.

### Seeded records are not visible

They belong to the placeholder owner UUID. Update `owner_user_id` to your
Supabase user ID (section 6).

### `ModuleNotFoundError: No module named 'fastapi'`

The virtual environment is not active. Run `.\.venv\Scripts\Activate.ps1` from
the `backend` folder, then reinstall requirements.

### `npm install` fails or Vite will not start

- Use Node.js 20 LTS or newer (`node --version`).
- Delete `node_modules` and `package-lock.json`, then run `npm install` again.
- Port `5173` is already in use. Stop the other process or change the port in
  `vite.config.js` and `FRONTEND_ORIGIN`.

### Port 8000 is already in use

Run Uvicorn on another port:

```powershell
uvicorn app.main:app --reload --port 8001
```

Then set `VITE_API_BASE_URL=http://localhost:8001` in `frontend/.env.local` and
restart Vite.

### `invalid URI query parameter: "schema"`

Some tools produce Prisma-style URLs ending in `?schema=public`. psycopg/libpq
does not understand `schema`. The backend removes this parameter automatically;
if you use `psql` directly, remove it from the URL.

### Database password contains special characters

URL-encode it in `DATABASE_URL`. For example, `p@ss#1` becomes `p%40ss%231`.

### `docker: command not found`

Install Docker Desktop and start it before running the container command. If
Docker is not available, use the native PostgreSQL option.

---

## 16. Verification status

Checks completed while creating this project:

- Python syntax compilation passed for `backend/app` and `backend/tests`.
- `python -m pytest -q` passed: **35 tests passed**.
- `npm run build` passed with Vite 6; the bundle uses `http://localhost:8000`
  as the API base URL.
- `npm run dev` served the frontend at `http://localhost:5173` with HTTP `200`.
- The frontend source contains no TypeScript files, `tsconfig` files, database
  URLs, database passwords, or Supabase service-role keys.
- `GET /api/health` returned `200` from a running Uvicorn server.
- `GET /api/health/db` returned `200` with a real query from a running Uvicorn
  server: database `recuirement_agent`, user `postgres`, PostgreSQL `18.6`.
- The lifespan-managed pool opened with `min_size=1`, `max_size=5`, served a
  query, and closed cleanly on shutdown.
- `GET /api/auth/me` returned `401` with no token and with an invalid token.
- `GET /docs` and `/openapi.json` returned `200`.
- CORS preflight from `http://localhost:5173` returned `200`; a preflight from
  an unapproved origin returned `400`.
- The Supabase Auth settings endpoint returned `200`, confirming the configured
  project URL and publishable key are reachable.
- Read-only PostgreSQL verification passed:
  - Server: PostgreSQL `18.6`, database `recuirement_agent`, user `postgres`.
  - `pgcrypto` `1.4` installed.
  - `jobs` and `candidates` tables exist with all expected columns.
  - Primary keys, NOT NULL constraints, CHECK constraints, timestamp triggers,
    and `set_updated_at()` are present.
  - Current data: `jobs=1`, `candidates=0`; existing rows were not modified.
- Live CRUD smoke test passed using a temporary user UUID: create, list, get,
  update, and delete for jobs and candidates, plus cross-user `404` responses.
  Temporary rows were removed afterwards; existing data was unchanged.
- No `.ts`, `.tsx`, or `tsconfig*.json` files exist in the project source.

Checks that still require your local setup or credentials:

- Phase 2 embeddings are stored locally, so no PostgreSQL extension is needed.
  `database/schema.sql` no longer creates the `vector` extension.
- Running `database/fix_jobs_indexes.sql` if `idx_jobs_owner_created`,
  `idx_jobs_owner_status`, and `idx_jobs_required_skills` are missing. The
  script only uses `CREATE INDEX IF NOT EXISTS`.
- Real registration, email confirmation, login, and logout against your
  Supabase project. The backend tests mock token verification.
- UI-level login, logout, session restoration, and live job/candidate CRUD. The
  frontend build and Vite dev server were verified, but no Supabase test-account
  password was available to execute those flows here.

## 17. Security checklist for this project

- `.env` files are gitignored; only `.env.example` templates are committed.
- No hardcoded passwords, keys, or database URLs in source code.
- Supabase service-role key is never used.
- FastAPI verifies every protected request with Supabase Auth.
- User identity always comes from the verified token.
- SQL uses psycopg parameters; dynamic update columns come from a whitelist.
- CORS is restricted to `FRONTEND_ORIGIN`.
- Database errors return generic messages and are logged only on the server.
- A user cannot read, edit, or delete another user's records by changing a URL
  or request body.
