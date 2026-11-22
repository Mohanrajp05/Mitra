
from contextlib import contextmanager

import pytest
from psycopg.types.json import Jsonb

from app.rag.llm import LLMError
from app.rag.pipeline import PipelineResult
from app.schemas.chat import ChatMessageCreate, ChatSessionRename
from app.services import chat_service
from app.services.chat_service import SessionNotFoundError
from tests.conftest import TEST_USER_ID

OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
USER_MESSAGE_ID = "11111111-2222-4333-8444-555555555555"
ASSISTANT_MESSAGE_ID = "66666666-7777-4888-8999-000000000000"

SESSION = {
    "id": SESSION_ID,
    "owner_user_id": TEST_USER_ID,
    "title": "New conversation",
    "created_at": "2026-11-14T10:00:00Z",
    "updated_at": "2026-11-14T10:00:00Z",
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
    "sources": [],
    "has_evidence": True,
    "created_at": "2026-11-14T10:01:05Z",
}


class FakeCursor:
    def __init__(self, results):
        self.results = list(results)
        self.executed = []
        self._current = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._current = self.results.pop(0) if self.results else None

    def fetchone(self):
        return self._current

    def fetchall(self):
        return list(self._current or [])

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConnection:
    def __init__(self, results):
        self.cursor_instance = FakeCursor(results)

    def cursor(self):
        return self.cursor_instance


def install_connection(monkeypatch, results):
    connection = FakeConnection(results)

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(chat_service, "get_connection", fake_get_connection)
    return connection


def test_create_session_uses_default_title(monkeypatch):
    connection = install_connection(monkeypatch, [[], SESSION])

    session = chat_service.create_session(TEST_USER_ID)

    assert session == SESSION
    sql, params = connection.cursor_instance.executed[-1]
    assert "INSERT INTO chat_sessions" in sql
    assert params == (TEST_USER_ID, "New conversation")


def test_create_session_uses_custom_title(monkeypatch):
    from app.schemas.chat import ChatSessionCreate

    connection = install_connection(
        monkeypatch, [[], {**SESSION, "title": "Shortlist"}]
    )

    chat_service.create_session(TEST_USER_ID, ChatSessionCreate(title=" Shortlist "))

    _, params = connection.cursor_instance.executed[-1]
    assert params == (TEST_USER_ID, "Shortlist")


def test_create_session_raises_when_limit_reached_without_deleting(monkeypatch):
    older = {
        "id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "owner_user_id": TEST_USER_ID,
        "title": "Older chat",
        "created_at": "2026-11-13T10:00:00Z",
        "updated_at": "2026-11-13T10:00:00Z",
    }
    newer = {
        "id": "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff",
        "owner_user_id": TEST_USER_ID,
        "title": "Newer chat",
        "created_at": "2026-11-14T10:00:00Z",
        "updated_at": "2026-11-14T10:00:00Z",
    }
    monkeypatch.setattr(chat_service, "MAX_CHAT_SESSIONS_PER_USER", 2)
    connection = install_connection(monkeypatch, [[older, newer]])

    with pytest.raises(chat_service.ChatLimitExceededError):
        chat_service.create_session(TEST_USER_ID)

    executed = connection.cursor_instance.executed
    assert len(executed) == 1
    sql, params = executed[0]
    assert "SELECT" in sql
    assert "DELETE FROM chat_sessions" not in sql
    assert "INSERT INTO chat_sessions" not in sql
    assert params == (TEST_USER_ID,)


def test_create_session_allows_creation_below_limit(monkeypatch):
    existing = [
        {
            "id": f"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeee{index:02d}",
            "owner_user_id": TEST_USER_ID,
            "title": f"Chat {index}",
            "created_at": f"2026-11-1{index}T10:00:00Z",
            "updated_at": f"2026-11-1{index}T10:00:00Z",
        }
        for index in range(9)
    ]
    monkeypatch.setattr(chat_service, "MAX_CHAT_SESSIONS_PER_USER", 10)
    connection = install_connection(monkeypatch, [existing, SESSION])

    session = chat_service.create_session(TEST_USER_ID)

    assert session == SESSION
    insert_calls = [
        params for sql, params in connection.cursor_instance.executed if "INSERT INTO chat_sessions" in sql
    ]
    assert insert_calls == [(TEST_USER_ID, "New conversation")]


def test_rename_session_raises_when_not_owned(monkeypatch):
    install_connection(monkeypatch, [None])

    with pytest.raises(SessionNotFoundError):
        chat_service.rename_session(
            TEST_USER_ID, SESSION_ID, ChatSessionRename(title="Hijacked")
        )


def test_rename_session_rejects_invalid_id_without_database(monkeypatch):
    def fail():
        raise AssertionError("database must not be queried")

    monkeypatch.setattr(chat_service, "get_connection", fail)

    with pytest.raises(SessionNotFoundError):
        chat_service.rename_session(
            TEST_USER_ID, "not-a-uuid", ChatSessionRename(title="Hijacked")
        )


def test_delete_session_raises_when_not_owned(monkeypatch):
    install_connection(monkeypatch, [None])

    with pytest.raises(SessionNotFoundError):
        chat_service.delete_session(OTHER_USER_ID, SESSION_ID)


def test_delete_all_sessions_is_owner_scoped(monkeypatch):
    connection = install_connection(
        monkeypatch, [[{"id": "a"}, {"id": "b"}, {"id": "c"}]]
    )

    deleted = chat_service.delete_all_sessions(TEST_USER_ID)

    assert deleted == 3
    sql, params = connection.cursor_instance.executed[0]
    assert "DELETE FROM chat_sessions" in sql
    assert "owner_user_id = %s" in sql
    assert "chat_messages" not in sql
    assert params == (TEST_USER_ID,)


