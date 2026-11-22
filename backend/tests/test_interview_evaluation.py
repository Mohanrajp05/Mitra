"""Regression tests for the mock interview answer evaluation and scoring.

Covers the "unreliable / inflated interview scoring" failures:

* empty / meaningless answers must never receive positive technical scores,
* partially correct answers must get proportionate scores,
* technically correct detailed answers must score high (never inflated),
* unrelated answers must score low,
* out-of-range or invalid LLM responses must never inflate the score.
"""

import asyncio

import pytest

from app.rag.llm import LLMError
from app.schemas.interview import InterviewAnswerEvaluation
from app.services import interview_service as service


QUESTION = {
    "question_number": 1,
    "question_type": "self_introduction",
    "question_text": "Tell me about yourself.",
    "difficulty": "Easy",
}

CONTEXT = {"candidate_name": "Mohan", "candidate_role": "UI/UX Developer"}


class FakeLLMClient:
    def __init__(self, evaluation=None, error=None):
        self.evaluation = evaluation
        self.error = error
        self.calls = 0

    async def complete_structured(self, model_cls, system_prompt, user_prompt, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if isinstance(self.evaluation, InterviewAnswerEvaluation):
            return self.evaluation
        return InterviewAnswerEvaluation(**self.evaluation)


def _install_client(monkeypatch, client):
    monkeypatch.setattr(service, "get_llm_client", lambda: client)
    monkeypatch.setattr(service, "_llm_settings_kwargs", lambda: {})


def _answered_row(number: int, evaluation=None) -> dict:
    return {
        "question_number": number,
        "question_text": f"Question {number}",
        "answer_text": "answer",
        "answered_at": "2026-01-01T00:00:00Z",
        "evaluation": evaluation,
    }


def _evaluate(client, answer: str) -> dict:
    return asyncio.run(service._evaluate_interview_answer(CONTEXT, QUESTION, answer))


# --------------------------------------------------------------------------- #
# 1. All answers are meaningless -> very low overall score.
# --------------------------------------------------------------------------- #
def test_all_meaningless_answers_produce_very_low_overall_score():
    evaluations = [
        service._meaningless_answer_evaluation(QUESTION["question_text"]) for _ in range(10)
    ]
    rows = [
        _answered_row(number, evaluation) for number, evaluation in enumerate(evaluations, start=1)
    ]
    final_score, category_scores = service._final_interview_score(rows)

    assert final_score <= 10.0
    assert final_score < 5.0, f"meaningless interview must not score like a passing interview ({final_score})"
    assert all(value == 0.0 for value in category_scores.values())


def test_meaningless_answers_get_zero_score_and_no_strengths():
    for answer in ("hi", "yes", "good", "wait", "out of range", "ok", "idk", ""):
        evaluation = _evaluate(FakeLLMClient(), answer)

        assert evaluation["score"] == 0.0, f"answer {answer!r} must not score positively"
        assert all(value == 0.0 for value in evaluation["categories"].values())
        assert evaluation["feedback"]["what_went_well"] == ""
        assert evaluation["feedback"]["improvements"]
        assert evaluation["feedback"]["missing_points"]


# --------------------------------------------------------------------------- #
# 2. All answers are empty -> zero / minimum score.
# --------------------------------------------------------------------------- #
def test_empty_answers_score_zero():
    evaluation = _evaluate(FakeLLMClient(), "   ")

    assert evaluation["score"] == 0.0
    assert evaluation["categories"] == {
        category: 0.0 for category in service.INTERVIEW_CATEGORIES
    }
    assert evaluation["feedback"]["what_went_well"] == ""
    assert evaluation["feedback"]["missing_points"]


def test_empty_answer_interview_aggregates_to_zero():
    rows = [_answered_row(number, None) for number in range(1, 11)]
    final_score, category_scores = service._final_interview_score(rows)
    assert final_score == 0.0
    assert final_score <= 0.0


# --------------------------------------------------------------------------- #
# 3. Partially correct answers -> proportionate scores.
# --------------------------------------------------------------------------- #
def test_partially_correct_answers_get_proportionate_scores(monkeypatch):
    client = FakeLLMClient(
        InterviewAnswerEvaluation(
            score=4.0,
            categories={
                "technical_knowledge": 4.0,
                "problem_solving": 3.0,
                "project_practical": 2.0,
                "communication": 3.0,
                "behavioural": 2.0,
            },
        )
    )
    _install_client(monkeypatch, client)

    evaluation = _evaluate(client, "I have touched React a little but I cannot recall the details.")

    expected = service._score_from_categories(evaluation["categories"])
    assert evaluation["score"] == pytest.approx(expected)
    assert evaluation["score"] < 5.0
    assert evaluation["score"] > 0.0


# --------------------------------------------------------------------------- #
# 4. Technically correct detailed answers -> high scores, never inflated.
# --------------------------------------------------------------------------- #
def test_technically_correct_detailed_answers_score_high(monkeypatch):
    client = FakeLLMClient(
        InterviewAnswerEvaluation(
            score=9.0,
            categories={
                "technical_knowledge": 9.0,
                "problem_solving": 8.0,
                "project_practical": 9.0,
                "communication": 8.0,
                "behavioural": 8.0,
            },
        )
    )
    _install_client(monkeypatch, client)

    evaluation = _evaluate(client, "I led the migration of our design system to React with zero downtime.")

    # The score is derived from the clamped category subscores, not from the raw
    # model value, so a high but honest answer lands on the documented scale.
    assert evaluation["score"] == pytest.approx(service._score_from_categories(evaluation["categories"]))
    assert evaluation["score"] >= 7.0


# --------------------------------------------------------------------------- #
# 5. Unrelated answers -> low scores.
# --------------------------------------------------------------------------- #
def test_unrelated_or_vague_answers_score_low(monkeypatch):
    client = FakeLLMClient(
        InterviewAnswerEvaluation(
            score=2.0,
            categories={
                "technical_knowledge": 2.0,
                "problem_solving": 1.0,
                "project_practical": 1.0,
                "communication": 2.0,
                "behavioural": 1.0,
            },
        )
    )
    _install_client(monkeypatch, client)

    evaluation = _evaluate(client, "I do not really know much about that topic honestly.")

    assert evaluation["score"] < 5.0
    assert evaluation["score"] < 5.0


# --------------------------------------------------------------------------- #
# 6. Invalid JSON / out-of-range LLM output -> safe validation, never inflated.
# --------------------------------------------------------------------------- #
def test_out_of_range_llm_categories_are_clamped(monkeypatch):
    client = FakeLLMClient(
        InterviewAnswerEvaluation(
            score=9.0,
            categories={
                "technical_knowledge": 15.0,
                "problem_solving": -5.0,
                "project_practical": 8.0,
                "communication": 12.0,
                "behavioural": 2.0,
            },
        )
    )
    _install_client(monkeypatch, client)

    evaluation = _evaluate(client, "I built a React app with Redux and tested it with Jest.")

    assert client.calls == 1
    assert all(0.0 <= value <= 10.0 for value in evaluation["categories"].values())
    assert evaluation["categories"]["technical_knowledge"] == 10.0
    assert evaluation["categories"]["problem_solving"] == 0.0
    assert evaluation["categories"]["communication"] == 10.0
    assert evaluation["score"] <= 10.0


def test_invalid_llm_response_does_not_inflate_score(monkeypatch):
    client = FakeLLMClient(error=LLMError("The AI service did not return valid JSON."))
    _install_client(monkeypatch, client)

    with pytest.raises(LLMError):
        asyncio.run(service._evaluate_interview_answer(CONTEXT, QUESTION, "I have used React for four years."))

    # An unscored / failed evaluation must never push the final score up.
    final_score, _category_scores = service._final_interview_score([_answered_row(1, None)])
    assert final_score == 0.0


def test_final_score_is_weighted_average_of_category_scores():
    rows = [
        _answered_row(1, {"categories": {"technical_knowledge": 8.0, "problem_solving": 8.0, "project_practical": 8.0, "communication": 8.0, "behavioural": 8.0}}),
        _answered_row(2, {"categories": {"technical_knowledge": 4.0, "problem_solving": 4.0, "project_practical": 4.0, "communication": 4.0, "behavioural": 4.0}}),
    ]
    final_score, category_scores = service._final_interview_score(rows)

    assert category_scores["technical_knowledge"] == 6.0
    assert final_score == pytest.approx(6.0)
