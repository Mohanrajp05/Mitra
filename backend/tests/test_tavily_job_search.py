import asyncio

import httpx
import pytest

from app.rag.pipeline import PipelineResult
from app.schemas.chat import ChatMessageCreate
from app.services import chat_service
from app.services import job_search_service as js
from app.services.guardrails import classify_message
from app.services.job_search_service import (
    JobPreferences,
    TavilyError,
    build_queries,
    extract_preferences,
    is_job_search,
    job_sources,
    missing_essential,
    search_jobs,
)


def test_job_search_intent_detection():
    assert is_job_search("Find software engineer jobs for freshers in Bengaluru.")
    assert is_job_search("I'm looking for full-time Python developer opportunities.")
    assert is_job_search("Show only Naukri job listings.")
    assert is_job_search("What are the latest software engineering opportunities?")
    assert not is_job_search("Summarize this resume.")
    assert not is_job_search("Which candidates have Python experience?")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("I'm a software engineer intern. I have completed my internship at XYZ company. Now I'm searching for a job in software development. Please find and list the jobs currently available for freshers.", True),
        ("I am looking for a job.", True),
        ("I completed my internship and need a full-time job.", True),
        ("Find jobs suitable for freshers.", True),
        ("Show current software developer openings.", True),
        ("Are companies hiring junior Python developers?", True),
        ("Help me find entry-level AI Engineer opportunities.", True),
        ("I am unemployed and searching for a developer role.", True),
        ("Find jobs matching my experience.", True),
        ("List available vacancies for recent graduates.", True),
        ("Explain Python.", False),
        ("Summarize this resume.", False),
        ("What skills does this candidate have?", False),
        ("Compare this resume with the selected job.", False),
    ],
)
def test_natural_language_intent_examples(message, expected):
    assert classify_message(message) == ("job_search" if expected else "recruitment" if "resume" in message.casefold() or "skills" in message.casefold() or "compare" in message.casefold() else "general")


def test_long_example_extracts_preferences_without_inventing_skills():
    prefs = extract_preferences("I'm a software engineer intern. I have completed my internship at XYZ company. "
    "Now I'm searching for a job in software development. Please find and list the jobs currently available for freshers.")
    
    assert prefs.role == "Software Engineer"
    assert prefs.experience == "Fresher / entry-level"
    assert prefs.previous_company == "XYZ"
    assert prefs.skills == []


def test_preference_extraction_and_merge():
    prefs = extract_preferences(
        "I'm a Software Engineer Intern. I completed my internship and want a full-time job. Skills: Python, FastAPI. Bengaluru."
    )
    assert prefs.role == "Software Engineer"
    assert "Python" in prefs.skills
    assert "FastAPI" in prefs.skills
    assert prefs.employment_type == "Full-time"
    assert prefs.location == "Bengaluru"
    assert prefs.experience == "Fresher / entry-level"

    updated = extract_preferences("Show only remote jobs on Naukri.", prefs)
    assert updated.remote is True
    assert updated.platform == "naukri"
    assert updated.role == "Software Engineer"


def test_missing_location_is_asked():
    prefs = extract_preferences("Find software engineer jobs.")
    assert missing_essential(prefs) == "location"
    prefs = extract_preferences("Bengaluru", prefs)
    assert missing_essential(prefs) == ""


def test_query_building_uses_preferences():
    prefs = JobPreferences(
        role="Python Developer",
        skills=["Python", "FastAPI"],
        experience="Fresher / entry-level",
        location="Bengaluru",
        platform="naukri",
    )
    queries = build_queries(prefs)
    assert any("Python Developer" in query and "Bengaluru" in query for query in queries)
    assert any("naukri" in query for query in queries)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", js.TAVILY_API_URL), response=httpx.Response(self.status_code)
            )


class FakeAsyncClient:
    payload = {"results": []}
    status_code = 200

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        assert url == js.TAVILY_API_URL
        assert json["api_key"]
        return FakeResponse(self.payload, self.status_code)