def test_delete_all_sessions_returns_zero_when_empty(monkeypatch):
    connection = install_connection(monkeypatch, [[]])

    assert chat_service.delete_all_sessions(TEST_USER_ID) == 0
    _, params = connection.cursor_instance.executed[0]
    assert params == (TEST_USER_ID,)


def test_list_messages_raises_when_session_not_owned(monkeypatch):
    connection = install_connection(monkeypatch, [None])

    with pytest.raises(SessionNotFoundError):
        chat_service.list_messages(OTHER_USER_ID, SESSION_ID)

    assert len(connection.cursor_instance.executed) == 1


def test_list_messages_is_owner_scoped_and_chronological(monkeypatch):
    connection = install_connection(
        monkeypatch, [SESSION, [USER_MESSAGE, ASSISTANT_MESSAGE]]
    )

    messages = chat_service.list_messages(TEST_USER_ID, SESSION_ID)

    assert [message["role"] for message in messages] == ["user", "assistant"]
    sql, params = connection.cursor_instance.executed[1]
    assert "owner_user_id = %s" in sql
    assert "ORDER BY created_at ASC" in sql
    assert params == (SESSION_ID, TEST_USER_ID)


def test_persist_exchange_inserts_both_messages_and_touches_session(monkeypatch):
    connection = install_connection(
        monkeypatch, [SESSION, USER_MESSAGE, ASSISTANT_MESSAGE, None]
    )
    result = PipelineResult(
        query="Who has Python experience?",
        answer="Jane Doe has Python experience.",
        has_evidence=True,
        sources=[
            {
                "document_id": "doc-1",
                "chunk_id": "doc-1-0",
                "chunk_index": 0,
                "score": 0.82,
                "source_type": "resume",
                "filename": "resume.pdf",
            }
        ],
    )

    exchange = chat_service._persist_exchange(
        TEST_USER_ID, SESSION_ID, "Who has Python experience?", result
    )

    assert exchange == {
        "user_message": USER_MESSAGE,
        "assistant_message": ASSISTANT_MESSAGE,
    }
    executed = connection.cursor_instance.executed
    assert len(executed) == 4
    assert "SELECT" in executed[0][0]
    assert "INSERT INTO chat_messages" in executed[1][0]
    assert executed[1][1][2] == "user"
    assert "INSERT INTO chat_messages" in executed[2][0]
    assert executed[2][1][2] == "assistant"
    assert isinstance(executed[2][1][4], Jsonb)
    assert executed[2][1][4].obj[0]["filename"] == "resume.pdf"
    assert "UPDATE chat_sessions SET updated_at" in executed[3][0]


def test_persist_exchange_writes_nothing_when_session_missing(monkeypatch):
    connection = install_connection(monkeypatch, [None])
    result = PipelineResult(
        query="Hello",
        answer="Hello",
        has_evidence=False,
        sources=[],
    )

    with pytest.raises(SessionNotFoundError):
        chat_service._persist_exchange(TEST_USER_ID, SESSION_ID, "Hello", result)

    assert len(connection.cursor_instance.executed) == 1


@pytest.mark.asyncio
async def test_send_message_queries_then_persists(monkeypatch):
    events = []
    result = PipelineResult(
        query="Who has Python experience?",
        answer="Jane Doe has Python experience.",
        has_evidence=True,
        sources=[],
    )
    exchange = {
        "user_message": USER_MESSAGE,
        "assistant_message": ASSISTANT_MESSAGE,
    }

    monkeypatch.setattr(
        chat_service, "_check_session", lambda owner, session: events.append("check")
    )

    async def fake_query(owner_user_id, content):
        events.append("query")
        assert owner_user_id == TEST_USER_ID
        assert content == "Who has Python experience?"
        return result

    monkeypatch.setattr(chat_service.rag_service, "query", fake_query)

    def fake_persist(owner_user_id, session_id, content, pipeline_result):
        events.append("persist")
        assert pipeline_result is result
        return exchange

    monkeypatch.setattr(chat_service, "_persist_exchange", fake_persist)

    response = await chat_service.send_message(
        TEST_USER_ID,
        SESSION_ID,
        ChatMessageCreate(content="Who has Python experience?"),
    )

    assert events == ["check", "query", "persist"]
    assert response == exchange


@pytest.mark.asyncio
async def test_send_message_does_not_persist_when_llm_fails(monkeypatch):
    events = []
    monkeypatch.setattr(
        chat_service, "_check_session", lambda owner, session: events.append("check")
    )

    async def failing_query(owner_user_id, content):
        events.append("query")
        raise LLMError("The AI service request failed.")

    monkeypatch.setattr(chat_service.rag_service, "query", failing_query)
    monkeypatch.setattr(
        chat_service, "_persist_exchange", lambda *args: events.append("persist")
    )

    with pytest.raises(LLMError):
        await chat_service.send_message(
            TEST_USER_ID,
            SESSION_ID,
            ChatMessageCreate(content="Who has Python experience?"),
        )

    assert events == ["check", "query"]


@pytest.mark.asyncio
async def test_send_message_rejects_invalid_session_id(monkeypatch):
    def fail():
        raise AssertionError("database must not be queried")

    monkeypatch.setattr(chat_service, "get_connection", fail)

    with pytest.raises(SessionNotFoundError):
        await chat_service.send_message(
            TEST_USER_ID, "not-a-uuid", ChatMessageCreate(content="Hello")
        )
