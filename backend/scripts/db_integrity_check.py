"""Read-only database integrity check for the Stage 9 audit.

Prints only structural facts: table existence, row counts, constraints,
indexes. Never prints connection details or credentials.
"""

from app.database.connection import close_pool, get_connection, open_pool

CHECKS = {
    "tables": """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """,
    "consent_constraints": """
        SELECT conname, contype
        FROM pg_constraint
        WHERE conrelid = 'candidate_consents'::regclass
        ORDER BY conname
    """,
    "consent_indexes": """
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'candidate_consents'
        ORDER BY indexname
    """,
    "chat_message_cascade": """
        SELECT confdeltype FROM pg_constraint
        WHERE conrelid = 'chat_messages'::regclass
          AND confrelid = 'chat_sessions'::regclass
    """,
    "counts": """
        SELECT
            (SELECT count(*) FROM jobs) AS jobs,
            (SELECT count(*) FROM candidates) AS candidates,
            (SELECT count(*) FROM chat_sessions) AS chat_sessions,
            (SELECT count(*) FROM chat_messages) AS chat_messages,
            (SELECT count(*) FROM candidate_consents) AS candidate_consents
    """,
    "candidate_columns": """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'candidates'
        ORDER BY ordinal_position
    """,
}


def main() -> None:
    try:
        open_pool()
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for name, sql in CHECKS.items():
                    try:
                        cursor.execute(sql)
                        rows = cursor.fetchall()
                        if name == "counts":
                            print(f"{name}: {dict(rows[0]) if rows else rows}")
                        else:
                            print(
                                f"{name}: "
                                f"{[tuple(r.values()) if hasattr(r, 'values') else tuple(r) for r in rows]}"
                            )
                    except Exception as exc:
                        connection.rollback()
                        print(f"{name}: ERROR {type(exc).__name__}")
    except Exception as exc:
        print(f"DATABASE_UNAVAILABLE: {type(exc).__name__}")
    finally:
        try:
            close_pool()
        except Exception:
            pass


if __name__ == "__main__":
    main()
