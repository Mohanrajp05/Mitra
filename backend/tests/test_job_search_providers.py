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
        assert len(tavily_called) == 1
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
