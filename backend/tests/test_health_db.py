"""Tests for the database health endpoint and pool lifespan wiring."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

from app.api import health as health_api
from app.database.connection import (
    DatabaseNotConfiguredError,
    DatabasePoolUnavailableError,
)
from app.main import app, database_pool_timeout_handler


class FakeCursor:
    def __init__(self, row):
        self._row = row
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self.executed = sql

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, row):
        self._cursor = FakeCursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def cursor(self):
        return self._cursor


def test_db_health_runs_a_real_query_and_reports_ok(monkeypatch):
    connection = FakeConnection(
        {
            "database_name": "recuirement_agent",
            "database_user": "postgres",
            "server_version": "PostgreSQL 18.6 on x86_64-windows, compiled by MSVC",
        }
    )

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(health_api, "get_connection", fake_get_connection)

    with TestClient(app) as client:
        response = client.get("/api/health/db")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["database_name"] == "recuirement_agent"
    assert body["server_version"] == "PostgreSQL 18.6 on x86_64-windows"
    assert "SELECT" in connection._cursor.executed.upper()


def test_db_health_returns_503_when_pool_is_unavailable(monkeypatch):
    @contextmanager
    def failing_get_connection():
        raise DatabasePoolUnavailableError("pool is not open")
        yield  # pragma: no cover

    monkeypatch.setattr(health_api, "get_connection", failing_get_connection)

    with TestClient(app) as client:
        response = client.get("/api/health/db")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["database"] == "unavailable"


def test_db_health_returns_503_when_database_is_not_configured(monkeypatch):
    @contextmanager
    def failing_get_connection():
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured.")
        yield  # pragma: no cover

    monkeypatch.setattr(health_api, "get_connection", failing_get_connection)

    with TestClient(app) as client:
        response = client.get("/api/health/db")

    assert response.status_code == 503


def test_db_health_returns_503_when_query_fails(monkeypatch):
    class BrokenCursor(FakeCursor):
        def execute(self, sql, params=None):
            raise RuntimeError("connection reset")

    class BrokenConnection(FakeConnection):
        def __init__(self):
            self._cursor = BrokenCursor(None)

    @contextmanager
    def failing_get_connection():
        yield BrokenConnection()

    monkeypatch.setattr(health_api, "get_connection", failing_get_connection)

    with TestClient(app) as client:
        response = client.get("/api/health/db")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Could not connect to the application database."
    )


def test_lifespan_opens_and_closes_the_pool(monkeypatch):
    calls = []
    monkeypatch.setattr("app.main.open_pool", lambda: calls.append("open"))
    monkeypatch.setattr("app.main.close_pool", lambda: calls.append("close"))

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert calls == ["open"]

    assert calls == ["open", "close"]


def test_app_still_starts_when_pool_initialization_fails(monkeypatch):
    def failing_open_pool():
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.main.open_pool", failing_open_pool)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_pool_timeout_handler_returns_503():
    request = SimpleNamespace(url=SimpleNamespace(path="/api/jobs"))

    response = asyncio.run(
        database_pool_timeout_handler(request, PoolTimeout("pool timeout"))
    )

    assert response.status_code == 503
    assert b"currently unavailable" in response.body
