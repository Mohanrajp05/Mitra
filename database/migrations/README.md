# Database migrations

Phase 1 uses a single `database/schema.sql` file because there is only one
initial schema.

For future changes, add numbered SQL files here instead of editing the schema
that has already been applied, for example:

```text
001_add_embedding_columns.sql
002_add_interview_notes.sql
```

Apply them with:

```powershell
psql -U postgres -d ai_recruitment -f database/migrations/001_add_embedding_columns.sql
```

Embeddings are stored locally under `backend/data/rag/` as NumPy arrays with
JSON metadata. No database extension or vector column is required.
