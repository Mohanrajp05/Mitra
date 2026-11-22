"""Tests for chat session and message routes, validation, and ownership."""

from app.api import chat as chat_api
from app.api import rag as rag_api
from app.main import app
from app.rag.llm import LLMError, LLMNotConfiguredError
from app.services.chat_service import SessionNotFoundError
from tests.conftest import TEST_USER_ID

OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
OTHER_SESSION_ID = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
USER_MESSAGE_ID = "11111111-2222-4333-8444-555555555555"
ASSISTANT_MESSAGE_ID = "66666666-7777-4888-8999-000000000000"

SESSION = {
    "id": SESSION_ID,
    "owner_user_id": TEST_USER_ID,
    "title": "New conversation",
    "created_at": "2026-11-14T10:00:00Z",
    "updated_at": "2026-11-14T10:00:00Z",
}

SOURCE = {
    "document_id": "doc-1",
    "chunk_id": "doc-1-0",
    "chunk_index": 0,
    "score": 0.82,
    "source_type": "resume",
    "filename": "resume.pdf",
}

USER_MESSAGE = {
    "id": USER_MESSAGE_ID,
    "session_id": SESSION_ID,
    "owner_user_id": TEST_USER_ID,
    "role": "user",
    "content": "Who has Python experience?",
    "sources": [],
    "has_evidence": True,
    "created_at": "2026-11-14T10:01:00Z",
}

ASSISTANT_MESSAGE = {
    "id": ASSISTANT_MESSAGE_ID,
    "session_id": SESSION_ID,
    "owner_user_id": TEST_USER_ID,
    "role": "assistant",
    "content": "Jane Doe has Python experience.",
    "sources": [SOURCE],
    "has_evidence": True,
    "created_at": "2026-11-14T10:01:05Z",
}


def test_create_session_uses_authenticated_owner(client, monkeypatch):
    seen = {}

    def fake_create(owner_user_id, payload):
        seen["owner"] = owner_user_id
        seen["payload"] = payload
        return SESSION

    monkeypatch.setattr(chat_api.chat_service, "create_session", fake_create)

    response = client.post("/api/chat/sessions", json={})

    assert response.status_code == 201
    assert seen["owner"] == TEST_USER_ID
    assert seen["payload"].title is None
    assert response.json()["owner_user_id"] == TEST_USER_ID
    assert response.json()["title"] == "New conversation"


def test_create_session_without_body(client, monkeypatch):
    monkeypatch.setattr(
        chat_api.chat_service, "create_session", lambda owner, payload: SESSION
    )

    response = client.post("/api/chat/sessions")

    assert response.status_code == 201
    assert response.json()["id"] == SESSION_ID


def test_create_session_accepts_custom_title(client, monkeypatch):
    seen = {}

    def fake_create(owner_user_id, payload):
        seen["title"] = payload.title
        return {**SESSION, "title": payload.title}

    monkeypatch.setattr(chat_api.chat_service, "create_session", fake_create)

    response = client.post("/api/chat/sessions", json={"title": "Python hiring"})

    assert response.status_code == 201
    assert seen["title"] == "Python hiring"
    assert response.json()["title"] == "Python hiring"


def test_create_session_rejects_client_supplied_owner(client):
    response = client.post(
        "/api/chat/sessions", json={"owner_user_id": OTHER_USER_ID}
    )

    assert response.status_code == 422


def test_create_session_returns_limit_error_when_limit_reached(client, monkeypatch):
    from app.services.chat_service import ChatLimitExceededError

    def failing_create(owner_user_id, payload):
        raise ChatLimitExceededError(
            "You have reached the maximum limit of 10 chat conversations "
            "for your account. You cannot create a new conversation right now."
        )

    monkeypatch.setattr(chat_api.chat_service, "create_session", failing_create)

    response = client.post("/api/chat/sessions", json={})

    assert response.status_code == 429
    assert "maximum limit" in response.json()["detail"]


def test_list_sessions_is_owner_scoped(client, monkeypatch):
    seen = {}

    def fake_list(owner_user_id):
        seen["owner"] = owner_user_id
        return [SESSION]

    monkeypatch.setattr(chat_api.chat_service, "list_sessions", fake_list)

    response = client.get("/api/chat/sessions")

    assert response.status_code == 200
    assert seen["owner"] == TEST_USER_ID
    assert response.json()[0]["id"] == SESSION_ID


