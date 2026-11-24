"""Regression tests for conversation memory and follow-up job search.

All external dependencies (LLM intent check, Tavily/JSearch, DB persistence) are
stubbed in-process.  These are NOT real external API tests.
"""

import asyncio

import pytest

from app.rag.pipeline import PipelineResult
from app.services import chat_service
from app.services.job_search_service import (
    JobPreferences,
    _pending_job_search_missing,
    build_session_context,
    format_company_vacancy_answer,
    is_career_info_question,
    is_company_listing_query,
    is_job_search,
    references_previous_companies,
)

OWNER_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

FIRST_MESSAGE = (
    "My name is Mohan. I completed a Web Development internship at a startup and am "
    "looking for a fresher job. Please list companies hiring for this role."
)

LISTING = {
    "kind": "job",
    "title": "Web Developer",
    "company": "Acme Corp",
    "location": "Bengaluru",
    "experience": "Fresher / entry-level",
    "employment_type": "Full-time",
    "salary": "Not specified",
    "description": "Graduate web role.",
    "skills": [],
    "url": "https://www.acme.com/jobs/1",
    "source": "jsearch",
    "search_date": "2026-11-23",
    "score": 1.0,
}

COMPANY_LISTING = {
    "kind": "company",
    "title": "Web Developer",
    "company": "Acme Corp",
    "location": "India",
    "experience": "Fresher / entry-level",
    "employment_type": None,
    "salary": None,
    "description": None,
    "skills": [],
    "url": "https://www.acme.com/careers",
    "source": "tavily",
    "search_date": "2026-11-23",
    "score": 0.9,
}

VACANCY_LISTING = {
    "kind": "job",
    "title": "Web Developer",
    "company": "Acme Corp",
    "location": "Bengaluru",
    "experience": "Fresher / entry-level",
    "employment_type": "Full-time",
    "salary": "Not specified",
    "description": "Graduate web role.",
    "skills": [],
    "url": "https://www.acme.com/jobs/2",
    "source": "jsearch",
    "search_date": "2026-11-23",
    "score": 1.0,
}


def _message(role, content, sources=None):
    return {"role": role, "content": content, "sources": sources or []}


def _install_harness(monkeypatch, history, searches, company_searches, vacancy_searches, rag_calls, verdict=False):
    async def fake_verdict(text, client=None, **kwargs):
        return verdict

    async def fake_search(prefs):
        searches.append(prefs)
        return [dict(LISTING)]

    async def fake_company(prefs):
        company_searches.append(prefs)
        return [dict(COMPANY_LISTING)]

    async def fake_vacancy(prefs, companies):
        vacancy_searches.append((prefs, [c.get("company") if isinstance(c, dict) else str(c) for c in companies]))
        return ([dict(VACANCY_LISTING)], {
            "requested": [c.get("company") if isinstance(c, dict) else str(c) for c in companies],
            "verified": [c.get("company") if isinstance(c, dict) else str(c) for c in companies],
            "unverified": [],
        })

    async def fake_rag(owner_user_id, content, **kwargs):
        rag_calls.append((content, kwargs.get("history")))
        return PipelineResult(query=content, answer="Answer from your uploaded documents.", has_evidence=True, sources=[])

    def fake_persist(owner, session, content, result):
        history.append({"role": "user", "content": content, "sources": []})
        history.append({"role": "assistant", "content": result.answer, "sources": result.sources})
        return {"user_message": {"content": content}, "assistant_message": {"content": result.answer, "sources": result.sources}}

    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    monkeypatch.setattr(chat_service, "_load_history", lambda *args: list(history))
    monkeypatch.setattr(chat_service, "_persist_exchange", fake_persist)
    monkeypatch.setattr(chat_service, "classify_unclear_message", fake_verdict)
    monkeypatch.setattr(chat_service, "search_jobs", fake_search)
    monkeypatch.setattr(chat_service, "search_hiring_companies", fake_company)
    monkeypatch.setattr(chat_service, "search_company_vacancies", fake_vacancy)
    monkeypatch.setattr(chat_service.rag_service, "query", fake_rag)


