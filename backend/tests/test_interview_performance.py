"""Regression tests for interview latency optimisations.

These cover the pieces that make Start Interview fast without changing the
10-question/interview-scoring rules:

* a bounded question batch (Question 1 alone, then 2-10 in the background),
* the content-hash document cache that avoids re-parsing a resume.
"""

import asyncio

import pytest

from app.rag import document_cache
from app.schemas.interview import InterviewQuestion, InterviewQuestionsPayload
from app.services import interview_service


@pytest.fixture(autouse=True)
def _clean_cache():
    document_cache.clear()
    yield
    document_cache.clear()
    interview_service._PREFETCH_TASKS.clear()
    interview_service._PENDING_EVALUATIONS.clear()


def test_document_cache_reuses_extracted_text_and_profile():
    calls = {"extract": 0}

    def extractor(text):
        calls["extract"] += 1
        return {"candidate_name": "Mohan", "chars": len(text)}

    document_cache.set_document_text("hash-1", "resume text")

    first = document_cache.get_or_extract_profile("hash-1", extractor, "resume text")
    second = document_cache.get_or_extract_profile("hash-1", extractor, "resume text")

    assert first == second == {"candidate_name": "Mohan", "chars": 11}
    assert calls["extract"] == 1


def test_document_cache_invalidates_on_replace_or_delete():
    document_cache.set_document_text("hash-2", "old resume")
    document_cache.get_or_extract_profile("hash-2", lambda text: {"text": text}, "old resume")

    document_cache.invalidate("hash-2")

    assert document_cache.get_document_text("hash-2") is None
    assert document_cache.get_profile("hash-2") is None


def test_question_prompts_only_ask_for_requested_numbers():
    system_prompt, user_prompt = interview_service._question_prompts({}, [1])

    assert "Generate exactly 1" in system_prompt
    assert "question_number 1" in user_prompt
    assert "question_number 2" not in user_prompt
    assert "difficulty=Easy" in user_prompt


def test_question_batch_uses_one_llm_call_for_one_question(monkeypatch):
    calls = []

    class FakeClient:
        async def complete_structured(self, model_cls, system_prompt, user_prompt, **kwargs):
            calls.append((system_prompt, user_prompt))
            return InterviewQuestionsPayload(
                questions=[
                    InterviewQuestion(
                        question_number=1,
                        question_type="self_introduction",
                        question_text="Introduce yourself.",
                        difficulty="Hard",
                    )
                ]
            )

    monkeypatch.setattr(interview_service, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(interview_service, "_llm_settings_kwargs", lambda: {})

    questions = asyncio.run(
        interview_service._generate_question_batch({"candidate_name": "Mohan"}, [1])
    )

    assert len(calls) == 1
    assert len(questions) == 1
    assert questions[0]["question_number"] == 1
    # Difficulty is deterministic by question number, never trusted from the model.
    assert questions[0]["difficulty"] == "Easy"


def test_question_batch_rejects_incomplete_plans(monkeypatch):
    class FakeClient:
        async def complete_structured(self, model_cls, system_prompt, user_prompt, **kwargs):
            return InterviewQuestionsPayload(
                questions=[
                    InterviewQuestion(
                        question_number=1,
                        question_text="Introduce yourself.",
                    )
                ]
            )

    monkeypatch.setattr(interview_service, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(interview_service, "_llm_settings_kwargs", lambda: {})

    with pytest.raises(interview_service.InterviewError):
        asyncio.run(
            interview_service._generate_question_batch({"candidate_name": "Mohan"}, [1, 2])
        )


def test_question_generation_timeout_is_reported(monkeypatch):
    class SlowClient:
        async def complete_structured(self, model_cls, system_prompt, user_prompt, **kwargs):
            await asyncio.sleep(5)

    monkeypatch.setattr(interview_service, "get_llm_client", lambda: SlowClient())
    monkeypatch.setattr(interview_service, "_llm_settings_kwargs", lambda: {})
    monkeypatch.setattr(interview_service, "QUESTION_GENERATION_TIMEOUT", 0.05)

    with pytest.raises(interview_service.InterviewError, match="took too long"):
        asyncio.run(
            interview_service._generate_question_batch({"candidate_name": "Mohan"}, [1])
        )
