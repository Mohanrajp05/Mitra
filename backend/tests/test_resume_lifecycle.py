"""Resume lifecycle regression tests (Stage 1).

Covers the replacement / deletion / cache-invalidation contract:

- replacing a resume removes the older resume file (privacy cleanup) and
  invalidates the user's cached RAG answers;
- matching resolves the resume text fresh on every call, so a replacement
  is used immediately and deleted content is never reused;
- invalidation is triggered by the document event itself (a content change
  with the same text length still invalidates);
- invalidation stays per user and per store event, and the server keeps no
  candidate-match cache that could go stale.
"""

import asyncio

import pytest

from app.rag.response_cache import CacheSettings, ResponseCache
from app.schemas.rag import EvidenceItem, MatchResult
from app.services import rag_service

OWNER = "owner-lifecycle"
CANDIDATE_ID = "cand-lifecycle"
JOB_ID = "job-lifecycle"

RESUME_A = (
    "Jane Doe, platform engineer. 6 years operating Kubernetes on AWS "
    "with Terraform and Datadog monitoring."
)
RESUME_B = (
    "Jane Doe, data engineer. 6 years building Airflow pipelines on "
    "Apache Spark with dbt and Snowflake."
)

JOB = {
    "id": JOB_ID,
    "title": "Engineer",
    "description": "Build things.",
    "required_skills": ["Python"],
}


class PipelineRun:
    """Minimal evidence-qualified result the response cache accepts."""

    has_evidence = True

    def __init__(self) -> None:
        self.answer = "cached answer"
        self.sources = [
            {
                "document_id": "doc-1",
                "score": 0.9,
                "source_type": "resume",
                "filename": "resume.pdf",
            }
        ]
        self.evidence_text = "evidence"


class ReplacementStore:
    """Fake document store tracking resume replacements."""

    def __init__(self, documents):
        self.documents = list(documents)
        self.deleted: list[str] = []
        self.invalidations = 0

    def list_documents(self, owner_user_id):
        assert owner_user_id == OWNER
        return [doc for doc in self.documents if doc["document_id"] not in self.deleted]

    def delete_document(self, owner_user_id, document_id):
        assert owner_user_id == OWNER
        self.deleted.append(document_id)
        self.documents = [
            doc for doc in self.documents if doc["document_id"] != document_id
        ]
        return True

    def document_text_for(self, owner_user_id, candidate_id, source_type):
        assert owner_user_id == OWNER
        assert candidate_id == CANDIDATE_ID
        assert source_type == "resume"
        remaining = [
            doc
            for doc in self.documents
            if doc.get("source_type") == "resume"
            and doc.get("candidate_id") == candidate_id
            and doc["document_id"] not in self.deleted
        ]
        return remaining[0]["text"] if remaining else None


def make_cache() -> ResponseCache:
    return ResponseCache(CacheSettings(enabled=True, ttl_seconds=60, max_entries=10))


def make_match() -> MatchResult:
    return MatchResult(
        matched_skills=[],
        missing_skills=[],
        unverified_skills=[],
        relevance="weak",
        relevance_score=0.0,
        match_score=0,
        partial_skills=[],
        explanation="n/a",
        evidence=[EvidenceItem(quote="quote", source="resume")],
    )


class RecordingOllama:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete_structured(self, model_cls, system_prompt, user_prompt):
        self.prompts.append(user_prompt)
        return make_match()


def run(coroutine):
    return asyncio.run(coroutine)


def seed_cache_entry(cache: ResponseCache) -> None:
    calls: list = []

    async def loader():
        calls.append(1)
        return PipelineRun()

    asyncio.run(cache.get_or_load(OWNER, "Who knows Python?", loader))
    assert len(calls) == 1
    # Sanity: the entry is cached.
    asyncio.run(cache.get_or_load(OWNER, "Who knows Python?", loader))
    assert len(calls) == 1


