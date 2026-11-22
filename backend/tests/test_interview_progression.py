"""Regression tests for interview question delivery and progression.

Covers the "Question N of 10 with no question on screen" failure:

* Question 1 is always the deterministic opening question and never needs an
  LLM call,
* the session pointer is reconciled with the stored questions,
* a pointer that is ahead of the stored questions regenerates the missing one,
* a pointer that is behind the first unanswered question is repaired.
"""

import asyncio

from app.services import interview_service


def _row(number, *, answered=False, total=10):
    return {
        "question_number": number,
        "total_questions": total,
        "question_type": "technical",
        "question_text": f"Question {number}?",
        "difficulty": interview_service._difficulty_for_question(number),
        "answered": answered,
        "answer_text": "answer" if answered else None,
        "score": None,
        "feedback": None,
        "answered_at": "2026-01-01T00:00:00Z" if answered else None,
        "evaluation": None,
    }


def test_opening_question_is_the_fixed_first_question():
    question = interview_service._opening_question()

    assert question["question_number"] == 1
    assert question["question_text"] == "Tell me about yourself."
    assert question["question_type"] == "self_introduction"
    assert question["difficulty"] == "Easy"


def _install_fakes(monkeypatch, rows, generated_calls, pointer_updates):
    store = list(rows)

    def fake_list(user_id, session_id):
        return [dict(row) for row in store]

    def fake_store(user_id, session_id, questions):
        store.extend(dict(question) for question in questions)

    async def fake_generate(context, numbers):
        generated_calls.append(list(numbers))
        return [_row(number) for number in sorted(numbers)]

    def fake_set_number(user_id, session_id, number):
        pointer_updates.append(number)

    monkeypatch.setattr(interview_service, "_list_question_rows", fake_list)
    monkeypatch.setattr(interview_service, "_store_questions", fake_store)
    monkeypatch.setattr(interview_service, "_generate_question_batch", fake_generate)
    monkeypatch.setattr(interview_service, "_set_current_question_number", fake_set_number)
    return store


def test_first_question_is_stored_without_an_llm_call(monkeypatch):
    generated = []
    pointers = []
    store = _install_fakes(monkeypatch, [], generated, pointers)

    row = asyncio.run(
        interview_service._resolve_current_question(
            "user", "session", {"total_questions": 10, "current_question_number": 0}
        )
    )

    assert row is not None
    assert row["question_number"] == 1
    assert row["question_text"] == "Tell me about yourself."
    assert generated == []  # no LLM call for Question 1
    assert [item["question_number"] for item in store] == [1]
    assert pointers == [1]


def test_pointer_ahead_of_stored_questions_regenerates_the_missing_question(monkeypatch):
    generated = []
    pointers = []
    store = _install_fakes(monkeypatch, [_row(1, answered=True)], generated, pointers)

    row = asyncio.run(
        interview_service._resolve_current_question(
            "user", "session", {"total_questions": 10, "current_question_number": 2}
        )
    )

    assert row is not None
    assert row["question_number"] == 2
    assert generated == [[2]]
    assert sorted(item["question_number"] for item in store) == [1, 2]
    assert pointers == []


def test_pointer_behind_first_unanswered_question_is_repaired(monkeypatch):
    generated = []
    pointers = []
    rows = [_row(1), _row(2), _row(3)]
    _install_fakes(monkeypatch, rows, generated, pointers)

    row = asyncio.run(
        interview_service._resolve_current_question(
            "user", "session", {"total_questions": 10, "current_question_number": 2}
        )
    )

    assert row is not None
    assert row["question_number"] == 1
    assert generated == []
    assert pointers == [1]


def test_answered_questions_are_never_redelivered(monkeypatch):
    generated = []
    pointers = []
    rows = [_row(1, answered=True), _row(2, answered=True), _row(3)]
    _install_fakes(monkeypatch, rows, generated, pointers)

    row = asyncio.run(
        interview_service._resolve_current_question(
            "user", "session", {"total_questions": 10, "current_question_number": 2}
        )
    )

    assert row is not None
    assert row["question_number"] == 3
    assert pointers == [3]


def test_all_questions_answered_has_no_pending_question(monkeypatch):
    generated = []
    pointers = []
    rows = [_row(number, answered=True) for number in range(1, 11)]
    _install_fakes(monkeypatch, rows, generated, pointers)

    row = asyncio.run(
        interview_service._resolve_current_question(
            "user", "session", {"total_questions": 10, "current_question_number": 10}
        )
    )

    assert row is None
    assert generated == []
