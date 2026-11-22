import json

import numpy as np
import pytest

from app.rag.document_loader import EmptyDocumentError, InvalidDocumentError
from app.rag.splitter import hash_content
from app.rag.vector_store import LocalVectorStore, VectorStoreIOError
from tests.rag_helpers import FakeEmbeddingService, make_settings

OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"
CANDIDATE_A = "33333333-3333-4333-8333-333333333333"
CANDIDATE_B = "55555555-5555-4555-8555-555555555555"
JOB_A = "44444444-4444-4444-8444-444444444444"
JOB_B = "66666666-6666-4666-8666-666666666666"

RESUME_TEXT = (
    b"Jane Doe\n\n"
    b"Python developer with five years of experience building FastAPI services.\n\n"
    b"Skills: Python, FastAPI, PostgreSQL, Docker, unit testing.\n\n"
    b"Education: Bachelor of Computer Science."
)

KNOWLEDGE_TEXT = (
    b"Interview scheduling guide.\n\n"
    b"Recruiters should confirm availability before proposing interview slots.\n\n"
    b"Always send a written summary after the interview."
)


@pytest.fixture
def store(rag_dir):
    settings = make_settings(rag_dir)
    return LocalVectorStore(settings, FakeEmbeddingService(8))


def save_resume(store, owner=OWNER_A, candidate_id=None, job_id=None, data=RESUME_TEXT):
    return store.save_document(
        owner,
        filename="resume.txt",
        data=data,
        source_type="resume",
        candidate_id=candidate_id,
        job_id=job_id,
        content_type="text/plain",
    )


def test_save_document_persists_all_artifacts(store):
    document = save_resume(store)

    assert document.created is True
    assert document.chunk_count >= 1
    assert document.embedding_dimension == 8

    settings = store.settings
    assert (settings.metadata_dir / f"{document.document_id}.json").exists()
    assert (settings.embeddings_dir / f"{document.document_id}.npy").exists()
    assert list(settings.documents_dir.glob(f"{document.document_id}__*"))

    matrix = np.load(settings.embeddings_dir / f"{document.document_id}.npy")
    assert matrix.shape == (document.chunk_count, 8)


def test_get_document_returns_full_record(store):
    saved = save_resume(store)

    loaded = store.get_document(OWNER_A, saved.document_id)

    assert loaded is not None
    assert loaded.document_id == saved.document_id
    assert loaded.content_hash == saved.content_hash
    assert [chunk.chunk_id for chunk in loaded.chunks] == [
        chunk.chunk_id for chunk in saved.chunks
    ]


def test_duplicate_upload_reuses_existing_document(store):
    first = save_resume(store)
    second = save_resume(store)

    assert second.created is False
    assert second.document_id == first.document_id
    assert len(store.list_documents(OWNER_A)) == 1
    assert len(list(store.settings.embeddings_dir.glob("*.npy"))) == 1


def test_duplicate_content_for_different_owner_is_separate(store):
    first = save_resume(store, owner=OWNER_A)
    second = save_resume(store, owner=OWNER_B)

    assert second.created is True
    assert second.document_id != first.document_id
    assert len(store.list_documents(OWNER_B)) == 1


def test_same_content_for_different_candidate_is_separate(store):
    first = save_resume(store, candidate_id=CANDIDATE_A)
    second = save_resume(store, candidate_id=CANDIDATE_B)

    assert second.created is True
    assert second.document_id != first.document_id


def test_duplicate_chunks_are_not_stored(store):
    text = ("b" * 100 + "\n\n") * 4

    document = store.save_document(
        OWNER_A,
        filename="repeat.txt",
        data=text.encode("utf-8"),
        source_type="knowledge",
        chunk_size=100,
        chunk_overlap=0,
    )

    assert document.chunk_count == 1


def test_list_documents_hides_chunk_content(store):
    save_resume(store)

    documents = store.list_documents(OWNER_A)

    assert len(documents) == 1
    assert "chunks" not in documents[0]
    assert documents[0]["filename"] == "resume.txt"


def test_ownership_isolation_for_get_and_list(store):
    saved = save_resume(store, owner=OWNER_A)

    assert store.get_document(OWNER_B, saved.document_id) is None
    assert store.list_documents(OWNER_B) == []


