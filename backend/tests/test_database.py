"""Tests for database connection-string and pool handling (no live database)."""

from types import SimpleNamespace

import pytest

from app.database import connection
from app.database.connection import (
    DatabaseNotConfiguredError,
    DatabasePoolUnavailableError,
    get_connection,
    normalize_database_url,
)


def test_normalize_database_url_removes_prisma_schema_parameter():
    url = (
        "postgresql://user:pass@localhost:5432/app_db"
        "?schema=public&sslmode=disable"
    )

    assert (
        normalize_database_url(url)
        == "postgresql://user:pass@localhost:5432/app_db?sslmode=disable"
    )


def test_normalize_database_url_leaves_clean_url_unchanged():
    url = "postgresql://user:pass@localhost:5432/app_db"

    assert normalize_database_url(url) == url


def test_build_pool_requires_database_url(monkeypatch):
    monkeypatch.setattr(connection, "settings", SimpleNamespace(database_url=""))

    with pytest.raises(DatabaseNotConfiguredError):
        connection.build_pool()


def test_get_connection_requires_an_open_pool(monkeypatch):
    monkeypatch.setattr(connection, "_pool", None)

    with pytest.raises(DatabasePoolUnavailableError):
        with get_connection():
            pass  # pragma: no cover


def test_close_pool_is_safe_when_pool_was_never_opened(monkeypatch):
    monkeypatch.setattr(connection, "_pool", None)

    connection.close_pool()

    assert connection._pool is None
