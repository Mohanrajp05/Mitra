"""Tests for candidate routes, validation, and ownership propagation."""

from app.api import candidates as candidates_api
from tests.conftest import TEST_USER_ID

CANDIDATE = {
    "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "owner_user_id": TEST_USER_ID,
    "full_name": "Asha Demo",
    "email": "asha.demo@example.com",
    "phone": "+91 90000 00000",
    "skills": ["Python", "SQL"],
    "experience_years": 2.0,
    "education": "B.Sc. Computer Science",
    "resume_text": "Fictional resume used for demonstration only.",
    "created_at": "2026-01-11T09:30:00Z",
    "updated_at": "2026-01-11T09:30:00Z",
}

NEW_CANDIDATE = {
    "full_name": "Ravi Demo",
    "email": "ravi.demo@example.com",
    "phone": "",
    "skills": ["React", "JavaScript"],
    "experience_years": 1,
    "education": "B.Tech Information Technology",
    "resume_text": "Fictional candidate profile.",
}


def test_list_candidates_uses_authenticated_owner(client, monkeypatch):
    seen = {}

    def fake_list(owner_user_id):
        seen["owner"] = owner_user_id
        return [CANDIDATE]

    monkeypatch.setattr(candidates_api.candidate_service, "list_candidates", fake_list)

    response = client.get("/api/candidates")

    assert response.status_code == 200
    assert seen["owner"] == TEST_USER_ID
    assert response.json()[0]["full_name"] == CANDIDATE["full_name"]


def test_create_candidate_assigns_verified_owner(client, monkeypatch):
    def fake_create(owner_user_id, payload):
        assert owner_user_id == TEST_USER_ID
        assert payload.full_name == NEW_CANDIDATE["full_name"]
        assert payload.phone is None
        return {**CANDIDATE, **payload.model_dump()}

    monkeypatch.setattr(
        candidates_api.candidate_service, "create_candidate", fake_create
    )

    response = client.post("/api/candidates", json=NEW_CANDIDATE)

    assert response.status_code == 201
    assert response.json()["owner_user_id"] == TEST_USER_ID


def test_create_candidate_rejects_client_supplied_owner(client):
    payload = {
        **NEW_CANDIDATE,
        "owner_user_id": "22222222-2222-4222-8222-222222222222",
    }

    response = client.post("/api/candidates", json=payload)

    assert response.status_code == 422


def test_create_candidate_validates_email(client):
    response = client.post(
        "/api/candidates", json={**NEW_CANDIDATE, "email": "not-an-email"}
    )

    assert response.status_code == 422