def test_ownership_isolation_for_search(store):
    save_resume(store, owner=OWNER_A)

    assert store.search(OWNER_B, query="python fastapi") == []
    assert store.search(OWNER_A, query="python fastapi") != []


def test_search_returns_ranked_hits_with_metadata(store):
    save_resume(store)
    store.save_document(
        OWNER_A,
        filename="guide.txt",
        data=KNOWLEDGE_TEXT,
        source_type="knowledge",
    )

    hits = store.search(OWNER_A, query="python fastapi postgresql")

    assert hits
    assert hits[0].filename == "resume.txt"
    assert hits[0].score >= hits[-1].score
    assert hits[0].source_type == "resume"
    assert hits[0].chunk_id
    assert hits[0].content


def test_search_respects_top_k(store):
    save_resume(store)
    store.save_document(
        OWNER_A,
        filename="guide.txt",
        data=KNOWLEDGE_TEXT,
        source_type="knowledge",
    )

    assert len(store.search(OWNER_A, query="python", top_k=1)) == 1


def test_search_filters_by_candidate(store):
    save_resume(store, candidate_id=CANDIDATE_A)
    save_resume(
        store,
        candidate_id=CANDIDATE_B,
        data=b"Different candidate with Java and Spring Boot experience.",
    )

    hits = store.search(OWNER_A, query="python", candidate_id=CANDIDATE_A)

    assert hits
    assert all(hit.candidate_id == CANDIDATE_A for hit in hits)


def test_search_filters_by_job(store):
    save_resume(store, job_id=JOB_A)
    save_resume(
        store,
        job_id=JOB_B,
        data=b"Another resume focused on machine learning models.",
    )

    hits = store.search(OWNER_A, query="python", job_id=JOB_B)

    assert hits
    assert all(hit.job_id == JOB_B for hit in hits)


def test_search_filters_by_source_type(store):
    save_resume(store)
    store.save_document(
        OWNER_A,
        filename="guide.txt",
        data=KNOWLEDGE_TEXT,
        source_type="knowledge",
    )

    hits = store.search(OWNER_A, query="python", source_types=("knowledge",))

    assert hits
    assert all(hit.source_type == "knowledge" for hit in hits)


def test_search_filters_by_document_ids(store):
    first = save_resume(store, candidate_id=CANDIDATE_A)
    second = save_resume(
        store,
        candidate_id=CANDIDATE_B,
        data=b"Different candidate with Java and Spring Boot experience.",
    )

    hits = store.search(OWNER_A, query="python", document_ids=[second.document_id])

    assert hits
    assert all(hit.document_id == second.document_id for hit in hits)
    assert all(hit.document_id != first.document_id for hit in hits)


def test_search_deduplicates_identical_chunks_across_documents(store):
    first = save_resume(store, candidate_id=CANDIDATE_A)
    second = save_resume(store, candidate_id=CANDIDATE_B)

    assert first.document_id != second.document_id
    hits = store.search(OWNER_A, query="python", top_k=20)

    assert hits
    assert len({hit.chunk_id for hit in hits}) == len(hits)
    assert len({hash_content(hit.content) for hit in hits}) == len(hits)


def test_search_on_empty_store_returns_empty_list(rag_dir):
    settings = make_settings(rag_dir)
    empty = LocalVectorStore(settings, FakeEmbeddingService(8))

    assert empty.search(OWNER_A, query="python") == []


def test_search_rejects_invalid_queries(store):
    with pytest.raises(ValueError):
        store.search(OWNER_A, query="   ")

    with pytest.raises(ValueError):
        store.search(OWNER_A, query="x" * 600)


def test_search_rejects_invalid_identifiers(store):
    with pytest.raises(ValueError):
        store.search("not-a-uuid", query="python")

    with pytest.raises(ValueError):
        store.search(OWNER_A, query="python", candidate_id="not-a-uuid")


def test_top_k_bounds_are_enforced(store):
    with pytest.raises(ValueError):
        store.search(OWNER_A, query="python", top_k=0)

    with pytest.raises(ValueError):
        store.search(OWNER_A, query="python", top_k=500)


