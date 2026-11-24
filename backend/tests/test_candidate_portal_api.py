"""API-level integration tests for Candidate Portal Phases 1-4.

External services and database access are stubbed; these exercise the real
FastAPI routes, dependency injection, and service-layer contracts.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_current_user

RECRUITER_ID = "11111111-1111-4111-8111-111111111111"
CANDIDATE_USER_ID = "22222222-2222-4222-8222-222222222222"
OTHER_CANDIDATE_USER_ID = "33333333-3333-4333-8333-333333333333"

PROFILE = {
    "id": "cand-1",
    "owner_user_id": CANDIDATE_USER_ID,
    "full_name": "Test Candidate",
    "email": "candidate@example.com",
    "phone": "123",
    "skills": ["Python"],
    "experience_years": 1,
    "education": "BS",
    "resume_text": "resume",
    "location": "Bengaluru",
}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def as_recruiter(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: {"id": RECRUITER_ID, "email": "recruiter@example.com"}
    import app.services.candidate_portal_service as cps
    monkeypatch.setattr(cps, "is_candidate", lambda uid: False)
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def as_candidate(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: {"id": CANDIDATE_USER_ID, "email": "candidate@example.com"}
    # stub candidate portal service
    import app.services.candidate_portal_service as cps
    monkeypatch.setattr(cps, "is_candidate", lambda uid: uid == CANDIDATE_USER_ID)
    monkeypatch.setattr(cps, "get_profile", lambda uid: PROFILE if uid == CANDIDATE_USER_ID else None)
    monkeypatch.setattr(cps, "dashboard", lambda uid: {"profile_completion": 80, "has_resume": True, "profile": PROFILE})
    monkeypatch.setattr(cps, "update_profile", lambda uid, changes: {**PROFILE, **changes})
    monkeypatch.setattr(cps, "create_profile", lambda uid, name, email=None: PROFILE)
    monkeypatch.setattr(cps, "ensure_candidate_role", lambda uid: None)
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def as_other_candidate(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: {"id": OTHER_CANDIDATE_USER_ID, "email": "other@example.com"}
    import app.services.candidate_portal_service as cps
    monkeypatch.setattr(cps, "is_candidate", lambda uid: uid == OTHER_CANDIDATE_USER_ID)
    monkeypatch.setattr(cps, "get_profile", lambda uid: None)
    yield
    app.dependency_overrides.pop(get_current_user, None)


# Phase 1
def test_phase1_onboard(client, as_candidate):
    r = client.post("/api/candidate/onboard", json={"full_name": "Test Candidate"})
    assert r.status_code in (200, 201)

def test_phase1_me(client, as_candidate):
    r = client.get("/api/candidate/me")
    assert r.status_code == 200
    assert r.json()["full_name"] == "Test Candidate"

def test_phase1_dashboard(client, as_candidate):
    r = client.get("/api/candidate/dashboard")
    assert r.status_code == 200
    assert "profile_completion" in r.json()

def test_phase1_update(client, as_candidate):
    r = client.put("/api/candidate/me", json={"phone": "999"})
    assert r.status_code == 200

def test_phase1_candidate_blocked_from_recruiter(client, as_candidate, monkeypatch):
    import app.services.candidate_service as cs
    monkeypatch.setattr(cs, "list_candidates", lambda uid: [])
    r = client.get("/api/candidates")
    assert r.status_code == 403

def test_phase1_recruiter_blocked_from_candidate(client, as_recruiter):
    r = client.get("/api/candidate/me")
    assert r.status_code == 403


def test_candidate_blocked_from_recruiter_api_routers(client, as_candidate):
    assert client.get("/api/jobs").status_code == 403
    assert client.get("/api/interviews/sessions/current").status_code == 403
    assert client.get("/api/notifications").status_code == 403

def test_phase1_other_candidate_isolated(client, as_other_candidate):
    r = client.get("/api/candidate/me")
    assert r.status_code == 404


def test_auth_role_endpoint_returns_candidate(client, as_candidate, monkeypatch):
    import app.services.candidate_portal_service as cps
    monkeypatch.setattr(cps, "get_account_role", lambda uid, metadata=None: "candidate")
    r = client.get("/api/auth/role")
    assert r.status_code == 200
    assert r.json() == {"role": "candidate", "user_id": CANDIDATE_USER_ID}


def test_auth_role_endpoint_returns_recruiter(client, as_recruiter, monkeypatch):
    import app.services.candidate_portal_service as cps
    monkeypatch.setattr(cps, "get_account_role", lambda uid, metadata=None: "recruiter")
    r = client.get("/api/auth/role")
    assert r.status_code == 200
    assert r.json() == {"role": "recruiter", "user_id": RECRUITER_ID}


def test_account_role_reads_user_roles_table(monkeypatch):
    import contextlib
    import app.services.candidate_portal_service as cps
    from app.database import user_role_queries

    monkeypatch.setattr(cps, "get_connection", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(user_role_queries, "get_role", lambda conn, uid: "candidate")
    assert cps.get_account_role(CANDIDATE_USER_ID) == "candidate"
    monkeypatch.setattr(user_role_queries, "get_role", lambda conn, uid: None)
    assert cps.get_account_role(RECRUITER_ID) == "recruiter"

    persisted = []
    monkeypatch.setattr(cps, "ensure_candidate_role", lambda uid: persisted.append(uid))
    assert cps.get_account_role(CANDIDATE_USER_ID, {"role": "candidate"}) == "candidate"
    assert persisted == [CANDIDATE_USER_ID]


def test_candidate_dashboard_aggregates_real_sections(monkeypatch):
    """Dashboard uses applications, interviews and messages, not mock stats."""
    import app.services.candidate_portal_service as cps
    import app.services.application_service as apps
    import app.services.candidate_interview_service as cis
    import app.services.messaging_service as ms

    monkeypatch.setattr(cps, "get_profile", lambda uid: PROFILE)
    monkeypatch.setattr(
        apps,
        "list_my_applications",
        lambda uid: [
            {"id": "a1", "status": "under_review", "job_title": "Dev"},
            {"id": "a2", "status": "shortlisted", "job_title": "QA"},
            {"id": "a3", "status": "applied", "job_title": "Ops"},
        ],
    )
    monkeypatch.setattr(
        cis,
        "list_my_interviews",
        lambda uid: [
            {"id": "i1", "status": "scheduled", "interview_date": "2999-01-01", "start_time": "10:00:00"},
            {"id": "i2", "status": "cancelled", "interview_date": "2999-01-02", "start_time": "10:00:00"},
        ],
    )
    monkeypatch.setattr(
        ms,
        "list_conversations",
        lambda uid: [{"id": "c1", "job_title": "Dev", "unread_count": 2, "last_message": "Hello"}],
    )

    data = cps.dashboard(CANDIDATE_USER_ID)
    assert data["stats"] == {
        "total_applications": 3,
        "under_review": 1,
        "shortlisted": 1,
        "upcoming_interviews": 1,
    }
    assert data["recent_applications"][0]["id"] == "a1"
    assert data["upcoming_interviews"][0]["id"] == "i1"
    assert data["recent_messages"][0]["unread_count"] == 2
    assert data["has_resume"] is True
    assert data["profile_completion"] == 100


# Phase 2
def test_phase2_jobs_and_apply(client, as_candidate, monkeypatch):
    import app.services.application_service as apps
    monkeypatch.setattr(apps, "list_open_jobs", lambda: [{"id": "job-1", "title": "Dev", "status": "open"}])
    monkeypatch.setattr(apps, "get_open_job", lambda jid: {"id": jid, "title": "Dev", "status": "open"})
    monkeypatch.setattr(apps, "apply", lambda uid, jid: {"id": "app-1", "candidate_id": "cand-1", "job_id": jid, "status": "applied"})
    monkeypatch.setattr(apps, "list_my_applications", lambda uid: [{"id": "app-1", "status": "applied"}])

    r = client.get("/api/candidate/jobs")
    assert r.status_code == 200
    r = client.get("/api/candidate/jobs/job-1")
    assert r.status_code == 200
    r = client.post("/api/candidate/jobs/job-1/apply")
    assert r.status_code == 201
    r = client.get("/api/candidate/applications")
    assert r.status_code == 200


def test_phase2_duplicate_apply(client, as_candidate, monkeypatch):
    import app.services.application_service as apps
    monkeypatch.setattr(apps, "get_open_job", lambda jid: {"id": jid, "status": "open"})
    monkeypatch.setattr(apps, "apply", lambda uid, jid: {"duplicate": True})
    r = client.post("/api/candidate/jobs/job-1/apply")
    assert r.status_code == 409


def test_phase2_recruiter_applicants(client, as_recruiter, monkeypatch):
    import app.services.application_service as apps
    monkeypatch.setattr(apps, "list_applicants", lambda uid, jid: [{"id": "app-1", "candidate_name": "C", "status": "applied"}])
    monkeypatch.setattr(apps, "update_status", lambda uid, aid, st: {"id": aid, "status": st})
    import app.database.queries as q
    monkeypatch.setattr(q, "get_job", lambda conn, uid, jid: {"id": jid})
    r = client.get("/api/jobs/job-1/applicants")
    assert r.status_code == 200
    r = client.patch("/api/applications/app-1", json={"status": "shortlisted"})
    assert r.status_code == 200
    assert r.json()["status"] == "shortlisted"


# Phase 3
def test_phase3_interviews(client, as_candidate, monkeypatch):
    import app.services.candidate_interview_service as cis
    monkeypatch.setattr(cis, "list_my_interviews", lambda uid: [{"id": "iv-1", "title": "I", "candidate_response": "awaiting"}])
    monkeypatch.setattr(cis, "accept", lambda uid, iid: {"id": iid, "candidate_response": "accepted"})
    monkeypatch.setattr(cis, "decline", lambda uid, iid, reason=None: {"id": iid, "candidate_response": "declined"})
    monkeypatch.setattr(cis, "request_reschedule", lambda uid, iid, d, t, reason=None: {"id": iid, "candidate_response": "reschedule_requested"})
    r = client.get("/api/candidate/interviews")
    assert r.status_code == 200
    r = client.post("/api/candidate/interviews/iv-1/accept")
    assert r.status_code == 200
    r = client.post("/api/candidate/interviews/iv-1/decline", json={"reason": "no"})
    assert r.status_code == 200
    r = client.post("/api/candidate/interviews/iv-1/reschedule-request", json={"suggested_date": "2026-12-01", "suggested_start_time": "10:00:00", "reason": "x"})
    assert r.status_code == 200


# Phase 4
def test_phase4_messaging(client, as_candidate, as_recruiter, monkeypatch):
    import app.services.messaging_service as ms
    monkeypatch.setattr(ms, "list_conversations", lambda uid: [{"id": "conv-1"}])
    monkeypatch.setattr(ms, "list_messages", lambda uid, cid: [{"id": "m-1", "content": "hi", "sender_role": "recruiter"}])
    monkeypatch.setattr(ms, "send_message", lambda uid, cid, content: {"id": "m-2", "content": content, "sender_role": "candidate"})
    monkeypatch.setattr(ms, "start_or_get_conversation", lambda rid, cid, aid=None: {"id": "conv-1", "recruiter_user_id": rid, "candidate_id": cid})

    # recruiter starts conversation
    app.dependency_overrides[get_current_user] = lambda: {"id": RECRUITER_ID, "email": "recruiter@example.com"}
    r = client.post("/api/conversations", json={"candidate_id": "cand-1"})
    assert r.status_code == 200

    # candidate lists
    import app.services.candidate_portal_service as cps
    monkeypatch.setattr(cps, "is_candidate", lambda uid: uid == CANDIDATE_USER_ID)
    app.dependency_overrides[get_current_user] = lambda: {"id": CANDIDATE_USER_ID, "email": "candidate@example.com"}
    r = client.get("/api/candidate/conversations")
    assert r.status_code == 200

    # send + retrieve
    r = client.post("/api/candidate/conversations/conv-1/messages", json={"content": "hello"})
    assert r.status_code == 200
    r = client.get("/api/candidate/conversations/conv-1/messages")
    assert r.status_code == 200

    app.dependency_overrides.pop(get_current_user, None)
