"""Tests for the mock interview Part 2 endpoints (questions, answers, scoring)."""

from app.api import interviews as interview_api
from app.main import app
from app.schemas.interview import InterviewAnswerResponse
from app.services.interview_service import (
    InterviewQuestionNotFoundError,
    InterviewSessionNotFoundError,
    InterviewStateError,
)
from tests.conftest import TEST_USER_ID

OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

QUESTION_NUMBER = 1

QUESTION = {
    "question_number": QUESTION_NUMBER,
    "total_questions": 10,
    "question_type": "self_introduction",
    "question_text": "Introduce yourself and explain your technical background.",
    "difficulty": "Easy",
    "answered": False,
    "answer_text": None,
    "score": None,
    "feedback": None,
    "answered_at": None,
}

SESSION = {
    "id": SESSION_ID,
    "user_id": TEST_USER_ID,
    "document_id": None,
    "resume_filename": "resume.pdf",
    "candidate_role": "Backend Engineer",
    "status": "in_progress",
    "interview_type": "Technical + HR",
    "difficulty": "Adaptive",
    "mode": "Text-based",
    "current_question_number": QUESTION_NUMBER,
    "total_questions": 10,
    "final_score": None,
    "evaluation_report": None,
    "extracted_info": None,
    "created_at": "2026-11-20T10:00:00Z",
    "updated_at": "2026-11-20T10:00:00Z",
    "completed_at": None,
}

START_RESULT = {
    "session": SESSION,
    "questions": [QUESTION],
    "message": "Interview session started.",
}

ANSWER_RESULT = InterviewAnswerResponse(
    question=QUESTION,
    answered=True,
    advanced=True,
    next_question_number=2,
)

REPORT = {
    "session_id": SESSION_ID,
    "status": "completed",
    "score": 72.5,
    "level": "Good",
    "questions_answered": 10,
    "questions_total": 10,
    "answered_question_numbers": list(range(1, 11)),
    "unanswered_question_numbers": [],
    "category_scores": {
        "technical_knowledge": 70.0,
        "problem_solving": 65.0,
        "project_practical": 60.0,
        "communication": 80.0,
        "behavioural": 75.0,
    },
    "category_weights": {
        "technical_knowledge": 30,
        "problem_solving": 20,
        "project_practical": 20,
        "communication": 15,
        "behavioural": 15,
    },
    "strengths": ["Clear communication of experience."],
    "areas_for_improvement": ["Deepen backend architecture depth."],
    "answered_questions": [],
    "recommendations": ["Targeted improvement: system design basics."],
    "completed_at": "2026-11-20T11:30:00Z",
}


def test_remove_resume_returns_awaiting_session(client, monkeypatch):
    async def fake_remove(user_id, session_id):
        return {
            **SESSION,
            "status": "awaiting_resume",
            "document_id": None,
            "resume_filename": None,
            "extracted_info": None,
        }

    monkeypatch.setattr(interview_api.interview_service, "remove_resume", fake_remove)

    response = client.delete(f"/api/interviews/sessions/{SESSION_ID}/resume")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_resume"
    assert body["resume_filename"] is None
    assert body["document_id"] is None


def test_remove_resume_rejects_in_progress(client, monkeypatch):
    async def failing_remove(user_id, session_id):
        raise InterviewStateError("Finish the current interview before removing the resume.")

    monkeypatch.setattr(interview_api.interview_service, "remove_resume", failing_remove)

    response = client.delete(f"/api/interviews/sessions/{SESSION_ID}/resume")

    assert response.status_code == 400


def test_list_questions_returns_questions(client, monkeypatch):
    async def fake_list(user_id, session_id):
        return [{
            "question_number": 1,
            "total_questions": 10,
            "question_type": "self_introduction",
            "question_text": "Introduce yourself.",
            "difficulty": "Easy",
            "answered": False,
            "answer_text": None,
            "score": None,
            "feedback": {"what_went_well": "", "improvements": [], "missing_points": []},
            "answered_at": None,
        }]

    monkeypatch.setattr(interview_api.interview_service, "list_questions_for_session", fake_list)

    response = client.get(f"/api/interviews/sessions/{SESSION_ID}/questions")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["question_number"] == 1


def test_start_returns_503_when_generation_fails_without_leaking_details(client, monkeypatch):
    from app.rag.llm import LLMError

    async def failing_start(user_id, session_id):
        raise LLMError("provider key sk-secret leaked at https://api.portkey.ai/v1")

    monkeypatch.setattr(interview_api.interview_service, "start_session", failing_start)

    response = client.post(f"/api/interviews/sessions/{SESSION_ID}/start")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "sk-secret" not in detail
    assert "portkey" not in detail.lower()
    assert response.headers.get("retry-after") == "5"


def test_start_is_idempotent_when_already_in_progress(client, monkeypatch):
    async def existing_start(user_id, session_id):
        return {
            "session": SESSION,
            "questions": [QUESTION],
            "message": "Interview session started.",
        }

    monkeypatch.setattr(interview_api.interview_service, "start_session", existing_start)

    first = client.post(f"/api/interviews/sessions/{SESSION_ID}/start")
    second = client.post(f"/api/interviews/sessions/{SESSION_ID}/start")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(first.json()["questions"]) == len(second.json()["questions"]) == 1


