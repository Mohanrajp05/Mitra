"""Tests for health checks and Supabase token verification."""

from fastapi.testclient import TestClient

from app.core import security
from app.main import app

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "database_configured" in body
    assert "auth_configured" in body


def test_me_requires_bearer_token():
    with TestClient(app) as client:
        response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token."


def test_me_rejects_invalid_token(monkeypatch):
    async def fake_fetch(token: str):
        raise security._unauthorized()

    monkeypatch.setattr(security, "_fetch_supabase_user", fake_fetch)

    with TestClient(app) as client:
        response = client.get(
            "/api/auth/me", headers={"Authorization": "Bearer invalid-token"}
        )

    assert response.status_code == 401


def test_me_returns_verified_supabase_user(monkeypatch):
    async def fake_fetch(token: str):
        assert token == "valid-token"
        return {
            "id": TEST_USER_ID,
            "email": "student@example.com",
            "user_metadata": {"full_name": "Demo Student"},
        }

    monkeypatch.setattr(security, "_fetch_supabase_user", fake_fetch)

    with TestClient(app) as client:
        response = client.get(
            "/api/auth/me", headers={"Authorization": "Bearer valid-token"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == TEST_USER_ID
    assert body["email"] == "student@example.com"
    assert body["user_metadata"]["full_name"] == "Demo Student"
