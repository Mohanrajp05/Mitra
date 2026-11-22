"""Job search providers.

JSearch (RapidAPI) is the structured primary source; Tavily remains a fallback.
No API keys are logged or returned to clients.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, Protocol

import httpx

if TYPE_CHECKING:
    from app.services.job_search_service import JobPreferences

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_TIMEOUT_SECONDS = 20.0


class ProviderError(RuntimeError):
    pass


class JobProvider(Protocol):
    async def search(self, prefs: "JobPreferences") -> list[dict[str, Any]]:
        """Return listings in the application's standard listing dict shape."""
        ...


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _map_jsearch_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map one JSearch result to the existing listing dict shape."""
    from app.services.job_search_service import normalize_location

    url = _clean(row.get("job_apply_link") or row.get("job_google_link"))
    if not url.startswith(("http://", "https://")):
        return None
    title = _clean(row.get("job_title"))
    if not title:
        return None

    place_parts = [
        _clean(row.get("job_city")),
        _clean(row.get("job_state")),
        _clean(row.get("job_country")),
    ]
    location = None
    for part in place_parts:
        if part:
            location = normalize_location(part) or part
            break

    description = _clean(row.get("job_description")) or None
    combined = f"{title} {description or ''}".casefold()
    if re.search(r"\b(?:freshers?|entry[\s-]?levels?|graduates?)\b", combined):
        experience = "Fresher / entry-level"
    else:
        match = re.search(r"\b\d+\s*[-–]\s*\d+\s*years?\b", combined)
        experience = match.group(0) if match else None

    minimum = row.get("job_min_salary")
    maximum = row.get("job_max_salary")
    period = _clean(row.get("job_salary_period"))
    salary = None
    if minimum or maximum:
        salary = f"{minimum or ''}-{maximum or ''}".strip("-")
        if period:
            salary += f" {period}"

    return {
        "kind": "job",
        "title": title,
        "company": _clean(row.get("employer_name")) or None,
        "location": location,
        "experience": experience,
        "employment_type": _clean(row.get("job_employment_type")) or None,
        "salary": salary,
        "description": description[:400] if description else None,
        "skills": [],
        "url": url,
        "source": "jsearch",
        "search_date": _clean(row.get("job_posted_at_datetime_utc"))[:10] or None,
        "score": 1.0,
    }


class JSearchProvider:
    """Structured job postings from JSearch (RapidAPI)."""

    def __init__(self, api_key: str | None = None, timeout: float = JSEARCH_TIMEOUT_SECONDS) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("JSEARCH_API_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def search(self, prefs: "JobPreferences") -> list[dict[str, Any]]:
        if not self.configured:
            return []

        bits = [prefs.role or "jobs"]
        if prefs.experience:
            bits.append(prefs.experience)
        query = " ".join(bits) + f" in {prefs.location or 'India'}"

        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": JSEARCH_HOST,
        }
        params = {"query": query, "page": "1", "num_pages": "1"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(JSEARCH_URL, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("JSearch request failed.") from exc

        rows = (payload or {}).get("data") or []
        listings: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            mapped = _map_jsearch_row(row)
            if mapped:
                listings.append(mapped)
        return listings