def test_invalid_source_type_is_rejected(store):
    with pytest.raises(ValueError):
        store.save_document(
            OWNER_A,
            filename="resume.txt",
            data=RESUME_TEXT,
            source_type="payroll",
        )


def test_invalid_document_is_rejected_and_nothing_is_written(store):
    with pytest.raises(InvalidDocumentError):
        store.save_document(
            OWNER_A,
            filename="resume.pdf",
            data=b"not a pdf",
            source_type="resume",
        )

    assert not list(store.settings.metadata_dir.glob("*.json"))


def test_empty_document_is_rejected(store):
    with pytest.raises(EmptyDocumentError):
        store.save_document(
            OWNER_A,
            filename="empty.txt",
            data=b"",
            source_type="resume",
        )


def test_delete_document_removes_files(store):
    saved = save_resume(store)

    assert store.delete_document(OWNER_A, saved.document_id) is True
    assert store.get_document(OWNER_A, saved.document_id) is None
    assert not (store.settings.metadata_dir / f"{saved.document_id}.json").exists()
    assert not (store.settings.embeddings_dir / f"{saved.document_id}.npy").exists()
    assert not list(store.settings.documents_dir.glob(f"{saved.document_id}__*"))


def test_delete_by_non_owner_is_refused(store):
    saved = save_resume(store, owner=OWNER_A)

    assert store.delete_document(OWNER_B, saved.document_id) is False
    assert store.get_document(OWNER_A, saved.document_id) is not None


def test_rebuild_index_restores_missing_embeddings(store):
    saved = save_resume(store)
    (store.settings.embeddings_dir / f"{saved.document_id}.npy").unlink()

    report = store.rebuild_index()

    assert report.scanned == 1
    assert report.rebuilt == 1
    assert (store.settings.embeddings_dir / f"{saved.document_id}.npy").exists()
    assert store.search(OWNER_A, query="python")


def test_rebuild_index_skips_current_documents(store):
    save_resume(store)

    report = store.rebuild_index()

    assert report.scanned == 1
    assert report.rebuilt == 0
    assert report.skipped == 1


def test_rebuild_index_removes_orphan_embeddings(store):
    store.ensure_directories()
    orphan = store.settings.embeddings_dir / "99999999-9999-4999-8999-999999999999.npy"
    np.save(orphan, np.ones((1, 8), dtype=np.float32))

    report = store.rebuild_index()

    assert report.removed == 1
    assert not orphan.exists()


def test_rebuild_index_can_scope_to_owner(store):
    save_resume(store, owner=OWNER_A)
    save_resume(store, owner=OWNER_B)

    report = store.rebuild_index(OWNER_A)

    assert report.scanned == 1


def test_storage_failure_is_reported(rag_dir):
    blocked = rag_dir / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    settings = make_settings(rag_dir, data_dir=blocked)
    broken = LocalVectorStore(settings, FakeEmbeddingService(8))

    with pytest.raises(VectorStoreIOError):
        broken.save_document(
            OWNER_A,
            filename="resume.txt",
            data=RESUME_TEXT,
            source_type="resume",
        )


def test_metadata_contains_no_secret_material(store):
    saved = save_resume(store)
    path = store.settings.metadata_dir / f"{saved.document_id}.json"

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["owner_user_id"] == OWNER_A
    assert payload["source_type"] == "resume"
    assert "api_key" not in path.read_text(encoding="utf-8").lower()


def test_open_original_returns_stored_file_for_owner(store):
    document = save_resume(store)

    opened = store.open_original(OWNER_A, document.document_id)

    assert opened is not None
    path, mime_type, filename = opened
    assert path.exists()
    assert filename == "resume.txt"
    assert mime_type == "text/plain"
    assert path.parent == store.settings.documents_dir.resolve()


def test_open_original_denies_other_owner(store):
    document = save_resume(store)

    assert store.open_original(OWNER_B, document.document_id) is None


def test_open_original_missing_file_returns_none(store, rag_dir):
    document = save_resume(store)
    original = store._original_path(document.document_id, "resume.txt")
    original.unlink()

    assert store.open_original(OWNER_A, document.document_id) is None
