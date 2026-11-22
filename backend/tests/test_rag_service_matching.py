import asyncio
from types import SimpleNamespace

import pytest

from app.rag import match_cache
from app.schemas.candidate import CandidateUpdate
from app.schemas.job import JobUpdate
from app.schemas.rag import EvidenceItem, MatchResult
from app.services import candidate_service, job_service, rag_service


OWNER = "owner-1"
CANDIDATE_ID = "cand-1"
JOB_ID = "job-1"


class FakeStore:
    settings = SimpleNamespace(max_query_chars=1_000)

    def __init__(self, documents=None):
        self._documents = list(documents or [])

    def search(self, *args, **kwargs):
        return []

    def list_documents(self, owner_user_id):
        return list(self._documents)

    def document_text_for(self, owner, candidate_id=None, source_type=None):
        return None


def test_resolve_resume_text_prefers_linked_document_over_placeholder(monkeypatch):
    class DocStore:
        def document_text_for(self, owner, candidate_id, source_type):
            assert (owner, candidate_id, source_type) == (
                "owner-1", "cand-1", "resume",
            )
            return "Full parsed resume text mentioning AWS, Terraform and Kubernetes."

    monkeypatch.setattr(rag_service, "_get_document_store", lambda: DocStore())

    candidate = {"resume_text": "My name is Jane and I have 5 years of experience."}
    result = rag_service._resolve_resume_text("owner-1", candidate, "cand-1")

    assert result == "Full parsed resume text mentioning AWS, Terraform and Kubernetes."


def test_resolve_resume_text_skips_store_for_substantial_db_text(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("document store must not be consulted")

    monkeypatch.setattr(rag_service, "_get_document_store", fail)

    long_text = "x" * 250
    candidate = {"resume_text": long_text}

    assert rag_service._resolve_resume_text("owner-1", candidate, "cand-1") == long_text


def test_resolve_resume_text_prefers_linked_document_over_db_text(monkeypatch):
    class DocStore:
        def document_text_for(self, *args, **kwargs):
            return "tiny doc"

    monkeypatch.setattr(rag_service, "_get_document_store", lambda: DocStore())

    medium_text = "y" * 120
    candidate = {"resume_text": medium_text}

    # Linked document text always takes precedence over DB text, even when
    # shorter, so a replaced resume is immediately reflected in matching.
    assert rag_service._resolve_resume_text("owner-1", candidate, "cand-1") == "tiny doc"


def test_resolve_resume_text_falls_back_to_placeholder_without_linked_doc(monkeypatch):
    class DocStore:
        def document_text_for(self, *args, **kwargs):
            return None

    monkeypatch.setattr(rag_service, "_get_document_store", lambda: DocStore())

    candidate = {"resume_text": "short placeholder"}
    result = rag_service._resolve_resume_text("owner-1", candidate, "cand-1")

    assert result == "short placeholder"


def test_resolve_resume_text_returns_none_without_any_text(monkeypatch):
    class DocStore:
        def document_text_for(self, *args, **kwargs):
            return None

    monkeypatch.setattr(rag_service, "_get_document_store", lambda: DocStore())

    candidate = {"resume_text": ""}

    assert rag_service._resolve_resume_text("owner-1", candidate, "cand-1") is None


def run(coroutine):
    return asyncio.run(coroutine)


def make_match() -> MatchResult:
    return MatchResult(
        matched_skills=["Python", "Kubernetes"],
        missing_skills=[],
        unverified_skills=[],
        relevance="strong",
        relevance_score=0.9,
        match_score=90,
        partial_skills=[],
        explanation="Strong backend fit.",
        evidence=[
            EvidenceItem(quote="Python developer", source="resume.txt"),
            EvidenceItem(quote="Ran a Kubernetes platform team", source="resume.txt"),
        ],
    )


def base_job(**overrides):
    job = {
        "id": JOB_ID,
        "title": "Backend Engineer",
        "company": "Acme",
        "description": "Build backend services with Python.",
        "required_skills": ["Python", "Kubernetes"],
        "experience_required": None,
        "location": "Remote",
    }
    job.update(overrides)
    return job


def base_candidate(**overrides):
    candidate = {
        "id": CANDIDATE_ID,
        "full_name": "Jane Doe",
        "experience_years": None,
        "skills": [],
        "resume_text": "Jane Doe is a Python developer.",
    }
    candidate.update(overrides)
    return candidate


def patch_dependencies(monkeypatch, ollama, *, job=None, candidate=None, resume_text=None, store=None):
    job_data = dict(job or base_job())
    candidate_data = dict(candidate or base_candidate())
    if resume_text is None:
        resume_text = "Jane Doe is a Python developer."
    doc_store = store or FakeStore()

    monkeypatch.setattr(rag_service, "_get_job", lambda owner, job_id: dict(job_data))
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: dict(candidate_data))
    monkeypatch.setattr(
        rag_service,
        "_resolve_resume_text",
        lambda owner, cand, cand_id: resume_text,
    )
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: doc_store)
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)
    return {"job": job_data, "candidate": candidate_data, "store": doc_store}


