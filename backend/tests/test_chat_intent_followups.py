import asyncio

import pytest

from app.rag.pipeline import RagPipeline
from app.rag.pipeline import PipelineResult
from app.schemas.chat import ChatMessageCreate
from app.services import chat_service
from app.services.job_search_service import (
    JobPreferences,
    build_queries,
    extract_preferences,
    format_job_answer,
    is_job_search,
    missing_essential,
    search_jobs,
)

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

WEB_DEV_INTERN_INTERN_REQUEST = (
    "My name is Mohan. I have completed a web development internship at a startup, "
    "and I am searching for fresher jobs in the same role. Please list companies hiring for this role."
)


def test_web_development_role_extracted_from_internship_request():
    prefs = extract_preferences(WEB_DEV_INTERN_INTERN_REQUEST)

    assert prefs.role == "Web Developer"
    assert prefs.experience == "Fresher / entry-level"


def test_pending_role_follow_up_answer_is_accepted():
    prefs = extract_preferences("Web Developer.")

    assert prefs.role == "Web Developer"


def test_react_developer_and_ai_engineer_roles_are_accepted():
    react = extract_preferences("I want React developer jobs for fresher candidates.")
    assert react.role == "React Developer"

    ai = extract_preferences("I am looking for AI Engineer opportunities for a fresher.")
    assert ai.role == "AI Engineer"


def test_ui_ux_developer_role_is_accepted():
    prefs = extract_preferences("Find UI/UX developer jobs in India.")

    assert prefs.role == "UI/UX Developer"


@pytest.mark.asyncio
async def test_unfamiliar_but_valid_role_is_not_rejected(monkeypatch):
    captured = {}

    async def fake_search(prefs):
        captured["prefs"] = prefs
        return []

    monkeypatch.setattr(chat_service, "search_jobs", fake_search)
    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    monkeypatch.setattr(
        chat_service, "_persist_exchange", lambda *args: {"user_message": {}, "assistant_message": {}}
    )

    await chat_service.send_message(
        TEST_USER_ID,
        SESSION_ID,
        ChatMessageCreate(content="Find Growth Hacker jobs in Bangalore.", job_search=True),
    )

    assert captured["prefs"].role == "Growth Hacker"
    assert captured["prefs"].location == "Bengaluru"
    assert missing_essential(captured["prefs"]) == ""


def test_job_search_intent_beats_resume_query():
    assert is_job_search("Find React developer jobs in India.")
    assert is_job_search(WEB_DEV_INTERN_INTERN_REQUEST)
    from app.services.guardrails import classify_message

    assert classify_message(WEB_DEV_INTERN_INTERN_REQUEST) == "job_search"
    assert classify_message("Summarize this resume.") == "recruitment"


def test_format_job_answer_lists_listing_details():
    prefs = JobPreferences(role="Web Developer", location="Bengaluru")
    listings = [
        {
            "kind": "job",
            "title": "Web Developer",
            "company": "Acme",
            "location": "Bengaluru",
            "experience": "Fresher / entry-level",
            "employment_type": "Full-time",
            "salary": "Not specified",
            "description": "Build web apps.",
            "skills": ["React"],
            "url": "https://www.naukri.com/web-developer-jobs",
            "source": "naukri",
            "search_date": "2026-11-22",
            "score": 0.9,
        }
    ]

    answer = format_job_answer(listings, prefs)

    assert "Acme" in answer
    assert "Web Developer" in answer
    assert "Bengaluru" in answer
    assert "Apply:" in answer
    assert "not verified open positions" in answer


def test_pending_job_search_context_is_detected():
    history = [
        {
            "role": "assistant",
            "content": "Which location do you prefer?",
            "sources": [{"kind": "job_search_prompt", "missing": ["location"]}],
        }
    ]

    assert chat_service._pending_job_search_missing(history) == "location"


def test_history_context_renders_prior_turns():
    pipeline = RagPipeline()
    history = [
        {"role": "user", "content": "I completed a web development internship."},
        {"role": "assistant", "content": "Which location do you prefer?"},
        {"role": "user", "content": "Bangalore."},
        {"role": "assistant", "content": "Great, here are fresher web developer roles in Bangalore."},
    ]

    context = RagPipeline._history_context(history, max_turns=6)

    assert "User: I completed a web development internship." in context
    assert "Assistant: Which location do you prefer?" in context
    assert "User: Bangalore." in context
    assert context.startswith("Conversation context so far")


@pytest.mark.asyncio
async def test_web_development_follow_up_runs_job_search(monkeypatch):
    captured = {}

    async def fake_search(prefs):
        captured["prefs"] = prefs
        return []

    monkeypatch.setattr(chat_service, "search_jobs", fake_search)
    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    monkeypatch.setattr(
        chat_service, "_persist_exchange", lambda *args: {"user_message": {}, "assistant_message": {}}
    )

    result = await chat_service.send_message(
        TEST_USER_ID,
        SESSION_ID,
        ChatMessageCreate(content="Web Developer in Bangalore", job_search=True),
    )

    assert captured["prefs"].role == "Web Developer"
    assert missing_essential(captured["prefs"]) == ""


@pytest.mark.asyncio
async def test_pending_location_follow_up_completes_search(monkeypatch):
    captured = {}

    async def fake_search(prefs):
        captured["prefs"] = prefs
        return []

    monkeypatch.setattr(chat_service, "search_jobs", fake_search)
    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    monkeypatch.setattr(
        chat_service, "_persist_exchange", lambda *args: {"user_message": {}, "assistant_message": {}}
    )

    history = [
        {
            "role": "assistant",
            "content": "Which location do you prefer?",
            "sources": [{"kind": "job_search_prompt", "missing": ["location"]}],
        },
        {
            "role": "user",
            "content": "Bangalore.",
            "sources": [],
        },
    ]

    result = await chat_service.send_message(
        TEST_USER_ID,
        SESSION_ID,
        ChatMessageCreate(
            content="Bangalore.",
            job_search=True,
            job_preferences={"role": "Web Developer", "experience": "Fresher / entry-level"},
        ),
    )

    assert captured["prefs"].role == "Web Developer"
    assert captured["prefs"].location == "Bengaluru"
    assert missing_essential(captured["prefs"]) == ""
