import pytest

from app.rag.retriever import Retriever, get_retriever, reset_retriever
from app.rag.vector_store import LocalVectorStore
from tests.rag_helpers import FakeEmbeddingService, make_settings

OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"
CANDIDATE_A = "33333333-3333-4333-8333-333333333333"

RESUME_TEXT = (
    b"Jane Doe\n\n"
    b"Python developer with FastAPI, PostgreSQL and Docker experience.\n\n"
    b"Skills: Python, FastAPI, PostgreSQL, Docker."
)

GUIDE_TEXT = (
    b"Recruitment guide.\n\n"
    b"Confirm availability before scheduling an interview with a candidate."
)


@pytest.fixture
def retriever(rag_dir):
    settings = make_settings(rag_dir)
    store = LocalVectorStore(settings, FakeEmbeddingService(8))
    return Retriever(store=store, settings=settings)


def ingest(retriever, owner=OWNER_A):
    retriever.store.save_document(
        owner,
        filename="resume.txt",
        data=RESUME_TEXT,
        source_type="resume",
        candidate_id=CANDIDATE_A,
    )
    retriever.store.save_document(
        owner,
        filename="guide.txt",
        data=GUIDE_TEXT,
        source_type="knowledge",
    )


def test_retrieve_returns_evidence_and_sources(retriever):
    ingest(retriever)

    result = retriever.retrieve(OWNER_A, "python fastapi developer")

    assert result.has_evidence is True
    assert result.query == "python fastapi developer"
    assert result.top_k == 5
    assert result.hits
    assert result.hits[0].filename == "resume.txt"
    assert result.hits[0].document_id
    assert result.hits[0].chunk_index >= 0
    assert 0.0 <= result.hits[0].score <= 1.0001


def test_retrieve_serializes_to_dict(retriever):
    ingest(retriever)

    payload = retriever.retrieve(OWNER_A, "python").as_dict()

    assert payload["query"] == "python"
    assert payload["has_evidence"] is True
    assert payload["hits"][0]["source_type"] == "resume"


def test_retrieve_on_empty_store_has_no_evidence(rag_dir):
    settings = make_settings(rag_dir)
    empty = Retriever(
        store=LocalVectorStore(settings, FakeEmbeddingService(8)),
        settings=settings,
    )

    result = empty.retrieve(OWNER_A, "python")

    assert result.has_evidence is False
    assert result.hits == ()


def test_retrieve_isolates_owners(retriever):
    ingest(retriever, owner=OWNER_A)

    result = retriever.retrieve(OWNER_B, "python fastapi")

    assert result.has_evidence is False
    assert result.hits == ()


def test_retrieve_respects_top_k(retriever):
    ingest(retriever)

    result = retriever.retrieve(OWNER_A, "python", top_k=1)

    assert len(result.hits) == 1


def test_retrieve_passes_candidate_filter(retriever):
    ingest(retriever)

    result = retriever.retrieve(OWNER_A, "python", candidate_id=CANDIDATE_A)

    assert result.has_evidence is True
    assert all(hit.candidate_id == CANDIDATE_A for hit in result.hits)


def test_retrieve_filters_by_source_type(retriever):
    ingest(retriever)

    result = retriever.retrieve(OWNER_A, "interview", source_types=["knowledge"])

    assert result.has_evidence is True
    assert all(hit.source_type == "knowledge" for hit in result.hits)


def test_retrieve_rejects_blank_query(retriever):
    with pytest.raises(ValueError):
        retriever.retrieve(OWNER_A, "   ")


def test_retrieve_rejects_overlong_query(retriever):
    with pytest.raises(ValueError):
        retriever.retrieve(OWNER_A, "x" * 600)


def test_retrieve_rejects_invalid_top_k(retriever):
    with pytest.raises(ValueError):
        retriever.retrieve(OWNER_A, "python", top_k=0)


def test_retrieve_rejects_invalid_owner(retriever):
    with pytest.raises(ValueError):
        retriever.retrieve("not-a-uuid", "python")


def test_min_similarity_filters_weak_matches(rag_dir):
    settings = make_settings(rag_dir, min_similarity=0.9)
    store = LocalVectorStore(settings, FakeEmbeddingService(8))
    retriever = Retriever(store=store, settings=settings)
    ingest(retriever)

    result = retriever.retrieve(OWNER_A, "completely unrelated topic")

    assert result.has_evidence is False


def test_get_retriever_is_cached(rag_dir):
    reset_retriever()
    settings = make_settings(rag_dir)

    first = get_retriever(settings)
    second = get_retriever(settings)

    assert first is second

    reset_retriever()
