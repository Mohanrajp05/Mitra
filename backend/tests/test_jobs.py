"""Tests for job routes, validation, and ownership propagation."""

from app.api import jobs as jobs_api
from tests.conftest import TEST_USER_ID

JOB = {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "owner_user_id": TEST_USER_ID,
    "title": "Junior Python Developer",
    "company": "Fictional Demo Company",
    "description": "Build small internal tools with Python and FastAPI.",
    "required_skills": ["Python", "FastAPI"],
    "experience_required": 1.0,
    "location": "Remote",
    "status": "open",
    "created_at": "2026-01-10T10:00:00Z",
    "updated_at": "2026-01-10T10:00:00Z",
}

NEW_JOB = {
    "title": "Frontend Developer",
    "company": "Example College Lab",
    "description": "Create accessible React interfaces.",
    "required_skills": ["React", "CSS"],
    "experience_required": 0,
    "location": "On campus",
    "status": "open",
}


def test_list_jobs_uses_authenticated_owner(client, monkeypatch):
    seen = {}

    def fake_list(owner_user_id):
        seen["owner"] = owner_user_id
        return [JOB]

    monkeypatch.setattr(jobs_api.job_service, "list_jobs", fake_list)

    response = client.get("/api/jobs")

    assert response.status_code == 200
    assert seen["owner"] == TEST_USER_ID
    assert response.json()[0]["title"] == JOB["title"]


def test_create_job_assigns_verified_owner(client, monkeypatch):
    def fake_create(owner_user_id, payload):
        assert owner_user_id == TEST_USER_ID
        assert payload.title == NEW_JOB["title"]
        return {**JOB, **payload.model_dump()}

    monkeypatch.setattr(jobs_api.job_service, "create_job", fake_create)

    response = client.post("/api/jobs", json=NEW_JOB)

    assert response.status_code == 201
    assert response.json()["owner_user_id"] == TEST_USER_ID


def test_create_job_rejects_client_supplied_owner(client):
    payload = {**NEW_JOB, "owner_user_id": "22222222-2222-4222-8222-222222222222"}

    response = client.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_create_job_validates_required_fields(client):
    response = client.post("/api/jobs", json={"title": "", "description": ""})

    assert response.status_code == 422


def test_get_job_returns_404_when_not_owned(client, monkeypatch):
    monkeypatch.setattr(jobs_api.job_service, "get_job", lambda owner, job_id: None)

    response = client.get(f"/api/jobs/{JOB['id']}")

    assert response.status_code == 404


def test_update_job_passes_owner_and_returns_record(client, monkeypatch):
    def fake_update(owner_user_id, job_id, payload):
        assert owner_user_id == TEST_USER_ID
        assert job_id == JOB["id"]
        assert payload.status == "closed"
        return {**JOB, "status": "closed"}

    monkeypatch.setattr(jobs_api.job_service, "update_job", fake_update)

    response = client.put(f"/api/jobs/{JOB['id']}", json={"status": "closed"})

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_update_job_rejects_null_required_field(client):
    response = client.put(f"/api/jobs/{JOB['id']}", json={"title": None})

    assert response.status_code == 422


def test_update_job_rejects_owner_change(client):
    response = client.put(
        f"/api/jobs/{JOB['id']}",
        json={"owner_user_id": "22222222-2222-4222-8222-222222222222"},
    )

    assert response.status_code == 422


def test_delete_job_returns_204(client, monkeypatch):
    monkeypatch.setattr(
        jobs_api.job_service, "delete_job", lambda owner, job_id: True
    )

    response = client.delete(f"/api/jobs/{JOB['id']}")

    assert response.status_code == 204
    assert response.content == b""


def test_delete_job_returns_404_when_not_owned(client, monkeypatch):
    monkeypatch.setattr(
        jobs_api.job_service, "delete_job", lambda owner, job_id: False
    )

    response = client.delete(f"/api/jobs/{JOB['id']}")

    assert response.status_code == 404


def test_bulk_delete_jobs_passes_owner_and_ids(client, monkeypatch):
    seen = {}

    def fake_delete_jobs(owner_user_id, job_ids):
        seen["owner"] = owner_user_id
        seen["ids"] = list(job_ids)
        return 2

    monkeypatch.setattr(jobs_api.job_service, "delete_jobs", fake_delete_jobs)

    response = client.post(
        "/api/jobs/bulk-delete",
        json={
            "ids": [
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": 2, "requested": 2}
    assert seen["owner"] == TEST_USER_ID
    assert seen["ids"] == [
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    ]


def test_bulk_delete_reports_partial_result(client, monkeypatch):
    def fake_delete_jobs(owner_user_id, job_ids):
        assert owner_user_id == TEST_USER_ID
        return 1

    monkeypatch.setattr(jobs_api.job_service, "delete_jobs", fake_delete_jobs)

    response = client.post(
        "/api/jobs/bulk-delete",
        json={
            "ids": [
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": 1, "requested": 2}


def test_bulk_delete_requires_at_least_one_id(client):
    response = client.post("/api/jobs/bulk-delete", json={"ids": []})

    assert response.status_code == 422


def test_bulk_delete_rejects_invalid_uuid(client):
    response = client.post("/api/jobs/bulk-delete", json={"ids": ["not-a-uuid"]})

    assert response.status_code == 422


def test_bulk_delete_dedupes_and_rejects_owner_fields(client):
    response = client.post(
        "/api/jobs/bulk-delete",
        json={
            "ids": [
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            ],
            "owner_user_id": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert response.status_code == 422


def test_job_deletion_removes_linked_job_documents(monkeypatch):
    from app.services import job_service

    removed = []

    class FakeStore:
        def list_documents(self, owner_user_id):
            assert owner_user_id == TEST_USER_ID
            return [
                {"document_id": "doc-job", "job_id": JOB["id"]},
                {"document_id": "doc-other", "job_id": "d4d4d4d4-d4d4-4d4d-8d4d-d4d4d4d4d4d4"},
                {"document_id": "doc-resume", "job_id": None},
            ]

        def delete_document(self, owner_user_id, document_id):
            removed.append((owner_user_id, document_id))
            return True

    monkeypatch.setattr(job_service, "get_document_store", lambda: FakeStore())

    assert job_service._delete_job_documents(TEST_USER_ID, JOB["id"]) == 1
    assert removed == [(TEST_USER_ID, "doc-job")]


def test_job_document_cleanup_failure_is_contained(monkeypatch):
    from app.services import job_service

    class ExplodingStore:
        def list_documents(self, owner_user_id):
            raise RuntimeError("vector store unavailable")

    monkeypatch.setattr(
        job_service, "get_document_store", lambda: ExplodingStore()
    )

    assert job_service._delete_job_documents(TEST_USER_ID, JOB["id"]) == 0