class FakeOllama:
    def __init__(self, *, delay=0.0):
        self.calls = []
        self.delay = delay

    async def complete_structured(self, model_cls, system_prompt, user_prompt):
        self.calls.append((model_cls, system_prompt, user_prompt))
        if self.delay:
            await asyncio.sleep(self.delay)
        return make_match()


class FailingOllama:
    def __init__(self):
        self.calls = 0

    async def complete_structured(self, model_cls, system_prompt, user_prompt):
        self.calls += 1
        raise rag_service.OllamaError("temporary ollama failure")


class InvalidResultOllama:
    """Returns a result that finalize_match may alter, but we can also force
    a cache-ineligible payload by returning a non-cacheable structure through
    a custom compute path in specific tests. For service-level failure caching
    we rely on exceptions; for invalid results we test cache directly."""

    def __init__(self):
        self.calls = 0

    async def complete_structured(self, model_cls, system_prompt, user_prompt):
        self.calls += 1
        return make_match()


def test_match_candidate_uses_ollama_with_full_job_and_resume(monkeypatch):
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)
    monkeypatch.setattr(
        rag_service,
        "get_orchestrator",
        lambda: (_ for _ in ()).throw(AssertionError("Portkey orchestrator must not run")),
    )

    result = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.calls) == 1
    prompt = ollama.calls[0][2]
    assert "Backend Engineer" in prompt
    assert "Jane Doe is a Python developer." in prompt
    assert "Required skills" in prompt
    assert result["cache_status"] == "miss"
    assert result["cached"] is False


def test_match_candidate_drops_unevidenced_claims(monkeypatch):
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    result = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    match = result["match"]

    assert match.matched_skills == ["Python"]
    assert match.unverified_skills == ["Kubernetes"]
    assert [item.quote for item in match.evidence] == ["Python developer"]
    assert result["candidate_id"] == CANDIDATE_ID
    assert result["job_id"] == JOB_ID
    # Deterministic score: 1 of 2 required skills matched + 1 partial,
    # no experience requirement on the job.
    # score = 100 * (0.8 * (1 + 0.5) / 2 + 0.2 * 1.0) = 80.0
    assert match.match_score == 80.0
    assert match.relevance == "strong"
    assert match.partial_skills == ["Kubernetes"]


def test_match_retrieval_query_stays_within_the_vector_store_limit():
    job = {
        "title": "Backend Engineer",
        "required_skills": ["Python", "FastAPI"],
        "description": "x" * 2_000,
    }

    query = rag_service._match_retrieval_query(job, 80)

    assert len(query) == 80
    assert "Backend Engineer" in query
    assert "Python" in query


def test_match_first_call_calls_ollama_once(monkeypatch):
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    result = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.calls) == 1
    assert result["cache_status"] == "miss"
    assert result["cached"] is False
    assert result["match"].match_score == 80.0


def test_repeat_same_request_returns_cached_result_without_ollama(monkeypatch):
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    first = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    second = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    third = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.calls) == 1, "unchanged repeat requests must not call Ollama again"
    assert first["cache_status"] == "miss"
    assert second["cache_status"] == "hit"
    assert second["cached"] is True
    assert third["cache_status"] == "hit"
    assert second["match"].match_score == first["match"].match_score == 80.0
    assert second["match"].matched_skills == ["Python"]
    assert [e.quote for e in second["match"].evidence] == ["Python developer"]


def test_navigate_away_and_return_does_not_cause_extra_ollama_call(monkeypatch):
    """Simulates returning to the same job/candidate after navigation/remount by
    repeating the identical backend request (frontend preserves results and
    should not re-request, but backend must still be safe/idempotent)."""
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    calls_after_first_view = len(ollama.calls)
    # "Navigate away" (no calls), then "return" and request same match again.
    again = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert calls_after_first_view == 1
    assert len(ollama.calls) == 1
    assert again["cached"] is True


def test_same_selection_repeated_does_not_cause_extra_ollama_call(monkeypatch):
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    for _ in range(5):
        result = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 1
    assert result["cache_status"] == "hit"