def test_pdf_three_message_flow(monkeypatch):
    history = []
    searches = []
    company_searches = []
    vacancy_searches = []
    rag_calls = []
    _install_harness(monkeypatch, history, searches, company_searches, vacancy_searches, rag_calls, verdict=False)

    # Turn 1: list companies hiring for the remembered role.
    r1 = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, __import__("app.schemas.chat", fromlist=["ChatMessageCreate"]).ChatMessageCreate(content=FIRST_MESSAGE)))
    assert (searches or company_searches), "expected a search on turn 1"
    first_search = (searches or company_searches)[0]
    assert first_search.role == "Web Developer"
    assert first_search.experience == "Fresher / entry-level"
    answer1 = r1["assistant_message"]["content"] if isinstance(r1, dict) else r1.answer
    assert "Acme Corp" in answer1

    # Turn 2: follow-up to the companies listed above.
    r2 = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, __import__("app.schemas.chat", fromlist=["ChatMessageCreate"]).ChatMessageCreate(content="List all the links of jobs that these companies are offering.")))
    assert vacancy_searches, "expected a company-scoped vacancy search"
    assert vacancy_searches[-1][1] == ["Acme Corp"]
    assert len(searches) == 1  # only the turn-1 search; turn 2 is company-scoped
    answer2 = r2["assistant_message"]["content"] if isinstance(r2, dict) else r2.answer
    assert "Apply:" in answer2

    # Turn 3: location-only update, job search, never RAG.
    r3 = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, __import__("app.schemas.chat", fromlist=["ChatMessageCreate"]).ChatMessageCreate(content="List the companies that are offering jobs in Bangalore.")))
    assert searches, "expected a job search"
    assert searches[-1].role == "Web Developer"
    assert searches[-1].experience == "Fresher / entry-level"
    assert searches[-1].location == "Bengaluru"
    assert rag_calls == []


def test_location_only_update_preserves_role(monkeypatch):
    history = []
    searches = []
    company_searches = []
    vacancy_searches = []
    rag_calls = []
    _install_harness(monkeypatch, history, searches, company_searches, vacancy_searches, rag_calls, verdict=False)

    # Seed a completed job search in history so the role is remembered.
    history.append({
        "role": "assistant",
        "content": "Here are jobs.",
        "sources": [{"kind": "job_preferences", "role": "Web Developer", "experience": "Fresher / entry-level",
                     "location": "India", "skills": [], "remote": False, "platform": "", "industry": "",
                     "salary": "", "previous_company": "", "employment_type": ""}],
    })

    from app.schemas.chat import ChatMessageCreate
    asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, ChatMessageCreate(content="Find jobs in Bangalore")))
    assert searches and searches[-1].role == "Web Developer"
    assert searches[-1].experience == "Fresher / entry-level"
    assert searches[-1].location == "Bengaluru"


def test_new_conversation_has_no_inherited_context(monkeypatch):
    history = []
    searches = []
    company_searches = []
    vacancy_searches = []
    rag_calls = []
    _install_harness(monkeypatch, history, searches, company_searches, vacancy_searches, rag_calls, verdict=False)

    from app.schemas.chat import ChatMessageCreate
    r1 = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, ChatMessageCreate(content="List all the links of jobs that these companies are offering.")))
    answer1 = r1["assistant_message"]["content"] if isinstance(r1, dict) else r1.answer
    assert vacancy_searches == []
    assert "don't have a verified company list" in answer1

    r2 = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, ChatMessageCreate(content="Find jobs in Bangalore")))
    answer2 = r2["assistant_message"]["content"] if isinstance(r2, dict) else r2.answer
    assert searches == []
    assert "Which location" not in answer2 or "What role" in answer2


def test_switch_job_search_to_salary_uses_rag(monkeypatch):
    history = []
    searches = []
    company_searches = []
    vacancy_searches = []
    rag_calls = []
    _install_harness(monkeypatch, history, searches, company_searches, vacancy_searches, rag_calls, verdict=False)

    history.append({
        "role": "assistant",
        "content": "Here are jobs.",
        "sources": [{"kind": "job_preferences", "role": "Web Developer", "experience": "Fresher / entry-level",
                     "location": "Bengaluru", "skills": [], "remote": False, "platform": "", "industry": "",
                     "salary": "", "previous_company": "", "employment_type": ""},
                    {"kind": "job", "title": "Web Developer", "company": "Acme Corp", "location": "Bengaluru",
                     "experience": "Fresher / entry-level", "employment_type": "Full-time", "salary": None,
                     "description": None, "skills": [], "url": "https://www.acme.com/jobs/1", "source": "jsearch",
                     "search_date": "2026-11-23", "score": 1.0}],
    })

    from app.schemas.chat import ChatMessageCreate
    r = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, ChatMessageCreate(content="What is the average AI Engineer salary in Bangalore?")))
    assert searches == [] and company_searches == [] and vacancy_searches == []
    assert rag_calls and rag_calls[-1][0] == "What is the average AI Engineer salary in Bangalore?"


