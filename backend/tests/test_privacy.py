"""Tests for Stage 8: privacy, consent, retention, export, and deletion."""

import asyncio
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import candidate_service, chat_service, privacy_service, rag_service
from tests.test_chat_service import FakeConnection

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
CANDIDATE_ID = "33333333-3333-4333-8333-333333333333"
SESSION_ID = "44444444-4444-4444-8444-444444444444"
MESSAGE_ID = "55555555-5555-4555-8555-555555555555"
JOB_ID = "66666666-6666-4666-8666-666666666666"

CANDIDATE = {
    "id": CANDIDATE_ID,
    "owner_user_id": TEST_USER_ID,
    "full_name": "Jane Candidate",
    "email": "jane.candidate@example.com",
    "phone": "+1-555-0100",
    "skills": ["python"],
    "experience_years": 5,
    "education": "BSc",
    "resume_text": "Senior python developer.",
    "created_at": "2026-11-01T10:00:00+00:00",
    "updated_at": "2026-11-01T10:00:00+00:00",
}

CONSENT_GRANTED = {
    "id": "77777777-7777-4777-8777-777777777777",
    "candidate_id": CANDIDATE_ID,
    "owner_user_id": TEST_USER_ID,
    "consent_type": "resume_processing",
    "status": "granted",
    "decided_at": "2026-11-02T09:00:00+00:00",
    "created_at": "2026-11-02T09:00:00+00:00",
    "updated_at": "2026-11-02T09:00:00+00:00",
}

CONSENT_WITHDRAWN = dict(CONSENT_GRANTED, status="withdrawn")

JOB = {
    "id": JOB_ID,
    "owner_user_id": TEST_USER_ID,
    "title": "Backend Engineer",
    "company": "Example Co",
    "description": "Build APIs.",
    "required_skills": ["python"],
    "experience_required": 3,
    "location": "Remote",
    "status": "open",
    "created_at": "2026-11-01T08:00:00+00:00",
    "updated_at": "2026-11-01T08:00:00+00:00",
}

SESSION = {
    "id": SESSION_ID,
    "owner_user_id": TEST_USER_ID,
    "title": "Screening",
    "created_at": "2026-11-03T10:00:00+00:00",
    "updated_at": "2026-11-03T10:00:00+00:00",
}

MESSAGE = {
    "id": MESSAGE_ID,
    "session_id": SESSION_ID,
    "owner_user_id": TEST_USER_ID,
    "role": "user",
    "content": "Hello",
    "sources": [],
    "has_evidence": False,
    "created_at": "2026-11-03T10:05:00+00:00",
}

OLD_DOC = {
    "document_id": "doc-old",
    "owner_user_id": TEST_USER_ID,
    "source_type": "resume",
    "candidate_id": CANDIDATE_ID,
    "job_id": None,
    "filename": "old-resume.pdf",
    "content_hash": "hash-old",
    "created_at": "2025-01-01T00:00:00+00:00",
}

NEW_DOC = dict(OLD_DOC, document_id="doc-new", filename="new-resume.pdf",
               content_hash="hash-new", created_at="2026-11-10T00:00:00+00:00")

OTHER_DOC = dict(NEW_DOC, document_id="doc-job", source_type="job_description",
                 candidate_id=None, filename="job.pdf", content_hash="hash-job")


class FakeCache:
    def __init__(self):
        self.invalidations = []

    def invalidate_user(self, owner_user_id):
        self.invalidations.append(owner_user_id)