def test_two_simultaneous_identical_requests_result_in_one_ollama_call(monkeypatch):
    ollama = FakeOllama(delay=0.05)
    patch_dependencies(monkeypatch, ollama)

    async def run_pair():
        return await asyncio.gather(
            rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID),
            rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID),
        )

    first, second = run(run_pair())

    assert len(ollama.calls) == 1, "concurrent identical requests must share one Ollama call"
    assert first["match"].match_score == 80.0
    assert second["match"].match_score == 80.0
    assert [e.quote for e in first["match"].evidence] == ["Python developer"]


def test_resume_replacement_triggers_fresh_analysis(monkeypatch):
    """A changed resume fingerprint/content must not reuse the old cached result."""
    ollama = FakeOllama()
    state = {"resume": "Jane Doe is a Python developer."}

    job = base_job()
    candidate = base_candidate()
    store = FakeStore()

    monkeypatch.setattr(rag_service, "_get_job", lambda owner, job_id: dict(job))
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: dict(candidate))
    monkeypatch.setattr(rag_service, "_resolve_resume_text", lambda owner, cand, cid: state["resume"])
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)

    first = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 1
    assert first["cache_status"] == "miss"

    # Simulate resume replacement: new content/fingerprint.
    state["resume"] = "Jane Doe is a Python and Kubernetes platform engineer."
    second = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.calls) == 2, "resume replacement must trigger a fresh Ollama analysis"
    assert second["cache_status"] == "miss"


def test_resume_delete_invalidates_and_old_result_not_reused(monkeypatch):
    """Deleting a resume invalidates cached matches for that candidate."""
    ollama = FakeOllama()
    store = FakeStore()
    patch_dependencies(monkeypatch, ollama, store=store)

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 1

    # Simulate backend invalidation performed on resume delete.
    rag_service._invalidate_match_cache_for_candidate(OWNER, CANDIDATE_ID)

    # After invalidation the next request for the same inputs must recompute.
    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 2, "old result must not be reused after resume deletion"


def test_job_description_update_triggers_fresh_analysis(monkeypatch):
    ollama = FakeOllama()
    job = base_job(description="Build backend services with Python.")
    candidate = base_candidate()
    store = FakeStore()

    def get_job(owner, job_id):
        return dict(job)

    monkeypatch.setattr(rag_service, "_get_job", get_job)
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: dict(candidate))
    monkeypatch.setattr(
        rag_service,
        "_resolve_resume_text",
        lambda owner, cand, cid: "Jane Doe is a Python developer.",
    )
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 1

    job["description"] = "Build distributed backend services with Python and Go."
    # Service-level invalidation hook (as called by job_service.update_job on relevant changes).
    job_service._invalidate_match_cache_for_job(OWNER, JOB_ID)

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 2, "job description update must trigger fresh analysis"


def test_required_skills_update_triggers_fresh_analysis(monkeypatch):
    ollama = FakeOllama()
    job = base_job(required_skills=["Python", "Kubernetes"])
    candidate = base_candidate()
    store = FakeStore()

    monkeypatch.setattr(rag_service, "_get_job", lambda owner, job_id: dict(job))
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: dict(candidate))
    monkeypatch.setattr(
        rag_service,
        "_resolve_resume_text",
        lambda owner, cand, cid: "Jane Doe is a Python developer.",
    )
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 1

    job["required_skills"] = ["Python", "Kubernetes", "Terraform"]
    job_service._invalidate_match_cache_for_job(OWNER, JOB_ID)

    run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert len(ollama.calls) == 2, "required skills update must trigger fresh analysis"


def test_different_users_cannot_share_cached_results(monkeypatch):
    ollama = FakeOllama()
    job = base_job()
    candidate = base_candidate()
    store = FakeStore()
    resume = "Jane Doe is a Python developer."

    monkeypatch.setattr(rag_service, "_get_job", lambda owner, job_id: dict(job))
    monkeypatch.setattr(rag_service, "_get_candidate", lambda owner, cand_id: dict(candidate))
    monkeypatch.setattr(rag_service, "_resolve_resume_text", lambda owner, cand, cid: resume)
    monkeypatch.setattr(rag_service, "_get_document_store", lambda: store)
    monkeypatch.setattr(rag_service, "get_ollama_client", lambda: ollama)

    a = run(rag_service.match_candidate("user-a", CANDIDATE_ID, JOB_ID))
    b = run(rag_service.match_candidate("user-b", CANDIDATE_ID, JOB_ID))

    assert len(ollama.calls) == 2, "different users must not share cached match results"
    assert a["cache_status"] == "miss"
    assert b["cache_status"] == "miss"