def test_search_jobs_parses_deduplicates_and_ranks(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    js.clear_cache()
    FakeAsyncClient.payload = {
        "results": [
            {
                "title": "Software Engineer at Acme Corp - Bengaluru",
                "url": "https://www.naukri.com/software-engineer-jobs-at-acme",
                "content": "Full-time role for freshers with Python and FastAPI in Bengaluru. Salary ₹6 LPA.",
                "score": 0.8,
            },
            {
                "title": "Software Engineer at Acme Corp - Bengaluru",
                "url": "https://www.naukri.com/software-engineer-jobs-at-acme?utm=1",
                "content": "Duplicate listing.",
                "score": 0.7,
            },
            {
                "title": "Data Analyst at Other Co",
                "url": "https://www.linkedin.com/jobs/view/123",
                "content": "Experienced analyst in Mumbai.",
                "score": 0.6,
            },
        ]
    }
    monkeypatch.setattr(js.httpx, "AsyncClient", FakeAsyncClient)

    prefs = JobPreferences(
        role="Software Engineer",
        skills=["Python", "FastAPI"],
        experience="Fresher / entry-level",
        location="Bengaluru",
    )
    results = asyncio.run(search_jobs(prefs))

    assert len(results) == 2
    assert results[0]["title"].startswith("Software Engineer")
    assert results[0]["source"] == "naukri"
    assert results[0]["url"].startswith("https://")
    assert job_sources(results)[0]["kind"] == "job"


def test_search_jobs_requires_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    js.clear_cache()
    with pytest.raises(TavilyError):
        asyncio.run(search_jobs(JobPreferences(role="Software Engineer", location="Bengaluru")))


def test_search_jobs_reports_invalid_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "bad-key")
    js.clear_cache()
    FakeAsyncClient.status_code = 401
    monkeypatch.setattr(js.httpx, "AsyncClient", FakeAsyncClient)
    with pytest.raises(TavilyError, match="configured correctly"):
        asyncio.run(search_jobs(JobPreferences(role="Software Engineer", location="Bengaluru")))
    FakeAsyncClient.status_code = 200


@pytest.mark.asyncio
async def test_job_search_is_routed_before_rag(monkeypatch):
    listing = {
        "kind": "job",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "Bengaluru",
        "experience": "Fresher / entry-level",
        "employment_type": "Full-time",
        "salary": "Not specified",
        "description": "Python role",
        "skills": ["Python"],
        "url": "https://www.naukri.com/software-engineer-jobs",
        "source": "naukri",
        "search_date": "2026-11-19",
    }

    async def fake_search(prefs):
        assert prefs.role == "Software Engineer"
        return [listing]

    monkeypatch.setattr(chat_service, "search_jobs", fake_search)
    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    captured = {}

    def fake_persist(owner, session, content, result):
        captured["result"] = result
        return {"user_message": {}, "assistant_message": {}}

    monkeypatch.setattr(chat_service, "_persist_exchange", fake_persist)

    await chat_service.send_message(
        "11111111-1111-4111-8111-111111111111",
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        ChatMessageCreate(content="Find software engineer jobs for freshers in Bengaluru."),
    )

    result = captured["result"]
    assert result.has_evidence is True
    assert result.sources[0]["kind"] == "job"
    assert result.sources[-1]["kind"] == "job_preferences"


@pytest.mark.asyncio
async def test_job_search_clarifies_missing_location(monkeypatch):
    captured = {}

    def fake_persist(owner, session, content, result):
        captured["result"] = result
        return {"user_message": {}, "assistant_message": {}}

    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    monkeypatch.setattr(chat_service, "_persist_exchange", fake_persist)

    await chat_service.send_message(
        "11111111-1111-4111-8111-111111111111",
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        ChatMessageCreate(content="Find software engineer jobs."),
    )

    assert captured["result"].has_evidence is False
    assert captured["result"].sources[0]["kind"] == "job_search_prompt"


def test_internship_experience_is_not_treated_as_internship_search():
    prefs = extract_preferences(
        "I have internship experience in React and FastAPI. Find entry-level full-stack developer jobs."
    )
    assert prefs.employment_type == ""
    assert prefs.experience == "Fresher / entry-level"
    assert all("Internship" not in query for query in build_queries(prefs))

    wanted = extract_preferences("Find internship jobs for Python developers in Pune.")
    assert wanted.employment_type == "Internship"


def test_fresher_and_graduate_plurals_are_detected():
    assert extract_preferences("Find jobs suitable for freshers.").experience == "Fresher / entry-level"
    assert extract_preferences("List openings for recent graduates.").experience == "Fresher / entry-level"


@pytest.mark.asyncio
async def test_clarification_follow_up_retains_preferences(monkeypatch):
    captured = {}

    async def fake_search(prefs):
        captured["prefs"] = prefs
        return []

    monkeypatch.setattr(chat_service, "search_jobs", fake_search)
    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    monkeypatch.setattr(
        chat_service,
        "_persist_exchange",
        lambda owner, session, content, result: {"user_message": {}, "assistant_message": {}},
    )

    await chat_service.send_message(
        "11111111-1111-4111-8111-111111111111",
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        ChatMessageCreate(
            content="Bengaluru",
            job_search=True,
            job_preferences={"role": "Software Engineer", "experience": "Fresher / entry-level"},
        ),
    )

    assert captured["prefs"].role == "Software Engineer"
    assert captured["prefs"].location == "Bengaluru"
    assert missing_essential(captured["prefs"]) == ""
