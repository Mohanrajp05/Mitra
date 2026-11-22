"""Regression tests for job-search providers, parsing and fallback behaviour."""

import asyncio

import pytest

from app.schemas.job_search import JobPostingExtraction
from app.services import job_providers
from app.services import job_search_service as js
from app.services.job_search_service import (
    JobPreferences,
    _parse_listing,
    _url_quality,
    free_text_location,
    normalize_location,
    format_company_answer,
    format_job_answer,
    search_jobs,
)

GOOD_URL = "https://boards.greenhouse.io/acme/jobs/123"


def test_listing_and_profile_urls_are_rejected():
    rejected = [
        "https://www.indeed.com/q-online-web-developer-jobs.html",
        "https://www.naukri.com/fresher-web-development-jobs-in-andhra-pradesh",
        "https://rocketreach.co/xlr8-andhra-pradesh-profile_b442",
        "https://www.zoominfo.com/c/acme/123",
    ]
    for url in rejected:
        assert _url_quality(url) == -1
        assert (
            _parse_listing(
                {"title": "Web Developer", "url": url, "content": "A job."},
                JobPreferences(),
            )
            is None
        )

    assert _url_quality(GOOD_URL) == 1
    assert _url_quality("https://www.naukri.com/job/web-developer-123") == 1
    assert _url_quality("https://example.com/some-page") == 0


def test_location_typo_is_normalized():
    assert normalize_location("Andra pradesh") == "Andhra Pradesh"
    assert normalize_location("bangalore") == "Bengaluru"
    assert free_text_location("Web Developer jobs in Andra pradesh") == "Andhra Pradesh"


def test_result_fields_are_never_copied_from_user_preferences():
    prefs = JobPreferences(
        role="Web Developer",
        experience="Fresher / entry-level",
        location="Andhra Pradesh",
        employment_type="Full-time",
        remote=True,
    )
    item = {
        "title": "Junior Web Developer at Acme",
        "url": GOOD_URL,
        "content": (
            "Build websites. Work from office(760) Hybrid(16) Remote(10) "
            "People also searched: Resume Resources: Career Resources: "
            "Employer Resources: ## Job Post Details Build responsive sites with React."
        ),
    }

    parsed = _parse_listing(item, prefs)

    assert parsed["company"] == "Acme"
    assert parsed["location"] is None
    assert parsed["experience"] is None
    assert parsed["employment_type"] is None
    assert parsed["salary"] is None
    assert "People also searched" not in parsed["description"]
    assert "Build responsive sites" in parsed["description"]


def _make_listing(location, index=0):
    return {
        "kind": "job",
        "title": f"Web Developer {index}",
        "company": f"Company {index}",
        "location": location,
        "experience": None,
        "employment_type": None,
        "salary": None,
        "description": "Build websites.",
        "skills": [],
        "url": f"{GOOD_URL}?loc={index}-{location.replace(' ', '-')}",
        "source": "jsearch",
        "score": 0.5,
    }


def test_empty_results_answer_offers_suggestions():
    answer = js.format_job_answer(
        [], JobPreferences(role="Web Developer", location="Pune", experience="Fresher / entry-level")
    )
    assert "could not find any verified individual job postings" in answer
    assert "Junior Web Developer" in answer
    assert "broader location" in answer
    assert "which companies are hiring" in answer


def test_is_company_hiring_query_detects_phrases():
    from app.services.job_search_service import is_company_hiring_query

    assert is_company_hiring_query("which companies are hiring for full stack web development?")
    assert is_company_hiring_query("who is hiring for React developer roles?")
    assert not is_company_hiring_query("Find React developer jobs in India.")


def test_search_hiring_companies_extracts_companies(monkeypatch):
    js.clear_cache()

    async def fake_tavily(prefs):
        return [
            {
                "kind": "company",
                "title": "Hiring",
                "company": "Acme",
                "location": "Bengaluru",
                "experience": None,
                "employment_type": None,
                "salary": None,
                "description": None,
                "skills": [],
                "url": "https://www.acme.com/careers",
                "source": "tavily",
                "search_date": "2026-11-23",
                "score": 0.9,
            }
        ]

    # Monkeypatch LLM extraction at the function level.
    async def fake_extract(item, client):
        return [
            {
                "kind": "company",
                "title": "Full Stack Developer",
                "company": "Acme",
                "location": "Bengaluru",
                "experience": None,
                "employment_type": None,
                "salary": None,
                "description": None,
                "skills": [],
                "url": "https://www.acme.com/careers",
                "source": "tavily",
                "search_date": "2026-11-23",
                "score": 0.9,
            }
        ]

    monkeypatch.setenv("JOB_SEARCH_LLM_VALIDATION", "true")
    monkeypatch.setattr(js, "_extract_company_hiring", fake_extract)

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"title": "Acme Careers", "url": "https://www.acme.com/careers", "content": "Acme is hiring"}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None):
            return FakeResponse()

    monkeypatch.setattr(js.httpx, "AsyncClient", FakeClient)

    results = asyncio.run(js.search_hiring_companies(js.JobPreferences(role="Full Stack Developer", location="India")))
    assert len(results) == 1
    assert results[0]["company"] == "Acme"
    assert results[0]["kind"] == "company"
    assert results[0]["url"] == "https://www.acme.com/careers"


