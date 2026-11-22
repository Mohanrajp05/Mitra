import asyncio

import pytest

from app.rag.pipeline import (
    NO_EVIDENCE_ANSWER,
    PipelineResult,
    RagPipeline,
    get_rag_pipeline,
    reset_rag_pipeline,
    set_rag_pipeline,
)
from app.rag.retriever import RetrievalResult
from app.rag.vector_store import SearchHit


def run(coro):
    return asyncio.run(coro)


OWNER_ID = "11111111-1111-4111-8111-111111111111"


def make_hit(**overrides):
    values = {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "chunk_index": 0,
        "content": "Candidate knows Python and FastAPI.",
        "score": 0.61,
        "source_type": "resume",
        "filename": "resume.txt",
        "candidate_id": None,
        "job_id": None,
        "created_at": "2026-11-13T00:00:00+00:00",
    }
    values.update(overrides)
    return SearchHit(**values)


class FakeRetriever:
    def __init__(self, hits=()):
        self.hits = tuple(hits)
        self.calls = []

    def retrieve(self, owner_user_id, query, top_k, candidate_id, job_id, source_types):
        self.calls.append(
            {
                "owner_user_id": owner_user_id,
                "query": query,
                "top_k": top_k,
                "candidate_id": candidate_id,
                "job_id": job_id,
                "source_types": source_types,
            }
        )
        return RetrievalResult(
            query=query,
            top_k=top_k or 5,
            hits=self.hits,
            has_evidence=bool(self.hits),
        )


class FakeLLMClient:
    def __init__(self, answer="Answer from evidence."):
        self.answer = answer
        self.calls = []

    async def complete(self, system_prompt, user_prompt, **kwargs):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                **kwargs,
            }
        )
        return self.answer


def make_pipeline(hits, answer="Answer from evidence."):
    retriever = FakeRetriever(hits)
    llm = FakeLLMClient(answer)
    return RagPipeline(retriever=retriever, llm_client=llm), retriever, llm


def test_pipeline_requires_query():
    pipeline, _, _ = make_pipeline([])

    with pytest.raises(ValueError):
        run(pipeline.run(OWNER_ID, "   "))


def test_pipeline_without_evidence_skips_llm():
    pipeline, retriever, llm = make_pipeline([])

    result = run(pipeline.run(OWNER_ID, "Who knows Python?"))

    assert isinstance(result, PipelineResult)
    assert result.has_evidence is False
    assert result.answer == NO_EVIDENCE_ANSWER
    assert result.sources == []
    assert result.evidence_text == ""
    assert llm.calls == []
    assert retriever.calls[0]["owner_user_id"] == OWNER_ID
    assert retriever.calls[0]["query"] == "Who knows Python?"


def test_pipeline_answers_from_evidence():
    pipeline, retriever, llm = make_pipeline(
        [make_hit(), make_hit(chunk_id="chunk-2", document_id="doc-2", score=0.42)],
        answer="Jane Doe knows Python.",
    )

    result = run(
        pipeline.run(OWNER_ID, "Who knows Python?", top_k=3, candidate_id="c-1")
    )

    assert result.has_evidence is True
    assert result.answer == "Jane Doe knows Python."
    assert result.query == "Who knows Python?"
    assert len(result.sources) == 2
    assert result.sources[0] == {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "chunk_index": 0,
        "score": 0.61,
        "source_type": "resume",
        "filename": "resume.txt",
    }
    assert "Candidate knows Python and FastAPI." in result.evidence_text
    assert llm.calls[0]["system_prompt"].startswith(
        "You answer questions for a recruitment team"
    )
    assert "Question: Who knows Python?" in llm.calls[0]["user_prompt"]
    assert retriever.calls[0]["top_k"] == 3
    assert retriever.calls[0]["candidate_id"] == "c-1"


def test_pipeline_strips_query():
    pipeline, retriever, _ = make_pipeline([])

    result = run(pipeline.run(OWNER_ID, "  padded query  "))

    assert result.query == "padded query"
    assert retriever.calls[0]["query"] == "padded query"


def test_pipeline_result_as_dict():
    result = PipelineResult(
        query="q",
        answer="a",
        has_evidence=True,
        sources=[{"document_id": "doc-1"}],
    )

    data = result.as_dict()

    assert data == {
        "query": "q",
        "has_evidence": True,
        "answer": "a",
        "sources": [{"document_id": "doc-1"}],
    }


def test_pipeline_singleton():
    reset_rag_pipeline()
    first = get_rag_pipeline()
    second = get_rag_pipeline()

    assert first is second

    set_rag_pipeline(RagPipeline())
    assert get_rag_pipeline() is not first

    reset_rag_pipeline()
