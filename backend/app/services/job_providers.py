"""Job search providers.

JSearch is the structured primary source; Tavily remains a fallback.

Two JSearch transports are supported and selected with ``JSEARCH_PROVIDER``:

* ``openwebninja`` (default) - https://api.openwebninja.com/jsearch/search
  authenticated with the ``x-api-key`` header.
* ``rapidapi`` - https://jsearch.p.rapidapi.com/search authenticated with the
  ``X-RapidAPI-Key`` / ``X-RapidAPI-Host`` headers (legacy behaviour).

No API keys are logged or returned to clients.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, Protocol

import httpx

if TYPE_CHECKING:
    from app.services.job_search_service import JobPreferences

JSEARCH_RAPIDAPI_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
JSEARCH_OPENWEBNINJA_URL = "https://api.openwebninja.com/jsearch/search"
JSEARCH_TIMEOUT_SECONDS = 20.0

# Kept for backwards compatibility with older imports.
JSEARCH_URL = JSEARCH_RAPIDAPI_URL
JSEARCH_HOST = JSEARCH_RAPIDAPI_HOST

JSEARCH_PROVIDERS = ("openwebninja", "rapidapi")
JSEARCH_DEFAULT_PROVIDER = "openwebninja"
JSEARCH_DEFAULT_COUNTRY = "in"
JSEARCH_ERROR_BODY_CHARS = 300


class ProviderError(RuntimeError):
    pass


class JobProvider(Protocol):
    async def search(self, prefs: "JobPreferences") -> list[dict[str, Any]]:
        """Return listings in the application's standard listing dict shape."""
        ...


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _redact(text: Any, secret: str = "") -> str:
    """Strip credentials before an error body is stored or logged."""
    cleaned = _clean(text)
    if secret:
        cleaned = cleaned.replace(secret, "***")
    cleaned = re.sub(r"\bak_[A-Za-z0-9]+", "ak_***", cleaned)
    return cleaned[:JSEARCH_ERROR_BODY_CHARS]


def _resolve_mode(mode: str | None) -> str:
    candidate = (mode or os.getenv("JSEARCH_PROVIDER") or JSEARCH_DEFAULT_PROVIDER).strip().lower()
    return candidate if candidate in JSEARCH_PROVIDERS else JSEARCH_DEFAULT_PROVIDER


def _api_key_from_env(mode: str) -> str:
    names = ["JSEARCH_API_KEY"]
    if mode == "openwebninja":
        names.append("OPENWEBNINJA_API_KEY")
    else:
        names.append("RAPIDAPI_KEY")
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Support both JSearch response envelopes.

    * RapidAPI ``/search`` and OpenWebNinja ``/search``: ``{"data": [ ... ]}``
    * OpenWebNinja ``/search-v2``: ``{"data": {"jobs": [ ... ], "cursor": "..."}}``
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        rows = data.get("jobs") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


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
        _clean(row.get("job_location")),
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
    """Structured job postings from JSearch (OpenWebNinja or RapidAPI)."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = JSEARCH_TIMEOUT_SECONDS,
        mode: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.mode = _resolve_mode(mode)
        self.api_key = (api_key if api_key is not None else _api_key_from_env(self.mode)).strip()
        self.timeout = timeout
        self.last_status: int | None = None
        if base_url:
            self.url = base_url.strip()
        elif self.mode == "openwebninja":
            self.url = (os.getenv("JSEARCH_OPENWEBNINJA_URL") or JSEARCH_OPENWEBNINJA_URL).strip()
        else:
            self.url = (os.getenv("JSEARCH_RAPIDAPI_URL") or JSEARCH_RAPIDAPI_URL).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _build_headers(self) -> dict[str, str]:
        if self.mode == "openwebninja":
            return {"X-API-Key": self.api_key}
        return {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": JSEARCH_RAPIDAPI_HOST,
        }

    def _build_params(self, prefs: "JobPreferences", query: str | None = None) -> dict[str, str]:
        if not query:
            bits = [prefs.role or "jobs"]
            if prefs.experience:
                bits.append(prefs.experience)
            query = " ".join(bits) + f" in {prefs.location or 'India'}"

        if self.mode == "openwebninja":
            params = {"query": query, "num_pages": "1"}
            country = (os.getenv("JSEARCH_COUNTRY") or JSEARCH_DEFAULT_COUNTRY).strip().lower()
            if country:
                params["country"] = country
            if getattr(prefs, "remote", False):
                params["work_from_home"] = "true"
            return params

        # RapidAPI keeps the legacy pagination parameters.
        return {"query": query, "page": "1", "num_pages": "1"}

    def _error_message(self, response: httpx.Response) -> str:
        body = _redact(getattr(response, "text", ""), self.api_key)
        suffix = f": {body}" if body else ""
        return f"JSearch ({self.mode}) HTTP {response.status_code}{suffix}"

    async def search(
        self, prefs: "JobPreferences", query: str | None = None
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.url,
                    headers=self._build_headers(),
                    params=self._build_params(prefs, query),
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"JSearch ({self.mode}) request failed: {type(exc).__name__}") from exc

        self.last_status = response.status_code

        if response.status_code >= 400:
            raise ProviderError(self._error_message(response))

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(f"JSearch ({self.mode}) returned a non-JSON response.") from exc

        listings: list[dict[str, Any]] = []
        for row in _extract_rows(payload):
            mapped = _map_jsearch_row(row)
            if mapped:
                listings.append(mapped)
        return listings
