"""PostgreSQL connection pool helpers.

A single ``psycopg_pool.ConnectionPool`` is created during FastAPI startup
(lifespan) and closed on shutdown. Service code borrows a connection from the
pool through :func:`get_connection`; the pool commits on success and rolls back
on error before returning the connection.

All SQL is executed with psycopg parameter binding in ``queries.py``.
"""

from contextlib import contextmanager
from typing import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

# Prisma-style connection strings sometimes include ?schema=public.
# libpq/psycopg does not understand that parameter, so it is ignored here.
UNSUPPORTED_QUERY_PARAMS = {"schema"}

POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 5
POOL_OPEN_TIMEOUT = 10


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when DATABASE_URL is missing."""


class DatabasePoolUnavailableError(RuntimeError):
    """Raised when the connection pool has not been opened."""


def normalize_database_url(url: str) -> str:
    """Remove query parameters that psycopg/libpq cannot understand."""
    parts = urlsplit(url)
    if not parts.query:
        return url

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in UNSUPPORTED_QUERY_PARAMS
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


# The pool is module-level state owned by the FastAPI lifespan.
_pool: ConnectionPool | None = None


def build_pool() -> ConnectionPool:
    """Create a pool object without opening any connections yet."""
    if not settings.database_url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured.")

    return ConnectionPool(
        conninfo=normalize_database_url(settings.database_url),
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        kwargs={"row_factory": dict_row, "connect_timeout": POOL_OPEN_TIMEOUT},
        name="ai-recruitment-pool",
        open=False,
    )


def open_pool() -> ConnectionPool:
    """Build and open the pool, waiting until at least one connection exists."""
    global _pool

    if _pool is not None:
        return _pool

    pool = build_pool()
    try:
        pool.open(wait=True, timeout=POOL_OPEN_TIMEOUT)
    except Exception:
        # Never leave a half-open pool behind if startup fails.
        pool.close()
        raise

    _pool = pool
    return _pool


def close_pool() -> None:
    """Close the pool and release all connections."""
    global _pool

    if _pool is None:
        return

    try:
        _pool.close()
    finally:
        _pool = None


def get_pool() -> ConnectionPool:
    """Return the open pool or raise a safe application error."""
    if _pool is None:
        raise DatabasePoolUnavailableError(
            "The database connection pool is not available."
        )
    return _pool


@contextmanager
def get_connection() -> Iterator[Connection]:
    """Borrow a pooled connection for the duration of the block."""
    pool = get_pool()
    with pool.connection() as connection:
        yield connection