def test_format_company_answer_lists_companies():
    listings = [
        {"kind": "company", "title": "Full Stack Developer", "company": "Acme", "url": "https://www.acme.com/careers"},
        {"kind": "company", "title": "Full Stack Developer", "company": "Beta", "url": None},
    ]
    answer = js.format_company_answer(listings, JobPreferences(role="Full Stack Developer", location="India"))
    assert "Acme" in answer
    assert "https://www.acme.com/careers" in answer
    assert "Beta" in answer


@pytest.mark.asyncio
async def test_company_hiring_query_returns_companies(monkeypatch):
    from app.services import chat_service

    captured = {}

    async def fake_company(prefs):
        captured["prefs"] = prefs
        return [
            {
                "kind": "company",
                "title": "Full Stack Developer",
                "company": "Acme",
                "location": "India",
                "experience": None,
                "employment_type": None,
                "salary": None,
                "description": None,
                "skills": [],
                "url": "https://www.acme.com/careers",
                "source": "tavily",
                "search_date": "2026-11-23",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(chat_service, "search_hiring_companies", fake_company)
    monkeypatch.setattr(chat_service, "_check_session", lambda *args: None)
    monkeypatch.setattr(chat_service, "_load_history", lambda *args: [])
    monkeypatch.setattr(
        chat_service, "_persist_exchange", lambda *args: {"user_message": {}, "assistant_message": {}}
    )

    result = await chat_service._run_job_search(
        "which companies are hiring for full stack web development?",
        {"role": "Full Stack Developer"},
        history=[],
    )

    assert "Acme" in result.answer
    assert "https://www.acme.com/careers" in result.answer
    assert captured["prefs"].role == "Full Stack Developer"


def test_location_ladder_stops_when_three_postings_found(monkeypatch):
    js.clear_cache()
    calls = []

    async def fake_provider(prefs):
        calls.append(prefs.location)
        count = 3 if len(calls) == 2 else 1
        return [_make_listing(prefs.location, i) for i in range(count)]

    monkeypatch.setattr(js, "_provider_search", fake_provider)
    prefs = JobPreferences(role="Web Developer", location="Andhra Pradesh")

    results = asyncio.run(js.search_jobs(prefs))

    assert calls == ["Andhra Pradesh", "Visakhapatnam, Vijayawada"]
    assert len(results) == 3
    assert prefs.search_meta["broader"] is True
    assert prefs.search_meta["used_location"] == "Visakhapatnam, Vijayawada"


def test_location_ladder_keeps_exact_location_when_sufficient(monkeypatch):
    js.clear_cache()
    calls = []

    async def fake_provider(prefs):
        calls.append(prefs.location)
        return [_make_listing(prefs.location, i) for i in range(3)]

    monkeypatch.setattr(js, "_provider_search", fake_provider)
    prefs = JobPreferences(role="Web Developer", location="Bengaluru")

    asyncio.run(js.search_jobs(prefs))

    assert calls == ["Bengaluru"]
    assert prefs.search_meta["broader"] is False


@pytest.mark.asyncio
async def test_broader_location_is_marked_in_response(monkeypatch):
    from app.services import chat_service

    prefs = JobPreferences(role="Web Developer", location="Andhra Pradesh")

    async def fake_search(profile):
        profile.search_meta = {
            "original_location": "Andhra Pradesh",
            "used_location": "Visakhapatnam, Vijayawada",
            "broader": True,
        }
        return [_make_listing("Visakhapatnam, Vijayawada")]

    monkeypatch.setattr(chat_service, "search_jobs", fake_search)

    result = await chat_service._run_job_search(
        "Web Developer jobs in Andhra Pradesh",
        {"role": "Web Developer", "location": "Andhra Pradesh"},
        history=[],
    )
    assert "broadened the search" in result.answer
    assert any(source.get("kind") == "job_search_scope" for source in result.sources)


class FakeProvider:
    def __init__(self, results=None, error=False):
        self.results = results or []
        self.error = error
        self.called = False

    async def search(self, prefs):
        self.called = True
        if self.error:
            raise RuntimeError("provider down")
        return self.results


@pytest.mark.parametrize("mode", ["success", "empty", "error"])
def test_jsearch_fallback_behaviour(monkeypatch, mode):
    js.clear_cache()
    provider_result = [
        {
            "kind": "job",
            "title": "Web Developer",
            "company": "Acme",
            "location": "Bengaluru",
            "url": GOOD_URL,
            "source": "jsearch",
            "experience": None,
            "employment_type": None,
            "salary": None,
            "description": None,
            "skills": [],
            "score": 1.0,
        }
    ]
    provider = FakeProvider(
        results=provider_result if mode == "success" else [],
        error=mode == "error",
    )
    monkeypatch.setattr(job_providers, "JSearchProvider", lambda: provider)

    tavily_called = []

    async def fake_tavily(prefs, queries=None):
        tavily_called.append(prefs)
        return [
            {
                "kind": "job",
                "title": "Fallback Job",
                "company": None,
                "location": None,
                "url": GOOD_URL + "?fallback=1",
                "source": "tavily",
                "experience": None,
                "employment_type": None,
                "salary": None,
                "description": None,
                "skills": [],
                "score": 0.5,
            }
        ]

    monkeypatch.setattr(js, "_search_tavily", fake_tavily)

    results = asyncio.run(search_jobs(JobPreferences(role="Web Developer", location="Bengaluru")))

    assert provider.called is True
    if mode == "success":
        assert tavily_called == []
        assert results[0]["source"] == "jsearch"
    else:
        assert len(tavily_called) >= 1
        assert results[0]["source"] == "tavily"


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": [
                {
                    "job_title": "Web Developer",
                    "employer_name": "Acme",
                    "job_city": "Bangalore",
                    "job_state": "Karnataka",
                    "job_country": "India",
                    "job_employment_type": "FULLTIME",
                    "job_apply_link": GOOD_URL,
                    "job_description": "Entry-level web developer role.",
                    "job_min_salary": 300000,
                    "job_max_salary": 500000,
                    "job_salary_period": "YEARLY",
                }
            ]
        }


class FakeAsyncClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None, params=None):
        assert headers["X-RapidAPI-Key"] == "dummy-key"
        assert "query" in params
        return FakeResponse()


def test_jsearch_provider_maps_structured_fields(monkeypatch):
    monkeypatch.setattr(job_providers.httpx, "AsyncClient", FakeAsyncClient)
    provider = job_providers.JSearchProvider(api_key="dummy-key")

    results = asyncio.run(provider.search(JobPreferences(role="Web Developer", location="Bangalore")))

    assert len(results) == 1
    assert results[0]["title"] == "Web Developer"
    assert results[0]["company"] == "Acme"
    assert results[0]["location"] == "Bengaluru"
    assert results[0]["employment_type"] == "FULLTIME"
    assert results[0]["experience"] == "Fresher / entry-level"
    assert results[0]["source"] == "jsearch"
    assert results[0]["url"] == GOOD_URL


class FakeTavilyResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [
                {
                    "title": "Junior Web Developer at Acme",
                    "url": GOOD_URL,
                    "content": "Build websites with React. Full-time role.",
                    "score": 0.9,
                }
            ]
        }


class FakeTavilyClient:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        assert "exclude_domains" in json
        assert json["include_domains"]
        assert json["search_depth"] == "advanced"
        assert json["max_results"] == 10
        assert "time_range" not in json
        return FakeTavilyResponse()


@pytest.mark.asyncio
async def test_llm_rejects_non_postings(monkeypatch):
    monkeypatch.setenv("JOB_SEARCH_LLM_VALIDATION", "true")
    monkeypatch.setattr(js.httpx, "AsyncClient", FakeTavilyClient)

    async def reject(item, client):
        return JobPostingExtraction(is_single_posting=False)

    monkeypatch.setattr(js, "_extract_job_posting", reject)

    results = await js._search_tavily(JobPreferences(role="Web Developer"))
    assert results == []


@pytest.mark.asyncio
async def test_llm_fields_override_heuristics(monkeypatch):
    monkeypatch.setenv("JOB_SEARCH_LLM_VALIDATION", "true")
    monkeypatch.setattr(js.httpx, "AsyncClient", FakeTavilyClient)

    async def accept(item, client):
        return JobPostingExtraction(
            is_single_posting=True,
            title="React Developer",
            company="New Co",
            location="Andra pradesh",
            employment_type="Full-time",
            apply_url=GOOD_URL,
        )

    monkeypatch.setattr(js, "_extract_job_posting", accept)

    results = await js._search_tavily(JobPreferences(role="Web Developer"))
    assert len(results) >= 1
    assert results[0]["title"] == "React Developer"
    assert results[0]["company"] == "New Co"
    assert results[0]["location"] == "Andhra Pradesh"
    assert results[0]["employment_type"] == "Full-time"