def test_replacement_cleanup_deletes_old_resume_and_invalidates_cache(monkeypatch):
    store = ReplacementStore(
        [
            {
                "document_id": "doc-old",
                "source_type": "resume",
                "candidate_id": CANDIDATE_ID,
                "content_hash": "hash-A",
                "text": RESUME_A,
            },
            {
                "document_id": "doc-other-candidate",
                "source_type": "resume",
                "candidate_id": "cand-someone-else",
                "content_hash": "hash-X",
                "text": "other candidate resume",
            },
            {
                "document_id": "doc-job",
                "source_type": "job_description",
                "candidate_id": None,
                "content_hash": "hash-J",
                "text": "job description",
            },
        ]
    )
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    cache = make_cache()
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: cache)
    monkeypatch.setattr(
        rag_service,
        "get_audit_trail",
        lambda: type("A", (), {"record": staticmethod(lambda *a, **k: None)})(),
    )
    seed_cache_entry(cache)

    removed = rag_service._cleanup_replaced_resume(
        OWNER,
        CANDIDATE_ID,
        {"document_id": "doc-new", "content_hash": "hash-B"},
    )

    assert removed == 1
    assert store.deleted == ["doc-old"]
    # Unrelated candidates' resumes and job documents survive.
    assert sorted(doc["document_id"] for doc in store.documents) == [
        "doc-job",
        "doc-other-candidate",
    ]
    # The user's cached answers are invalidated by the replacement.
    assert cache.get(cache.make_key(OWNER, "Who knows Python?")) is None


def test_replacement_with_identical_hash_is_kept():
    store = ReplacementStore(
        [
            {
                "document_id": "doc-old",
                "source_type": "resume",
                "candidate_id": CANDIDATE_ID,
                "content_hash": "hash-A",
                "text": RESUME_A,
            }
        ]
    )

    removed = rag_service._cleanup_replaced_resume(
        OWNER,
        CANDIDATE_ID,
        {"document_id": "doc-new", "content_hash": "hash-A"},
    )

    assert removed == 0
    assert store.deleted == []


def test_cache_invalidation_fires_on_same_length_content_change():
    """A same-length, different-content replacement must still invalidate.

    Invalidation is driven by the document event, not by the length of the
    changed text, so two resumes of identical length cannot share cache
    entries across the replacement boundary.
    """
    cache = make_cache()
    seed_cache_entry(cache)

    calls: list = []

    async def loader():
        calls.append(1)
        return PipelineRun()

    # Replacement upload: any document save invalidates the user's entries.
    cache.invalidate_user(OWNER)
    result = asyncio.run(cache.get_or_load(OWNER, "Who knows Python?", loader))

    assert len(calls) == 1
    assert result.answer == "cached answer"


def test_match_uses_replacement_resume_immediately(monkeypatch):
    """Stage 1 acceptance: match with Resume A, replace with Resume B, the
    next match prompt contains Resume B and never Resume A."""
    store = ReplacementStore(
        [
            {
                "document_id": "doc-a",
                "source_type": "resume",
                "candidate_id": CANDIDATE_ID,
                "content_hash": "hash-A",
                "text": RESUME_A,
            }
        ]
    )
    candidate = {"id": CANDIDATE_ID, "resume_text": "short placeholder"}

    monkeypatch.setattr(rag_service, "_get_job", lambda owner, job_id: JOB)
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: candidate)
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: make_cache())
    ollama = RecordingOllama()
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert RESUME_A in ollama.prompts[0]
    assert RESUME_B not in ollama.prompts[0]

    # Replace the resume: the store now only holds Resume B.
    store.documents[0]["text"] = RESUME_B
    store.documents[0]["content_hash"] = "hash-B"

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.prompts) == 2
    assert RESUME_B in ollama.prompts[1]
    assert RESUME_A not in ollama.prompts[1]


def test_deleted_resume_content_is_not_used_by_matching(monkeypatch):
    """After deletion the match falls back to the stored DB text; the
    deleted resume content never reaches the model."""
    store = ReplacementStore(
        [
            {
                "document_id": "doc-a",
                "source_type": "resume",
                "candidate_id": CANDIDATE_ID,
                "content_hash": "hash-A",
                "text": RESUME_A,
            }
        ]
    )
    placeholder = "Hand-typed note: Jane has six years of experience."
    candidate = {"id": CANDIDATE_ID, "resume_text": placeholder}

    monkeypatch.setattr(rag_service, "_get_job", lambda owner, job_id: JOB)
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: candidate)
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: make_cache())
    ollama = RecordingOllama()
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)

    store.delete_document(OWNER, "doc-a")
    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.prompts) == 1
    assert placeholder in ollama.prompts[0]
    assert RESUME_A not in ollama.prompts[0]