def test_answer_reports_unready_next_question_without_failing(client, monkeypatch):
    async def saved_but_unready(user_id, session_id, question_number, answer_text):
        return InterviewAnswerResponse(
            question=QUESTION,
            answered=True,
            advanced=True,
            next_question_number=2,
            next_question_ready=False,
            evaluation_pending=True,
        )

    monkeypatch.setattr(
        interview_api.interview_service, "submit_answer", saved_but_unready
    )

    response = client.post(
        f"/api/interviews/sessions/{SESSION_ID}/questions/{QUESTION_NUMBER}/answer",
        json={"answer_text": "My answer is saved even without a next question."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert body["next_question_ready"] is False
    assert body["evaluation_pending"] is True


def test_difficulty_progression_is_easy_medium_hard():
    from app.services import interview_service

    expected = {
        1: "Easy", 2: "Easy", 3: "Easy",
        4: "Medium", 5: "Medium", 6: "Medium", 7: "Medium",
        8: "Hard", 9: "Hard", 10: "Hard",
    }
    for number, difficulty in expected.items():
        assert interview_service._difficulty_for_question(number) == difficulty


def test_start_returns_generated_questions(client, monkeypatch):
    async def fake_start(user_id, session_id):
        return START_RESULT

    monkeypatch.setattr(interview_api.interview_service, "start_session", fake_start)

    response = client.post(f"/api/interviews/sessions/{SESSION_ID}/start")

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["status"] == "in_progress"
    assert len(body["questions"]) == 1
    assert body["questions"][0]["question_number"] == QUESTION_NUMBER


def test_start_rejects_session_that_is_not_ready(client, monkeypatch):
    async def failing_start(user_id, session_id):
        raise InterviewStateError("Upload and process a resume before starting the interview.")

    monkeypatch.setattr(interview_api.interview_service, "start_session", failing_start)

    response = client.post(f"/api/interviews/sessions/{SESSION_ID}/start")

    assert response.status_code == 400
    assert "Upload and process a resume" in response.json()["detail"]


def test_start_returns_404_for_missing_session(client, monkeypatch):
    async def missing_start(user_id, session_id):
        raise InterviewSessionNotFoundError("Interview session not found.")

    monkeypatch.setattr(interview_api.interview_service, "start_session", missing_start)

    response = client.post(f"/api/interviews/sessions/{SESSION_ID}/start")

    assert response.status_code == 404


def test_current_question_returns_question(client, monkeypatch):
    async def fake_current(user_id, session_id):
        return QUESTION

    monkeypatch.setattr(interview_api.interview_service, "get_current_question", fake_current)

    response = client.get(f"/api/interviews/sessions/{SESSION_ID}/questions/current")

    assert response.status_code == 200
    assert response.json()["question_number"] == QUESTION_NUMBER
    assert response.json()["question_text"].startswith("Introduce yourself")


def test_answer_question_returns_evaluation_and_progress(client, monkeypatch):
    seen = {}

    async def fake_answer(user_id, session_id, question_number, answer_text):
        seen["user"] = user_id
        seen["session"] = session_id
        seen["question"] = question_number
        seen["answer"] = answer_text
        return ANSWER_RESULT

    monkeypatch.setattr(interview_api.interview_service, "submit_answer", fake_answer)

    response = client.post(
        f"/api/interviews/sessions/{SESSION_ID}/questions/{QUESTION_NUMBER}/answer",
        json={"answer_text": "I am a backend engineer with Python experience."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert body["advanced"] is True
    assert body["next_question_number"] == 2
    assert body["question"]["question_number"] == QUESTION_NUMBER
    assert seen["answer"] == "I am a backend engineer with Python experience."


def test_answer_question_rejects_missing_session(client, monkeypatch):
    async def missing_answer(user_id, session_id, question_number, answer_text):
        raise InterviewSessionNotFoundError("Interview session not found.")

    monkeypatch.setattr(interview_api.interview_service, "submit_answer", missing_answer)

    response = client.post(
        f"/api/interviews/sessions/{SESSION_ID}/questions/{QUESTION_NUMBER}/answer",
        json={"answer_text": "I am a backend engineer."},
    )

    assert response.status_code == 404


def test_complete_returns_final_report(client, monkeypatch):
    async def fake_complete(user_id, session_id):
        return REPORT

    monkeypatch.setattr(interview_api.interview_service, "complete_interview", fake_complete)

    response = client.post(f"/api/interviews/sessions/{SESSION_ID}/complete")

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 72.5
    assert body["level"] == "Good"
    assert body["questions_answered"] == 10
    assert body["category_scores"]["technical_knowledge"] == 70.0


def test_complete_rejects_completed_session(client, monkeypatch):
    async def completed_complete(user_id, session_id):
        raise InterviewStateError("This interview session has already been completed.")

    monkeypatch.setattr(interview_api.interview_service, "complete_interview", completed_complete)

    response = client.post(f"/api/interviews/sessions/{SESSION_ID}/complete")

    assert response.status_code == 400