def test_rename_session(client, monkeypatch):
    seen = {}

    def fake_rename(owner_user_id, session_id, payload):
        seen["owner"] = owner_user_id
        seen["session_id"] = session_id
        seen["title"] = payload.title
        return {**SESSION, "title": payload.title}

    monkeypatch.setattr(chat_api.chat_service, "rename_session", fake_rename)

    response = client.patch(
        f"/api/chat/sessions/{SESSION_ID}", json={"title": "Shortlisted"}
    )

    assert response.status_code == 200
    assert seen == {
        "owner": TEST_USER_ID,
        "session_id": SESSION_ID,
        "title": "Shortlisted",
    }
    assert response.json()["title"] == "Shortlisted"


def test_rename_session_rejects_empty_title(client):
    response = client.patch(
        f"/api/chat/sessions/{SESSION_ID}", json={"title": "   "}
    )

    assert response.status_code == 422


def test_rename_other_users_session_returns_404(client, monkeypatch):
    def fake_rename(owner_user_id, session_id, payload):
        raise SessionNotFoundError("Chat session not found.")

    monkeypatch.setattr(chat_api.chat_service, "rename_session", fake_rename)

    response = client.patch(
        f"/api/chat/sessions/{OTHER_SESSION_ID}", json={"title": "Hijacked"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat session not found."


def test_delete_session_returns_204(client, monkeypatch):
    seen = {}

    def fake_delete(owner_user_id, session_id):
        seen["owner"] = owner_user_id
        seen["session_id"] = session_id

    monkeypatch.setattr(chat_api.chat_service, "delete_session", fake_delete)

    response = client.delete(f"/api/chat/sessions/{SESSION_ID}")

    assert response.status_code == 204
    assert seen == {"owner": TEST_USER_ID, "session_id": SESSION_ID}


def test_delete_other_users_session_returns_404(client, monkeypatch):
    def fake_delete(owner_user_id, session_id):
        raise SessionNotFoundError("Chat session not found.")

    monkeypatch.setattr(chat_api.chat_service, "delete_session", fake_delete)

    response = client.delete(f"/api/chat/sessions/{OTHER_SESSION_ID}")

    assert response.status_code == 404


def test_delete_all_sessions_is_owner_scoped(client, monkeypatch):
    seen = {}

    def fake_delete_all(owner_user_id):
        seen["owner"] = owner_user_id
        return 3

    monkeypatch.setattr(
        chat_api.chat_service, "delete_all_sessions", fake_delete_all
    )

    response = client.delete("/api/chat/sessions")

    assert response.status_code == 200
    assert seen == {"owner": TEST_USER_ID}
    assert response.json() == {"deleted": 3}


def test_delete_all_sessions_returns_zero_for_empty_history(client, monkeypatch):
    monkeypatch.setattr(
        chat_api.chat_service, "delete_all_sessions", lambda owner: 0
    )

    response = client.delete("/api/chat/sessions")

    assert response.status_code == 200
    assert response.json() == {"deleted": 0}


def test_delete_all_sessions_ignores_client_supplied_owner(client, monkeypatch):
    seen = {}

    def fake_delete_all(owner_user_id):
        seen["owner"] = owner_user_id
        return 1

    monkeypatch.setattr(
        chat_api.chat_service, "delete_all_sessions", fake_delete_all
    )

    response = client.request(
        "DELETE",
        "/api/chat/sessions",
        json={"owner_user_id": OTHER_USER_ID},
    )

    assert response.status_code == 200
    assert seen == {"owner": TEST_USER_ID}


def test_list_messages_returns_chronological_order(client, monkeypatch):
    seen = {}

    def fake_list(owner_user_id, session_id):
        seen["owner"] = owner_user_id
        seen["session_id"] = session_id
        return [USER_MESSAGE, ASSISTANT_MESSAGE]

    monkeypatch.setattr(chat_api.chat_service, "list_messages", fake_list)

    response = client.get(f"/api/chat/sessions/{SESSION_ID}/messages")

    assert response.status_code == 200
    assert seen == {"owner": TEST_USER_ID, "session_id": SESSION_ID}
    roles = [message["role"] for message in response.json()]
    assert roles == ["user", "assistant"]


def test_list_messages_for_other_users_session_returns_404(client, monkeypatch):
    def fake_list(owner_user_id, session_id):
        raise SessionNotFoundError("Chat session not found.")

    monkeypatch.setattr(chat_api.chat_service, "list_messages", fake_list)

    response = client.get(f"/api/chat/sessions/{OTHER_SESSION_ID}/messages")

    assert response.status_code == 404


def test_send_message_returns_both_messages(client, monkeypatch):
    seen = {}

    async def fake_send(owner_user_id, session_id, payload):
        seen["owner"] = owner_user_id
        seen["session_id"] = session_id
        seen["content"] = payload.content
        return {
            "user_message": USER_MESSAGE,
            "assistant_message": ASSISTANT_MESSAGE,
        }

    monkeypatch.setattr(chat_api.chat_service, "send_message", fake_send)

    response = client.post(
        f"/api/chat/sessions/{SESSION_ID}/messages",
        json={"content": "Who has Python experience?"},
    )

    assert response.status_code == 200
    assert seen == {
        "owner": TEST_USER_ID,
        "session_id": SESSION_ID,
        "content": "Who has Python experience?",
    }
    body = response.json()
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["sources"][0]["filename"] == "resume.pdf"


def test_send_message_rejects_empty_content(client):
    response = client.post(
        f"/api/chat/sessions/{SESSION_ID}/messages", json={"content": "   "}
    )

    assert response.status_code == 422


def test_send_message_rejects_oversized_content(client):
    response = client.post(
        f"/api/chat/sessions/{SESSION_ID}/messages",
        json={"content": "a" * 4_001},
    )

    assert response.status_code == 422


def test_send_message_rejects_client_supplied_owner(client):
    response = client.post(
        f"/api/chat/sessions/{SESSION_ID}/messages",
        json={"content": "Hello", "owner_user_id": OTHER_USER_ID},
    )

    assert response.status_code == 422


def test_send_message_llm_failure_returns_safe_502(client, monkeypatch):
    async def fake_send(owner_user_id, session_id, payload):
        raise LLMError("The AI service request failed.")

    monkeypatch.setattr(chat_api.chat_service, "send_message", fake_send)

    response = client.post(
        f"/api/chat/sessions/{SESSION_ID}/messages", json={"content": "Hello"}
    )

    assert response.status_code == 502
    assert "traceback" not in response.text.lower()


def test_send_message_not_configured_returns_503(client, monkeypatch):
    async def fake_send(owner_user_id, session_id, payload):
        raise LLMNotConfiguredError("PORTKEY_AI_API is not set.")

    monkeypatch.setattr(chat_api.chat_service, "send_message", fake_send)

    response = client.post(
        f"/api/chat/sessions/{SESSION_ID}/messages", json={"content": "Hello"}
    )

    assert response.status_code == 503
    assert "PORTKEY_AI_API" not in response.text


def test_chat_routes_are_registered():
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert ("GET", "/api/chat/sessions") in routes
    assert ("POST", "/api/chat/sessions") in routes
    assert ("DELETE", "/api/chat/sessions") in routes
    assert ("PATCH", "/api/chat/sessions/{session_id}") in routes
    assert ("DELETE", "/api/chat/sessions/{session_id}") in routes
    assert ("GET", "/api/chat/sessions/{session_id}/messages") in routes
    assert ("POST", "/api/chat/sessions/{session_id}/messages") in routes


def test_existing_rag_endpoints_still_work(client, monkeypatch):
    async def fake_list(owner_user_id):
        return []

    monkeypatch.setattr(rag_api.rag_service, "list_documents", fake_list)

    response = client.get("/api/rag/documents")

    assert response.status_code == 200
    assert response.json() == {"documents": [], "total": 0}


def test_cors_allows_patch_for_session_rename(client):
    from app.core.config import settings

    response = client.options(
        f"/api/chat/sessions/{SESSION_ID}",
        headers={
            "Origin": settings.allowed_origins[0],
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_migration_is_non_destructive():
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[2]
        / "database"
        / "migrations"
        / "001_chat_sessions_and_messages.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS chat_sessions" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_messages" in migration
    assert "ON DELETE CASCADE" in migration
    assert "idx_chat_sessions_owner_updated" in migration
    assert "idx_chat_messages_session_created" in migration
    assert "DROP TABLE" not in migration.upper()
    assert "ALTER TABLE JOBS" not in migration.upper()
    assert "ALTER TABLE CANDIDATES" not in migration.upper()