class FakeDocumentStore:
    def __init__(self, documents=None):
        self.documents = {item["document_id"]: dict(item) for item in documents or []}
        self.deleted = []
        self.error_ids: set[str] = set()
        self.saved: list[dict] = []

    def list_documents(self, owner_user_id):
        return [
            item
            for item in self.documents.values()
            if item["owner_user_id"] == owner_user_id
        ]

    def delete_document(self, owner_user_id, document_id):
        item = self.documents.get(document_id)
        if item is None or item["owner_user_id"] != owner_user_id:
            return False
        if document_id in self.error_ids:
            raise OSError("simulated storage failure")
        del self.documents[document_id]
        self.deleted.append(document_id)
        return True

    def save_document(self, owner_user_id, **kwargs):
        self.saved.append(kwargs)
        return {"document_id": "doc-uploaded", "content_hash": "hash-new"}


def install_privacy_connection(monkeypatch, results):
    connection = FakeConnection(results)

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(privacy_service, "get_connection", fake_get_connection)
    return connection


def install_candidate_connection(monkeypatch, results):
    connection = FakeConnection(results)

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(candidate_service, "get_connection", fake_get_connection)
    return connection


def install_rag_connection(monkeypatch, results):
    connection = FakeConnection(results)

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(rag_service, "get_connection", fake_get_connection)
    return connection


@pytest.fixture
def fake_store(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(privacy_service, "get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_document_store", lambda: store)
    cache = FakeCache()
    monkeypatch.setattr(privacy_service, "get_response_cache", lambda: cache)
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: cache)
    store.cache = cache
    return store


@pytest.fixture
def clear_retention_env(monkeypatch):
    for name in privacy_service.RETENTION_POLICIES.values():
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestConsentService:
    def test_missing_consent_reported_as_not_recorded(
        self, monkeypatch, clear_retention_env, fresh_audit_trail
    ):
        install_candidate_connection(monkeypatch, [CANDIDATE, None])

        record = candidate_service.get_consent_status(
            TEST_USER_ID, CANDIDATE_ID, "resume_processing"
        )

        assert record["status"] == "not_recorded"
        assert record["decided_at"] is None
        assert record["candidate_id"] == CANDIDATE_ID
        assert all(
            event["event_type"] != "consent_granted"
            for event in fresh_audit_trail.recent()
        )

    def test_consent_grant_is_recorded(
        self, monkeypatch, clear_retention_env, fresh_audit_trail
    ):
        connection = install_candidate_connection(
            monkeypatch, [CANDIDATE, CONSENT_GRANTED]
        )

        record = candidate_service.set_consent(
            TEST_USER_ID, CANDIDATE_ID, "resume_processing", True
        )

        assert record["status"] == "granted"
        sql, params = connection.cursor_instance.executed[-1]
        assert "INSERT INTO candidate_consents" in sql
        assert "ON CONFLICT" in sql
        assert params[0] == CANDIDATE_ID
        assert params[1] == TEST_USER_ID
        assert params[3] == "granted"
        events = fresh_audit_trail.recent()
        assert events[-1]["event_type"] == "consent_granted"
        assert events[-1]["resource_id"] == CANDIDATE_ID
        assert events[-1]["user_id"] == TEST_USER_ID

    def test_consent_withdrawal_is_recorded(
        self, monkeypatch, clear_retention_env, fresh_audit_trail
    ):
        connection = install_candidate_connection(
            monkeypatch, [CANDIDATE, CONSENT_WITHDRAWN]
        )

        record = candidate_service.set_consent(
            TEST_USER_ID, CANDIDATE_ID, "resume_processing", False
        )

        assert record["status"] == "withdrawn"
        sql, params = connection.cursor_instance.executed[-1]
        assert params[3] == "withdrawn"
        assert fresh_audit_trail.recent()[-1]["event_type"] == "consent_withdrawn"

    def test_consent_for_other_users_candidate_returns_none(
        self, monkeypatch, clear_retention_env, fresh_audit_trail
    ):
        connection = install_candidate_connection(monkeypatch, [None])

        result = candidate_service.set_consent(
            TEST_USER_ID, CANDIDATE_ID, "resume_processing", True
        )

        assert result is None
        sql, params = connection.cursor_instance.executed[0]
        assert "owner_user_id = %s" in sql
        assert params[1] == TEST_USER_ID
        assert fresh_audit_trail.recent() == []

    def test_invalid_consent_type_rejected_without_sql(
        self, monkeypatch, clear_retention_env, fresh_audit_trail
    ):
        connection = install_candidate_connection(monkeypatch, [])

        with pytest.raises(candidate_service.ConsentTypeError):
            candidate_service.get_consent_status(TEST_USER_ID, CANDIDATE_ID, "email")

        with pytest.raises(candidate_service.ConsentTypeError):
            candidate_service.set_consent(TEST_USER_ID, CANDIDATE_ID, "email", True)

        assert connection.cursor_instance.executed == []
        assert fresh_audit_trail.recent() == []