def test_switch_job_search_to_comparison_uses_rag(monkeypatch):
    history = []
    searches = []
    company_searches = []
    vacancy_searches = []
    rag_calls = []
    _install_harness(monkeypatch, history, searches, company_searches, vacancy_searches, rag_calls, verdict=False)

    history.append({
        "role": "assistant",
        "content": "Here are jobs.",
        "sources": [{"kind": "job_preferences", "role": "Web Developer", "experience": "Fresher / entry-level",
                     "location": "Bengaluru", "skills": [], "remote": False, "platform": "", "industry": "",
                     "salary": "", "previous_company": "", "employment_type": ""}],
    })

    from app.schemas.chat import ChatMessageCreate
    r = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, ChatMessageCreate(content="Compare Software Engineer and Cybersecurity Engineer")))
    assert searches == [] and company_searches == [] and vacancy_searches == []
    assert rag_calls


def test_job_search_never_falls_back_to_rag(monkeypatch):
    history = []
    searches = []
    company_searches = []
    vacancy_searches = []
    rag_calls = []
    _install_harness(monkeypatch, history, searches, company_searches, vacancy_searches, rag_calls, verdict=False)

    from app.schemas.chat import ChatMessageCreate
    r = asyncio.run(chat_service.send_message(OWNER_ID, SESSION_ID, ChatMessageCreate(content="Find Web Developer jobs in Bangalore", job_search=True)))
    assert searches
    assert rag_calls == []


def test_context_ignores_unrelated_salary_message():
    history = [
        {"role": "user", "content": "I am looking for Web Developer fresher jobs."},
        {"role": "assistant", "content": "Here are jobs.", "sources": [
            {"kind": "job_preferences", "role": "Web Developer", "experience": "Fresher / entry-level",
             "location": "India", "skills": [], "remote": False, "platform": "", "industry": "",
             "salary": "", "previous_company": "", "employment_type": ""},
        ]},
        {"role": "user", "content": "What is the average AI Engineer salary in Bangalore?"},
        {"role": "assistant", "content": "No docs.", "sources": []},
    ]
    ctx = build_session_context(history)
    assert ctx.preferences.role == "Web Developer"
    assert ctx.preferences.experience == "Fresher / entry-level"
    assert ctx.pending_missing == ""


def test_pending_cleared_after_completed_search():
    history = [
        {"role": "assistant", "content": "Which location?", "sources": [
            {"kind": "job_search_prompt", "missing": ["location"], "preferences": {"role": "Web Developer", "experience": "Fresher / entry-level"}},
        ]},
        {"role": "assistant", "content": "Here are jobs.", "sources": [
            {"kind": "job_preferences", "role": "Web Developer", "experience": "Fresher / entry-level", "location": "Bengaluru"},
        ]},
    ]
    assert _pending_job_search_missing(history) == ""


def test_references_previous_companies_variants():
    for text in [
        "List all the links of jobs that these companies are offering.",
        "Show links for those companies",
        "their openings",
        "the companies you listed",
    ]:
        assert references_previous_companies(text), text
    assert not references_previous_companies("Find React developer jobs in India.")


def test_is_company_listing_query_variants():
    assert is_company_listing_query("List the companies that are offering jobs in Bangalore.")
    assert not is_company_listing_query("List all the links of jobs that these companies are offering.")


def test_career_info_question_variants():
    assert is_career_info_question("What is the average AI Engineer salary in Bangalore?")
    assert is_career_info_question("Compare Software Engineer and Cybersecurity Engineer")
    assert not is_career_info_question("Summarize my candidates")


def test_session_context_isolated():
    h1 = [{"role": "assistant", "content": "jobs", "sources": [
        {"kind": "job", "title": "Web Developer", "company": "Acme Corp", "location": "India", "url": "https://www.acme.com/jobs/1"},
        {"kind": "job_preferences", "role": "Web Developer", "experience": "Fresher / entry-level", "location": "India"},
    ]}]
    h2 = [{"role": "assistant", "content": "jobs", "sources": [
        {"kind": "job", "title": "Web Developer", "company": "Beta Inc", "location": "India", "url": "https://www.beta.com/jobs/1"},
        {"kind": "job_preferences", "role": "Web Developer", "experience": "Fresher / entry-level", "location": "India"},
    ]}]
    assert build_session_context(h1).companies[0]["company"] == "Acme Corp"
    assert build_session_context(h2).companies[0]["company"] == "Beta Inc"


def test_missing_company_and_generic_url_honesty():
    from app.services.job_search_service import _url_quality
    assert _url_quality("https://www.indeed.com/q-web-developer-jobs.html") == -1
    answer = format_company_vacancy_answer(
        [],
        JobPreferences(role="Web Developer", location="Bengaluru"),
        {"requested": ["Acme"], "verified": [], "unverified": ["Acme"]},
    )
    assert "could not verify" in answer
    assert "Acme" in answer


def test_pdf_first_message_extraction():
    from app.services.job_search_service import extract_preferences
    prefs = extract_preferences(FIRST_MESSAGE)
    assert prefs.role == "Web Developer"
    assert prefs.experience == "Fresher / entry-level"
    assert prefs.location == ""