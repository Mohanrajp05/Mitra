"""Apply a non-destructive migration file against the application database.

Only runs statements that create new objects or add nullable columns (CREATE
TABLE/INDEX/TRIGGER IF NOT EXISTS and ALTER TABLE ... ADD COLUMN IF NOT
EXISTS). Refuses files containing destructive statements.
"""

import re
import sys
from pathlib import Path

from app.database.connection import close_pool, get_connection, open_pool

FORBIDDEN = re.compile(
    r"\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|DELETE\s+FROM)\b"
    r"|\bALTER\s+TABLE\b(?!"
    r"\s+\w+\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b)",
    re.IGNORECASE,
)


def main(path: str) -> int:
    sql = Path(path).read_text(encoding="utf-8")
    if FORBIDDEN.search(sql):
        print("REFUSED: migration contains destructive statements.")
        return 2

    try:
        open_pool()
    except Exception as exc:
        print(f"DATABASE_UNAVAILABLE: {type(exc).__name__}")
        return 1

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
            print(f"APPLIED: {path}")
        return 0
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}")
        return 1
    finally:
        try:
            close_pool()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