def test_unrelated_candidate_never_reads_another_candidates_resume(monkeypatch):
    """Resume text resolution is scoped to the candidate: matching candidate
    B cannot pick up candidate A's resume."""
    store = ReplacementStore(
        [
            {
                "document_id": "doc-a",
                "source_type": "resume",
                "candidate_id": "cand-A",
                "content_hash": "hash-A",
                "text": RESUME_A,
            }
        ]
    )
    candidate_b = {"id": CANDIDATE_ID, "resume_text": ""}

    monkeypatch.setattr(rag_service, "_get_job", lambda owner, job_id: JOB)
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: candidate_b)
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: make_cache())
    ollama = RecordingOllama()
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)

    # Candidate B has no resume at all: the endpoint refuses instead of
    # silently matching against someone else's resume.
    with pytest.raises(rag_service.RagServiceError):
        run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert ollama.prompts == []


def test_save_document_invalidates_cache_once_per_upload(monkeypatch):
    """A resume upload (replacement or first upload) invalidates the cached
    RAG answers exactly once, and the privacy cleanup runs afterwards."""
    saved_records = iter(
        [
            {
                "document_id": "doc-new",
                "source_type": "resume",
                "candidate_id": CANDIDATE_ID,
                "content_hash": "hash-B",
            }
        ]
    )

    class SaveStore:
        def save_document(self, owner_user_id, **kwargs):
            assert owner_user_id == OWNER
            assert kwargs["source_type"] == "resume"
            assert kwargs["candidate_id"] == CANDIDATE_ID
            return next(saved_records)

        def list_documents(self, owner_user_id):
            return [
                {
                    "document_id": "doc-old",
                    "source_type": "resume",
                    "candidate_id": CANDIDATE_ID,
                    "content_hash": "hash-A",
                }
            ]

        def delete_document(self, owner_user_id, document_id):
            assert document_id == "doc-old"
            return True

    store = SaveStore()
    cache = make_cache()
    seed_cache_entry(cache)
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "_check_links", lambda *a, **k: None)
    monkeypatch.setattr(rag_service, "get_audit_trail", lambda: type("A", (), {"record": staticmethod(lambda *a, **k: None)})())
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: cache)

    run(
        rag_service.save_document(
            OWNER,
            filename="resume-b.txt",
            data=b"resume B",
            source_type="resume",
            candidate_id=CANDIDATE_ID,
        )
    )

    # Cache invalidated by the upload and by the replacement cleanup.
    assert cache.get(cache.make_key(OWNER, "Who knows Python?")) is None


def test_deleting_resume_clears_extracted_profile(monkeypatch):
    """Stage 1+2: deleting the resume invalidates the cache AND clears the
    candidate's extracted profile so the detail page never shows skills from
    a deleted resume."""
    from types import SimpleNamespace

    updated = {}
    monkeypatch.setattr(
        rag_service.queries,
        "update_candidate",
        lambda connection, owner, cand_id, changes: updated.setdefault(
            "changes", (owner, cand_id, changes)
        ) or {"id": cand_id},
    )
    monkeypatch.setattr(
        rag_service, "get_connection",
        lambda: __import__("contextlib").nullcontext(object()),
    )
    class Store:
        def get_document(self, owner, document_id):
            assert (owner, document_id) == (OWNER, "doc-a")
            return SimpleNamespace(
                source_type="resume", candidate_id=CANDIDATE_ID
            )
        def delete_document(self, owner, document_id):
            return True
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: Store())
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: SimpleNamespace(
        invalidate_user=lambda owner: updated.setdefault("invalidated", owner)))
    monkeypatch.setattr(rag_service, "get_audit_trail", lambda: SimpleNamespace(
        record=lambda *a, **k: None))

    run(rag_service.delete_document(OWNER, "doc-a"))

    assert updated["invalidated"] == OWNER
    assert updated["changes"] == (OWNER, CANDIDATE_ID, {"extracted_profile": None})


def test_deleting_job_document_does_not_touch_extracted_profile(monkeypatch):
    """Only resume deletions clear the extraction; job documents leave the
    candidate record untouched."""
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(
        rag_service.queries,
        "update_candidate",
        lambda *a, **k: calls.append(a),
    )
    monkeypatch.setattr(
        rag_service, "get_connection",
        lambda: __import__("contextlib").nullcontext(object()),
    )
    class Store:
        def get_document(self, owner, document_id):
            return SimpleNamespace(
                source_type="job_description", candidate_id=None
            )
        def delete_document(self, owner, document_id):
            return True
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: Store())
    monkeypatch.setattr(rag_service, "get_response_cache", lambda: SimpleNamespace(
        invalidate_user=lambda owner: None))
    monkeypatch.setattr(rag_service, "get_audit_trail", lambda: SimpleNamespace(
        record=lambda *a, **k: None))

    run(rag_service.delete_document(OWNER, "doc-job"))

    assert calls == []