class TestConsentAPI:
    def test_get_consent_not_recorded(self, client, monkeypatch):
        install_candidate_connection(monkeypatch, [CANDIDATE, None])

        response = client.get(f"/api/candidates/{CANDIDATE_ID}/consent")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "not_recorded"
        assert body["consent_type"] == "resume_processing"

    def test_put_consent_grants(self, client, monkeypatch):
        install_candidate_connection(monkeypatch, [CANDIDATE, CONSENT_GRANTED])

        response = client.put(
            f"/api/candidates/{CANDIDATE_ID}/consent",
            json={"consent_type": "resume_processing", "granted": True},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "granted"

    def test_put_consent_withdraws(self, client, monkeypatch):
        install_candidate_connection(monkeypatch, [CANDIDATE, CONSENT_WITHDRAWN])

        response = client.put(
            f"/api/candidates/{CANDIDATE_ID}/consent",
            json={"consent_type": "resume_processing", "granted": False},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "withdrawn"

    def test_consent_endpoints_reject_cross_user_access(self, client, monkeypatch):
        connection = install_candidate_connection(monkeypatch, [None])

        missing = client.get(f"/api/candidates/{CANDIDATE_ID}/consent")
        assert missing.status_code == 404

        rejected = client.put(
            f"/api/candidates/{CANDIDATE_ID}/consent",
            json={"consent_type": "resume_processing", "granted": True},
        )
        assert rejected.status_code == 404

        for sql, params in connection.cursor_instance.executed:
            assert "owner_user_id = %s" in sql
            assert params[1] == TEST_USER_ID

    def test_consent_endpoints_require_authentication(self):
        with TestClient(app) as anonymous:
            assert (
                anonymous.get(f"/api/candidates/{CANDIDATE_ID}/consent").status_code
                == 401
            )
            assert (
                anonymous.put(
                    f"/api/candidates/{CANDIDATE_ID}/consent",
                    json={"consent_type": "resume_processing", "granted": True},
                ).status_code
                == 401
            )


class TestCandidateCorrection:
    def test_update_is_audited_with_field_names_only(
        self, monkeypatch, fresh_audit_trail
    ):
        from app.schemas.candidate import CandidateUpdate

        connection = install_candidate_connection(monkeypatch, [CANDIDATE])

        candidate_service.update_candidate(
            TEST_USER_ID,
            CANDIDATE_ID,
            CandidateUpdate(full_name="Updated Name", email="new@example.com"),
        )

        events = fresh_audit_trail.recent()
        assert events[-1]["event_type"] == "candidate_updated"
        assert events[-1]["resource_id"] == CANDIDATE_ID
        assert events[-1]["user_id"] == TEST_USER_ID
        assert events[-1]["detail"] == "fields=email,full_name"
        dumped = "\n".join(str(event) for event in events)
        assert "new@example.com" not in dumped
        assert "Updated Name" not in dumped

    def test_create_and_delete_are_audited(self, monkeypatch, fresh_audit_trail):
        from app.schemas.candidate import CandidateCreate

        connection = install_candidate_connection(monkeypatch, [CANDIDATE])
        candidate_service.create_candidate(
            TEST_USER_ID,
            CandidateCreate(full_name="New Person", email="new.person@example.com"),
        )
        assert fresh_audit_trail.recent()[-1]["event_type"] == "candidate_created"

        connection2 = install_candidate_connection(monkeypatch, [True])
        assert candidate_service.delete_candidate(TEST_USER_ID, CANDIDATE_ID) is True
        assert fresh_audit_trail.recent()[-1]["event_type"] == "candidate_deleted"
        assert fresh_audit_trail.recent()[-1]["resource_id"] == CANDIDATE_ID
        assert fresh_audit_trail.recent()[-1]["user_id"] == TEST_USER_ID

    def test_failed_delete_is_not_audited(self, monkeypatch, fresh_audit_trail):
        install_candidate_connection(monkeypatch, [None])

        assert candidate_service.delete_candidate(TEST_USER_ID, CANDIDATE_ID) is False
        assert fresh_audit_trail.recent() == []


class TestRetention:
    def test_retention_disabled_by_default(
        self, clear_retention_env, fake_store, monkeypatch, fresh_audit_trail
    ):
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        install_privacy_connection(monkeypatch, [])

        summary = privacy_service.expired_summary(TEST_USER_ID)

        assert summary["expired"] == {
            "chat_messages": 0,
            "candidates": 0,
            "documents": 0,
        }
        assert all(
            policy["days"] == 0 for policy in summary["policies"].values()
        )

        result = privacy_service.cleanup_expired(TEST_USER_ID)
        assert result["deleted"] == {
            "chat_messages": 0,
            "documents": 0,
            "candidates": 0,
        }
        assert "doc-old" in fake_store.documents
        assert fake_store.deleted == []
        assert fresh_audit_trail.recent()[-1]["event_type"] == "retention_cleanup"

    def test_expired_records_are_identified_safely(
        self, clear_retention_env, fake_store, monkeypatch
    ):
        clear_retention_env.setenv("RETENTION_CHAT_MESSAGES_DAYS", "30")
        clear_retention_env.setenv("RETENTION_DOCUMENTS_DAYS", "90")
        clear_retention_env.setenv("RETENTION_CANDIDATES_DAYS", "180")
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        connection = install_privacy_connection(monkeypatch, [[MESSAGE], [CANDIDATE]])

        summary = privacy_service.expired_summary(TEST_USER_ID)

        assert summary["expired"]["chat_messages"] == 1
        assert summary["expired"]["candidates"] == 1
        assert summary["expired"]["documents"] == 1
        sql, params = connection.cursor_instance.executed[0]
        assert "created_at < %s" in sql
        assert params[0] == TEST_USER_ID

    def test_cleanup_deletes_only_expired_owner_records(
        self, clear_retention_env, fake_store, monkeypatch, fresh_audit_trail
    ):
        clear_retention_env.setenv("RETENTION_CHAT_MESSAGES_DAYS", "30")
        clear_retention_env.setenv("RETENTION_DOCUMENTS_DAYS", "90")
        clear_retention_env.setenv("RETENTION_CANDIDATES_DAYS", "180")
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        fake_store.documents["doc-new"] = dict(NEW_DOC)
        fake_store.documents["doc-other-owner"] = dict(
            OLD_DOC, owner_user_id=OTHER_USER_ID
        )
        connection = install_privacy_connection(monkeypatch, [[1, 2], [1]])

        result = privacy_service.cleanup_expired(TEST_USER_ID)

        assert result["deleted"]["chat_messages"] == 2
        assert result["deleted"]["candidates"] == 1
        assert result["deleted"]["documents"] == 1
        assert fake_store.deleted == ["doc-old"]
        assert "doc-new" in fake_store.documents
        assert "doc-other-owner" in fake_store.documents
        assert result["warnings"] == []

        executed = connection.cursor_instance.executed
        assert any("DELETE FROM chat_messages" in sql for sql, _ in executed)
        assert any("DELETE FROM candidates" in sql for sql, _ in executed)
        assert all(params[0] == TEST_USER_ID for _, params in executed)

        event = fresh_audit_trail.recent()[-1]
        assert event["event_type"] == "retention_cleanup"
        assert event["user_id"] == TEST_USER_ID
        assert event["status"] == "success"

    def test_cleanup_survives_document_deletion_failures(
        self, clear_retention_env, fake_store, monkeypatch, fresh_audit_trail
    ):
        clear_retention_env.setenv("RETENTION_DOCUMENTS_DAYS", "30")
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        fake_store.documents["doc-broken"] = dict(OLD_DOC, document_id="doc-broken")
        fake_store.error_ids.add("doc-broken")
        install_privacy_connection(monkeypatch, [])

        result = privacy_service.cleanup_expired(TEST_USER_ID)

        assert result["deleted"]["documents"] == 1
        assert len(result["warnings"]) == 1
        assert "doc-broken" in result["warnings"][0]
        assert fresh_audit_trail.recent()[-1]["status"] == "success"
        assert "warnings=1" in fresh_audit_trail.recent()[-1]["detail"]

    def test_invalid_retention_configuration_is_rejected(
        self, clear_retention_env, monkeypatch
    ):
        clear_retention_env.setenv("RETENTION_CHAT_MESSAGES_DAYS", "-5")

        with pytest.raises(privacy_service.RetentionConfigError):
            privacy_service.expired_summary(TEST_USER_ID)

        clear_retention_env.setenv("RETENTION_CHAT_MESSAGES_DAYS", "soon")

        with pytest.raises(privacy_service.RetentionConfigError):
            privacy_service.cleanup_expired(TEST_USER_ID)

    def test_retention_endpoint_requires_authentication(self):
        with TestClient(app) as anonymous:
            assert anonymous.get("/api/privacy/retention").status_code == 401
            assert (
                anonymous.post("/api/privacy/retention/cleanup").status_code == 401
            )


class TestDataExport:
    def test_export_returns_all_owned_data(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        connection = install_privacy_connection(
            monkeypatch, [[JOB], [CANDIDATE], [CONSENT_GRANTED], [SESSION], [MESSAGE]]
        )

        export = privacy_service.export_owner_data(TEST_USER_ID)

        assert export["counts"] == {
            "jobs": 1,
            "candidates": 1,
            "consents": 1,
            "chat_sessions": 1,
            "chat_messages": 1,
            "documents": 1,
        }
        assert export["jobs"][0]["id"] == JOB_ID
        assert export["candidates"][0]["resume_text"] == "Senior python developer."
        assert export["consents"][0]["status"] == "granted"
        assert export["chat_sessions"][0]["messages"][0]["id"] == MESSAGE_ID
        assert export["documents"][0]["document_id"] == "doc-old"

        for sql, params in connection.cursor_instance.executed:
            assert params[-1] == TEST_USER_ID

        event = fresh_audit_trail.recent()[-1]
        assert event["event_type"] == "data_exported"
        assert event["user_id"] == TEST_USER_ID

    def test_export_audit_does_not_contain_personal_content(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        install_privacy_connection(
            monkeypatch, [[JOB], [CANDIDATE], [CONSENT_GRANTED], [SESSION], [MESSAGE]]
        )

        privacy_service.export_owner_data(TEST_USER_ID)

        dumped = "\n".join(str(event) for event in fresh_audit_trail.recent())
        assert "jane.candidate@example.com" not in dumped
        assert "Jane Candidate" not in dumped
        assert "Senior python developer." not in dumped
        assert "Hello" not in dumped

    def test_export_endpoint_requires_authentication(self):
        with TestClient(app) as anonymous:
            assert anonymous.get("/api/privacy/export").status_code == 401


class TestAccountDataDeletion:
    def test_deletion_removes_files_then_rows(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        connection = install_privacy_connection(
            monkeypatch, [[1], [1, 2], [1, 2, 3], [1]]
        )

        result = privacy_service.delete_account_data(TEST_USER_ID)

        assert result["deleted"] == {
            "documents": 1,
            "consents": 1,
            "candidates": 2,
            "jobs": 3,
            "chat_sessions": 1,
        }
        assert result["warnings"] == []
        assert fake_store.deleted == ["doc-old"]
        assert fake_store.documents == {}

        executed = connection.cursor_instance.executed
        assert "DELETE FROM candidate_consents" in executed[0][0]
        assert "DELETE FROM candidates" in executed[1][0]
        assert "DELETE FROM jobs" in executed[2][0]
        assert "DELETE FROM chat_sessions" in executed[3][0]
        assert all(params[0] == TEST_USER_ID for _, params in executed)

        event = fresh_audit_trail.recent()[-1]
        assert event["event_type"] == "account_data_deleted"
        assert event["user_id"] == TEST_USER_ID
        assert event["status"] == "success"

    def test_supabase_account_is_never_deleted(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        install_privacy_connection(monkeypatch, [0, 0, 0, 0])

        result = privacy_service.delete_account_data(TEST_USER_ID)

        assert result["supabase_account"].startswith("not_deleted")

    def test_partial_document_failure_is_reported_as_warning(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        fake_store.documents["doc-broken"] = dict(OLD_DOC, document_id="doc-broken")
        fake_store.error_ids.add("doc-broken")
        install_privacy_connection(monkeypatch, [0, 0, 0, 0])

        result = privacy_service.delete_account_data(TEST_USER_ID)

        assert result["deleted"]["documents"] == 1
        assert len(result["warnings"]) == 1
        assert "doc-broken" in result["warnings"][0]
        assert fresh_audit_trail.recent()[-1]["status"] == "failure"
        assert "warnings=1" in fresh_audit_trail.recent()[-1]["detail"]

    def test_document_store_failure_does_not_stop_database_deletion(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        def broken_store():
            raise OSError("storage offline")

        monkeypatch.setattr(privacy_service, "get_document_store", broken_store)
        monkeypatch.setattr(privacy_service, "get_response_cache", lambda: FakeCache())
        connection = install_privacy_connection(
            monkeypatch, [[1], [1], [1], [1]]
        )

        result = privacy_service.delete_account_data(TEST_USER_ID)

        assert result["deleted"]["documents"] == 0
        assert result["deleted"]["candidates"] == 1
        assert any("document store" in warning for warning in result["warnings"])
        assert fresh_audit_trail.recent()[-1]["status"] == "failure"

    def test_deletion_is_owner_scoped(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        fake_store.documents["doc-other-owner"] = dict(
            OLD_DOC, owner_user_id=OTHER_USER_ID
        )
        install_privacy_connection(monkeypatch, [0, 0, 0, 0])

        privacy_service.delete_account_data(TEST_USER_ID)

        assert "doc-other-owner" in fake_store.documents
        assert fake_store.deleted == []

    def test_deletion_endpoint_requires_authentication(self):
        with TestClient(app) as anonymous:
            assert anonymous.delete("/api/privacy/account-data").status_code == 401


class TestResumeReplacement:
    def _save_resume(self, monkeypatch, store, candidate_row=CANDIDATE):
        install_rag_connection(monkeypatch, [candidate_row])

        return asyncio.run(
            rag_service.save_document(
                TEST_USER_ID,
                filename="new-resume.pdf",
                data=b"resume bytes",
                source_type="resume",
                candidate_id=CANDIDATE_ID,
            )
        )

    def test_replacement_removes_obsolete_resume_files(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        fake_store.documents["doc-old"] = dict(OLD_DOC)
        fake_store.documents["doc-job"] = dict(OTHER_DOC)
        monkeypatch.setattr(
            rag_service,
            "get_document_store",
            lambda: _SavingStore(fake_store),
        )

        record = self._save_resume(monkeypatch, fake_store)

        assert record["document_id"] == "doc-uploaded"
        assert "doc-old" not in fake_store.documents
        assert "doc-job" in fake_store.documents
        assert fresh_audit_trail.recent()[-1]["event_type"] == "document_deleted"
        assert fresh_audit_trail.recent()[-1]["detail"] == "resume_replaced"
        assert fresh_audit_trail.recent()[-1]["resource_id"] == "doc-old"

    def test_replacement_keeps_documents_with_same_content_hash(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        fake_store.documents["doc-old"] = dict(OLD_DOC, content_hash="hash-new")
        monkeypatch.setattr(
            rag_service,
            "get_document_store",
            lambda: _SavingStore(fake_store),
        )

        self._save_resume(monkeypatch, fake_store)

        assert "doc-old" in fake_store.documents
        assert fake_store.deleted == []
        assert all(
            event.get("detail") != "resume_replaced"
            for event in fresh_audit_trail.recent()
        )

    def test_replacement_failure_does_not_break_upload(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        class ExplodingStore(_SavingStore):
            def list_documents(self, owner_user_id):
                raise OSError("listing failed")

        fake_store.documents["doc-old"] = dict(OLD_DOC)
        monkeypatch.setattr(
            rag_service, "get_document_store", lambda: ExplodingStore(fake_store)
        )

        record = self._save_resume(monkeypatch, fake_store)

        assert record["document_id"] == "doc-uploaded"
        assert fresh_audit_trail.recent()[-1]["event_type"] == "document_uploaded"


class _SavingStore(FakeDocumentStore):
    def __init__(self, base):
        super().__init__(list(base.documents.values()))
        self.base = base

    def delete_document(self, owner_user_id, document_id):
        removed = super().delete_document(owner_user_id, document_id)
        if removed:
            self.base.documents.pop(document_id, None)
            self.base.deleted.append(document_id)
        return removed


class TestExistingChatFeaturesRemainIntact:
    def test_clear_all_chat_history_still_works(
        self, client, monkeypatch, fresh_audit_trail
    ):
        connection = FakeConnection([[1, 2]])

        @contextmanager
        def fake_get_connection():
            yield connection

        monkeypatch.setattr(chat_service, "get_connection", fake_get_connection)

        response = client.delete("/api/chat/sessions")

        assert response.status_code == 200
        assert response.json() == {"deleted": 2}
        sql, params = connection.cursor_instance.executed[0]
        assert sql.startswith("DELETE FROM chat_sessions")
        assert params == (TEST_USER_ID,)
        assert fresh_audit_trail.recent()[-1]["event_type"] == "chat_history_cleared"

    def test_chat_export_remains_client_side_only(self, client):
        response = client.get("/openapi.json")
        paths = response.json()["paths"]
        chat_paths = [path for path in paths if path.startswith("/api/chat")]

        assert "/api/chat/sessions" in chat_paths
        assert "get" in paths["/api/chat/sessions"]
        assert not any(path.endswith("/export") for path in chat_paths)

    def test_privacy_events_do_not_leak_secrets_into_audit(
        self, fake_store, monkeypatch, fresh_audit_trail
    ):
        install_privacy_connection(
            monkeypatch, [[JOB], [CANDIDATE], [CONSENT_GRANTED], [SESSION], [MESSAGE]]
        )
        privacy_service.export_owner_data(TEST_USER_ID)
        privacy_service.delete_account_data(TEST_USER_ID)

        dumped = "\n".join(str(event) for event in fresh_audit_trail.recent())
        assert "jane.candidate@example.com" not in dumped
        assert "+1-555-0100" not in dumped
        assert "Senior python developer." not in dumped
        assert "Bearer" not in dumped
        assert fresh_audit_trail.recent()