def test_explicit_refresh_performs_new_analysis(monkeypatch):
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    first = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    refreshed = run(
        rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID, force_refresh=True)
    )
    after = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.calls) == 2, "explicit refresh must trigger a new Ollama call"
    assert first["cache_status"] == "miss"
    assert refreshed["cache_status"] == "refresh"
    assert refreshed["cached"] is False
    assert after["cache_status"] == "hit"
    assert refreshed["match"].match_score == 80.0


def test_failed_ollama_requests_are_not_cached(monkeypatch):
    ollama = FailingOllama()
    patch_dependencies(monkeypatch, ollama)

    with pytest.raises(rag_service.RagAgentError):
        run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert ollama.calls == 1

    # Second attempt must call Ollama again because failures are not cached.
    with pytest.raises(rag_service.RagAgentError):
        run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert ollama.calls == 2

    stats = match_cache.get_match_cache().stats()
    assert stats["entries"] == 0


def test_invalid_match_results_are_not_cached(monkeypatch):
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    async def bad_compute(owner, candidate_id, job_id, key, loader, *, force_refresh=False):
        # Simulate a completed but invalid/incomplete payload.
        return {"candidate_id": candidate_id, "job_id": job_id, "match": None}, "miss"

    cache = match_cache.get_match_cache()
    monkeypatch.setattr(cache, "get_or_load", bad_compute)

    result = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    assert result["match"] is None
    # Nothing cacheable was stored.
    assert cache.stats()["entries"] == 0


def test_evidence_validation_and_deterministic_scores_remain_correct_on_cache_hit(monkeypatch):
    """Cached responses must preserve the same validated, deterministically scored
    match as the original computation (no weakened evidence rules)."""
    ollama = FakeOllama()
    patch_dependencies(monkeypatch, ollama)

    first = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))
    second = run(rag_service.match_candidate(OWNER, CANDIDATE_ID, JOB_ID))

    assert len(ollama.calls) == 1
    for result in (first, second):
        match = result["match"]
        # Unevidenced 'Kubernetes' claim must remain dropped on hit and miss.
        assert match.matched_skills == ["Python"]
        assert match.unverified_skills == ["Kubernetes"]
        assert match.partial_skills == ["Kubernetes"]
        assert [item.quote for item in match.evidence] == ["Python developer"]
        assert match.match_score == 80.0
        assert match.relevance == "strong"
        assert isinstance(match.experience_comparison, str)


def test_service_invalidation_hook_is_called_for_relevant_candidate_update(monkeypatch):
    calls = []

    def fake_invalidate(owner, candidate_id):
        calls.append((owner, candidate_id))

    monkeypatch.setattr(candidate_service, "_invalidate_match_cache_for_candidate", fake_invalidate)

    def fake_get_connection():
        class _Conn:
            def __enter__(self_inner):
                return object()
            def __exit__(self_inner, *exc):
                return False
        return _Conn()

    monkeypatch.setattr(candidate_service, "get_connection", fake_get_connection)
    monkeypatch.setattr(
        candidate_service.queries,
        "update_candidate",
        lambda connection, owner, cid, changes: {"id": cid},
    )
    monkeypatch.setattr(candidate_service, "get_audit_trail", lambda: SimpleNamespace(record=lambda *a, **k: None))

    candidate_service.update_candidate(
        OWNER, CANDIDATE_ID, CandidateUpdate(experience_years=5)
    )
    assert calls == [(OWNER, CANDIDATE_ID)]

    calls.clear()
    candidate_service.update_candidate(
        OWNER, CANDIDATE_ID, CandidateUpdate(full_name="Jane Q. Doe")
    )
    assert calls == [], "non-relevant candidate fields must not invalidate match cache"


def test_service_invalidation_hook_is_called_for_relevant_job_update(monkeypatch):
    calls = []

    def fake_invalidate(owner, job_id):
        calls.append((owner, job_id))

    monkeypatch.setattr(job_service, "_invalidate_match_cache_for_job", fake_invalidate)

    class _Conn:
        def __enter__(self):
            return object()
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(job_service, "get_connection", lambda: _Conn())
    monkeypatch.setattr(
        job_service.queries,
        "update_job",
        lambda connection, owner, jid, changes: {"id": jid},
    )

    job_service.update_job(
        OWNER, JOB_ID, JobUpdate(description="Updated description")
    )
    assert calls == [(OWNER, JOB_ID)]

    calls.clear()
    job_service.update_job(OWNER, JOB_ID, JobUpdate(status="closed"))
    assert calls == [], "non-relevant job fields must not invalidate match cache"