def test_get_candidate_returns_404_when_not_owned(client, monkeypatch):
    monkeypatch.setattr(
        candidates_api.candidate_service,
        "get_candidate",
        lambda owner, candidate_id: None,
    )

    response = client.get(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 404


def test_update_candidate_passes_owner_and_returns_record(client, monkeypatch):
    def fake_update(owner_user_id, candidate_id, payload):
        assert owner_user_id == TEST_USER_ID
        assert candidate_id == CANDIDATE["id"]
        assert payload.education == "M.Sc. Computer Science"
        return {**CANDIDATE, "education": payload.education}

    monkeypatch.setattr(
        candidates_api.candidate_service, "update_candidate", fake_update
    )

    response = client.put(
        f"/api/candidates/{CANDIDATE['id']}",
        json={"education": "M.Sc. Computer Science"},
    )

    assert response.status_code == 200
    assert response.json()["education"] == "M.Sc. Computer Science"


def test_update_candidate_rejects_null_full_name(client):
    response = client.put(
        f"/api/candidates/{CANDIDATE['id']}", json={"full_name": None}
    )

    assert response.status_code == 422


def test_delete_candidate_returns_204(client, monkeypatch):
    monkeypatch.setattr(
        candidates_api.candidate_service,
        "delete_candidate",
        lambda owner, candidate_id: True,
    )

    response = client.delete(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 204


def test_delete_candidate_returns_404_when_not_owned(client, monkeypatch):
    monkeypatch.setattr(
        candidates_api.candidate_service,
        "delete_candidate",
        lambda owner, candidate_id: False,
    )

    response = client.delete(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 404


LINKED_RESUME = {
    "document_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "filename": "Smitha_Rao_Resume.pdf",
    "mime_type": "application/pdf",
    "byte_size": 123456,
    "chunk_count": 4,
    "created_at": "2026-11-17T10:00:00+00:00",
}


def test_get_candidate_returns_linked_resume_documents(client, monkeypatch):
    def fake_get(owner_user_id, candidate_id):
        assert owner_user_id == TEST_USER_ID
        return dict(CANDIDATE)

    def fake_package(owner_user_id, candidate):
        assert candidate["id"] == CANDIDATE["id"]
        return ("Full parsed resume text from the linked document.", [dict(LINKED_RESUME)])

    monkeypatch.setattr(candidates_api.candidate_service, "get_candidate", fake_get)
    monkeypatch.setattr(
        candidates_api.rag_service, "candidate_resume_package", fake_package
    )

    response = client.get(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 200
    body = response.json()
    # The parsed resume text from the linked document replaces a short
    # hand-typed placeholder so the profile shows the real resume.
    assert body["resume_text"] == "Full parsed resume text from the linked document."
    assert body["resume_documents"] == [LINKED_RESUME]


def test_get_candidate_keeps_stored_text_without_linked_documents(client, monkeypatch):
    def fake_get(owner_user_id, candidate_id):
        return dict(CANDIDATE)

    def fake_package(owner_user_id, candidate):
        return (None, [])

    monkeypatch.setattr(candidates_api.candidate_service, "get_candidate", fake_get)
    monkeypatch.setattr(
        candidates_api.rag_service, "candidate_resume_package", fake_package
    )

    response = client.get(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["resume_text"] == CANDIDATE["resume_text"]
    assert body["resume_documents"] == []


def test_list_candidates_does_not_enrich_documents(client, monkeypatch):
    monkeypatch.setattr(
        candidates_api.candidate_service, "list_candidates", lambda owner: [dict(CANDIDATE)]
    )

    response = client.get("/api/candidates")

    assert response.status_code == 200
    assert response.json()[0]["resume_documents"] == []


EXTRACTED_PROFILE = {
    "summary": "Cloud engineer with 6 years of experience.",
    "skills": ["AWS", "Kubernetes", "Terraform"],
    "experience": [
        {"title": "Cloud Engineer", "company": "Acme Corp", "period": "2019 - Present"}
    ],
    "education": ["B.Tech Computer Science"],
    "certifications": [],
    "total_years": 6.0,
    "extraction_method": "deterministic",
}


def test_get_candidate_returns_extracted_profile(client, monkeypatch):
    def fake_get(owner_user_id, candidate_id):
        return {**CANDIDATE, "extracted_profile": EXTRACTED_PROFILE}

    def fake_package(owner_user_id, candidate):
        return (CANDIDATE["resume_text"], [])

    monkeypatch.setattr(candidates_api.candidate_service, "get_candidate", fake_get)
    monkeypatch.setattr(candidates_api.rag_service, "candidate_resume_package", fake_package)

    response = client.get(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_profile"]["skills"] == ["AWS", "Kubernetes", "Terraform"]
    assert body["extracted_profile"]["experience"][0]["company"] == "Acme Corp"


def test_get_candidate_backfills_missing_extracted_profile(client, monkeypatch):
    """Existing candidates get a deterministic profile on first detail view."""
    def fake_get(owner_user_id, candidate_id):
        return dict(CANDIDATE)

    def fake_package(owner_user_id, candidate):
        return (
            "Jane Doe\nSenior Cloud Engineer\njane.doe@example.com\n\n"
            "Skills: AWS, Azure, Docker, Kubernetes, Terraform, Python\n\n"
            "Experience\nSenior Cloud Engineer at Acme Corp, 2019 - Present\n"
            "- 6+ years of hands-on cloud engineering across AWS and Azure.\n",
            [],
        )

    backfilled = {}

    def fake_backfill(owner_user_id, candidate, resume_text):
        backfilled["owner"] = owner_user_id
        backfilled["resume_text"] = resume_text
        return {
            "extraction_method": "deterministic",
            "skills": ["AWS", "Azure"],
            "experience": [],
        }

    monkeypatch.setattr(candidates_api.candidate_service, "get_candidate", fake_get)
    monkeypatch.setattr(candidates_api.rag_service, "candidate_resume_package", fake_package)
    from app.services import extraction_service
    monkeypatch.setattr(extraction_service, "extract_profile_deterministic", fake_backfill)

    response = client.get(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 200
    body = response.json()
    assert backfilled["owner"] == TEST_USER_ID
    assert body["extracted_profile"]["skills"] == ["AWS", "Azure"]


def test_get_candidate_backfill_failure_is_contained(client, monkeypatch):
    """A failing backfill must not break the detail response."""

    def fake_get(owner_user_id, candidate_id):
        return dict(CANDIDATE)

    def fake_package(owner_user_id, candidate):
        return ("Jane Doe is a Python developer with long resume text.", [])

    def broken_backfill(*args):
        raise RuntimeError("backfill exploded")

    monkeypatch.setattr(candidates_api.candidate_service, "get_candidate", fake_get)
    monkeypatch.setattr(candidates_api.rag_service, "candidate_resume_package", fake_package)
    from app.services import extraction_service
    monkeypatch.setattr(extraction_service, "extract_profile_deterministic", broken_backfill)

    response = client.get(f"/api/candidates/{CANDIDATE['id']}")

    assert response.status_code == 200
    assert response.json()["extracted_profile"] is None
