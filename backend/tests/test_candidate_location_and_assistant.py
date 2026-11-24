"""Regression tests for candidate profile location and AI assistant access."""

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app
from app.api import chat as chat_api

RECRUITER_ID = "11111111-1111-4111-8111-111111111111"
CANDIDATE_USER_ID = "22222222-2222-4222-8222-222222222222"

PROFILE = {
    "id": "cand-1",
    "owner_user_id": CANDIDATE_USER_ID,
    "full_name": "Test Candidate",
    "email": "candidate@example.com",
    "phone": "123",
    "skills": ["Python"],
    "experience_years": 1,
    "education": "BS",
    "location": None,
    "resume_text": "resume",
}


@pytest.fixture
def as_candidate(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: {
        "id": CANDIDATE_USER_ID, "email": "candidate@example.com"
    }
    import app.services.candidate_portal_service as cps
    monkeypatch.setattr(cps, "is_candidate", lambda uid: uid == CANDIDATE_USER_ID)
    monkeypatch.setattr(cps, "get_profile", lambda uid: PROFILE if uid == CANDIDATE_USER_ID else None)
    monkeypatch.setattr(cps, "update_profile", lambda uid, changes: {**PROFILE, **changes})
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_candidate_profile_location_persists(client, as_candidate):
    response = client.put("/api/candidate/me", json={"location": "Bengaluru, Karnataka, India"})
    assert response.status_code == 200
    assert response.json()["location"] == "Bengaluru, Karnataka, India"

    # Simulate a fresh fetch returning the stored value.
    import app.services.candidate_portal_service as cps
    cps.get_profile = lambda uid: {**PROFILE, "location": "Bengaluru, Karnataka, India"}
    fetched = client.get("/api/candidate/me")
    assert fetched.status_code == 200
    assert fetched.json()["location"] == "Bengaluru, Karnataka, India"


def test_candidate_can_create_chat_session(client, as_candidate, monkeypatch):
    monkeypatch.setattr(chat_api.chat_service, "create_session", lambda owner, payload: {
        "id": "11111111-2222-4333-8444-555555555555",
        "owner_user_id": CANDIDATE_USER_ID,
        "title": "New conversation",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    response = client.post("/api/chat/sessions", json={})
    assert response.status_code == 201
    assert response.json()["owner_user_id"] == CANDIDATE_USER_ID


def test_candidate_can_send_chat_message(client, as_candidate, monkeypatch):
    session_id = "11111111-2222-4333-8444-555555555555"

    async def fake_send(owner, sid, payload):
        return {
            "user_message": {"id": "22222222-2222-4222-8222-222222222222", "session_id": sid, "owner_user_id": owner, "role": "user", "content": payload.content, "sources": [], "has_evidence": True, "created_at": "2026-01-01T00:00:00Z"},
            "assistant_message": {"id": "33333333-3333-4333-8333-333333333333", "session_id": sid, "owner_user_id": owner, "role": "assistant", "content": "Hello candidate!", "sources": [], "has_evidence": True, "created_at": "2026-01-01T00:00:00Z"},
        }

    monkeypatch.setattr(chat_api.chat_service, "send_message", fake_send)
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages", json={"content": "hello"}
    )
    assert response.status_code == 200
    assert response.json()["assistant_message"]["content"] == "Hello candidate!"


def test_candidate_chat_not_forbidden(client, as_candidate, monkeypatch):
    monkeypatch.setattr(chat_api.chat_service, "list_sessions", lambda owner: [])
    response = client.get("/api/chat/sessions")
    assert response.status_code == 200
