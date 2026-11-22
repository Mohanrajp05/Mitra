import os
import re
import time
from dataclasses import dataclass, field, replace
from difflib import get_close_matches
from typing import Any
from urllib.parse import quote_plus, urlsplit

import httpx

ROLE_ALIASES = {
    "se": "Software Engineer",
    "sde": "Software Development Engineer",
    "swe": "Software Engineer",
    "ds": "Data Scientist",
    "da": "Data Analyst",
    "pm": "Product Manager",
    "qa": "Quality Assurance Engineer",
    "hr": "Human Resources Specialist",
    "devops": "DevOps Engineer",
}


def normalize_role(role: str) -> str:
    cleaned = (role or "").strip()
    return ROLE_ALIASES.get(cleaned.lower(), cleaned)


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def build_job_url(
    source: str, role: str, location: str = "", *, naukri_fallback: bool = False
) -> str:
    normalized_role = normalize_role(role)
    if not normalized_role:
        raise ValueError("role is required.")

    normalized_source = (source or "").strip().lower()
    if normalized_source == "linkedin":
        return (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={quote_plus(normalized_role)}&location={quote_plus((location or '').strip())}"
        )
    if normalized_source == "naukri":
        if naukri_fallback:
            return (
                "https://www.naukri.com/jobs-in-india"
                f"?k={quote_plus(normalized_role)}&l={quote_plus((location or '').strip())}"
            )
        role_slug = _slug(normalized_role)
        if not role_slug:
            raise ValueError("role must contain letters or numbers.")
        location_slug = _slug(location or "")
        return f"https://www.naukri.com/{role_slug}-jobs" + (
            f"-in-{location_slug}" if location_slug else ""
        )
    raise ValueError("source must be linkedin or naukri.")


TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_TIMEOUT_SECONDS = 20.0
TAVILY_MAX_RESULTS = 8
CACHE_TTL_SECONDS = 600.0

PLATFORM_DOMAINS = {
    "linkedin": ["linkedin.com"],
    "naukri": ["naukri.com"],
    "indeed": ["indeed.com"],
    "foundit": ["foundit.in", "foundit.com"],
    "wellfound": ["wellfound.com"],
    "internshala": ["internshala.com"],
}

# Common aliases are normalized, but this list is NOT an exhaustive whitelist:
# free_text_location() below accepts arbitrary place names (states, districts,
# cities) so location answers are never rejected just because they are unusual.
KNOWN_LOCATIONS = (
    "bengaluru", "bangalore", "hyderabad", "delhi", "new delhi", "mumbai",
    "pune", "chennai", "kolkata", "ahmedabad", "noida", "gurgaon", "gurugram",
    "india", "remote", "usa", "united states", "uk", "london", "singapore",
    "germany", "canada", "australia",
)

LOCATION_ALIASES = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
}

# Canonical Indian locations + common misspellings/aliases.  Fuzzy matching is
# used for near misses such as "Andra pradesh".
LOCATION_CANONICAL = {
    "andra pradesh": "Andhra Pradesh",
    "andhra pradesh": "Andhra Pradesh",
    "andhra": "Andhra Pradesh",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "bangaluru": "Bengaluru",
    "bengalooru": "Bengaluru",
    "bombay": "Mumbai",
    "mumbai": "Mumbai",
    "calcutta": "Kolkata",
    "kolkata": "Kolkata",
    "madras": "Chennai",
    "chennai": "Chennai",
    "delhi": "Delhi",
    "new delhi": "New Delhi",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
    "ahmedabad": "Ahmedabad",
    "noida": "Noida",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "jaipur": "Jaipur",
    "kochi": "Kochi",
    "kerala": "Kerala",
    "karnataka": "Karnataka",
    "tamil nadu": "Tamil Nadu",
    "telangana": "Telangana",
    "maharashtra": "Maharashtra",
    "gujarat": "Gujarat",
    "uttar pradesh": "Uttar Pradesh",
    "west bengal": "West Bengal",
    "madhya pradesh": "Madhya Pradesh",
    "india": "India",
}


def normalize_location(value: str | None) -> str | None:
    """Normalize known place names (including common typos) to canonical form."""
    cleaned = re.sub(r"\s+", " ", str(value or "").strip()).strip(".,!?:-").strip()
    if not cleaned:
        return None
    key = cleaned.casefold()
    if key in LOCATION_CANONICAL:
        return LOCATION_CANONICAL[key]
    close = get_close_matches(key, LOCATION_CANONICAL.keys(), n=1, cutoff=0.86)
    if close:
        return LOCATION_CANONICAL[close[0]]
    return cleaned


BAD_URL_FRAGMENTS = ("/q-", "-jobs.html", "/jobs-in-", "/profile_")
BAD_HOSTS = ("rocketreach.co", "zoominfo.com")
GOOD_URL_FRAGMENTS = ("/job/", "/viewjob", "/jobs/view/", "/job-posting/")
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workday")
_TAVILY_EXCLUDE_DOMAINS = ("rocketreach.co", "zoominfo.com")

_NAV_BOILERPLATE = (
    "People also searched",
    "Resume Resources",
    "Career Resources",
    "Employer Resources",
)
_JOB_CONTENT_MARKERS = ("Job Post Details", "Job Description", "Job details", "About the job")


JOB_POSTING_SYSTEM_PROMPT = (
    "You validate one raw web-search result for a job search. Decide whether it "
    "describes ONE individual job posting (not a category page, search results "
    "page, company profile, salary guide or list of vacancies). Extract only "
    "fields explicitly present in the result; use null when absent. Never invent "
    "a company, location or application link. Return JSON only."
)


def _tavily_llm_client():
    """Return the existing LLM client when configured, else None."""
    try:
        from app.rag.llm import get_llm_client

        client = get_llm_client()
        settings = getattr(client, "settings", None)
        return client if settings and getattr(settings, "configured", False) else None
    except Exception:
        return None


async def _extract_job_posting(item: dict[str, Any], llm_client) -> Any | None:
    """Structured validation of a raw search result; None means unavailable."""
    if llm_client is None:
        return None
    try:
        from app.schemas.job_search import JobPostingExtraction

        title = _clean_text(item.get("title"))
        url = _clean_text(item.get("url"))
        content = _clean_text(item.get("content"))[:1200]
        settings = getattr(llm_client, "settings", None)
        use_responses = bool(getattr(settings, "use_responses", False))
        return await llm_client.complete_structured(
            JobPostingExtraction,
            JOB_POSTING_SYSTEM_PROMPT,
            f"Title: {title}\nURL: {url}\nContent: {content}",
            max_tokens=300,
            use_responses=use_responses,
        )
    except Exception:
        # Fail open: the URL/field heuristics already ran in _parse_listing.
        return None


def _url_quality(url: str) -> int:
    """-1 = reject (listing/profile page), 1 = prefer, 0 = neutral."""
    lowered = (url or "").casefold()
    host = urlsplit(lowered).netloc
    if any(bad in host for bad in BAD_HOSTS):
        return -1
    if any(fragment in lowered for fragment in BAD_URL_FRAGMENTS):
        return -1
    if any(good in lowered for good in GOOD_URL_FRAGMENTS):
        return 1
    if any(ats in host for ats in ATS_HOSTS):
        return 1
    return 0


def _strip_navigation_boilerplate(content: str) -> str:
    """Remove board navigation blocks, keeping real job detail text if present."""
    text = content or ""
    positions = [
        text.casefold().find(marker.casefold())
        for marker in _NAV_BOILERPLATE
    ]
    positions = [pos for pos in positions if pos >= 0]
    if not positions:
        return text
    start = min(positions)
    tail = text[start:]
    detail_positions = [
        tail.casefold().find(marker.casefold())
        for marker in _JOB_CONTENT_MARKERS
    ]
    detail_positions = [pos for pos in detail_positions if pos >= 0]
    if detail_positions:
        detail = tail[min(detail_positions):]
        return re.sub(r"^[#\s]+", "", detail).strip()
    return text[:start].strip()

_LOCATION_NON_PLACE = {
    "a", "an", "the", "this", "that", "these", "those", "same", "my", "your",
    "startup", "start", "company", "companies", "role", "roles", "field",
    "domain", "industry", "area", "position", "positions", "job", "jobs",
    "work", "working", "hiring", "opening", "openings", "opportunity",
    "opportunities", "listing", "listings", "location", "developer",
    "engineer", "analyst", "scientist", "designer", "manager", "tester",
    "architect", "consultant", "specialist", "support", "qa", "sde", "swe",
    "lead", "intern", "fresher", "graduate", "anywhere", "please", "remote",
}

ROLE_PATTERNS = (
    (r"\bsoftware\s+(?:engineer|developer)\b", "Software Engineer"),
    (r"\b(?:sde|swe)\b", "Software Engineer"),
    (r"\bfull[\s-]?stack\s+(?:developer|engineer)\b", "Full Stack Developer"),
    (r"\bfull[\s-]?stack[\s-]?web[\s-]?(?:development|developer)\b", "Full Stack Developer"),
    (r"\bfull[\s-]?stack[\s-]?development\b", "Full Stack Developer"),
    (r"\bfront[\s-]?end\s+(?:developer|engineer)\b", "Frontend Developer"),
    (r"\bback[\s-]?end\s+(?:developer|engineer)\b", "Backend Developer"),
    (r"\bpython\s+(?:developer|engineer)\b", "Python Developer"),
    (r"\breact\s+(?:developer|engineer)\b", "React Developer"),
    (r"\bjava\s+(?:developer|engineer)\b", "Java Developer"),
    (r"\bdata\s+scientist\b", "Data Scientist"),
    (r"\bdata\s+analyst\b", "Data Analyst"),
    (r"\b(?:ai|ml)\s+(?:engineer|developer)\b", "AI Engineer"),
    (r"\bdevops\s+engineer\b", "DevOps Engineer"),
    (r"\bqa\s+engineer\b", "QA Engineer"),
    (r"\bproduct\s+manager\b", "Product Manager"),

    (r"\bweb[\s-]?developer\b", "Web Developer"),
    (r"\bweb[\s-]?development\b", "Web Developer"),
    (r"\bfrontend[\s-]?developer\b", "Frontend Developer"),
    (r"\bfront[\s-]?end[\s-]?developer\b", "Frontend Developer"),
    (r"\bbackend[\s-]?developer\b", "Backend Developer"),
    (r"\bbacke?[\s-]?end[\s-]?developer\b", "Backend Developer"),
    (r"\bfull[\s-]?stack[\s-]?developer\b", "Full Stack Developer"),
    (r"\bfull[\s-]?stack[\s-]?engineer\b", "Full Stack Developer"),
    (r"\breact[\s-]?developer\b", "React Developer"),
    (r"\bangular[\s-]?developer\b", "Angular Developer"),
    (r"\bvue[\s-]?developer\b", "Vue Developer"),
    (r"\bpython[\s-]?developer\b", "Python Developer"),
    (r"\bjava[\s-]?developer\b", "Java Developer"),
    (r"\bai[\s-]?engineer\b", "AI Engineer"),
    (r"\bml[\s-]?engineer\b", "Machine Learning Engineer"),
    (r"\bdata[\s-]?scientist\b", "Data Scientist"),
    (r"\bdata[\s-]?engineer\b", "Data Engineer"),
    (r"\bdata[\s-]?analyst\b", "Data Analyst"),
    (r"\bdevops[\s-]?engineer\b", "DevOps Engineer"),
    (r"\bcloud[\s-]?engineer\b", "Cloud Engineer"),
    (r"\bcybersecurity[\s-]?engineer\b", "Cybersecurity Engineer"),
    (r"\bqa[\s-]?engineer\b", "QA Engineer"),
    (r"\bproduct[\s-]?manager\b", "Product Manager"),
    (r"\bux[\s-]?designer\b", "UI/UX Designer"),
    (r"\bui[\s/]?ux[\s-]?designer\b", "UI/UX Designer"),
    (r"\bui[\s/]?ux[\s-]?developer\b", "UI/UX Developer"),
    (r"\bmobile[\s-]?developer\b", "Mobile Developer"),
    (r"\bbusiness[\s-]?analyst\b", "Business Analyst"),
    (r"\btechnical[\s-]?support[\s-]?engineer\b", "Technical Support Engineer"),
)

SKILL_TERMS = (
    "Python", "FastAPI", "Django", "Flask", "React", "Angular", "Vue",
    "JavaScript", "TypeScript", "Java", "Spring Boot", "Node.js", "Go",
    "Rust", "C++", "SQL", "PostgreSQL", "MySQL", "MongoDB", "Docker",
    "Kubernetes", "AWS", "Azure", "GCP", "Git", "Machine Learning",
    "TensorFlow", "PyTorch", "HTML", "CSS", "REST APIs", "GraphQL",
)

JOB_SEARCH_PATTERN = re.compile(
    r"\b(?:find|search|look(?:ing)?\s+for|discover|recommend|show|get|suggest|share)\b"
    r"[\s\S]{0,80}?\b(?:jobs?|job\s+listings?|opportunities|openings|roles|positions|vacancies)\b"
    r"|\b(?:jobs?|opportunities|openings)\s+(?:in|on|for)\b"
    r"|\b(?:latest|new|recent)\b[\s\S]{0,40}?\b(?:jobs?|opportunities|openings)\b"
    r"|\bshow\s+(?:me\s+)?(?:only\s+)?(?:similar\s+)?jobs\b"
    r"|\b(?:need|want|require)\b[\s\S]{0,60}?\bfull[\s-]?time\s+job\b"
    r"|\b(?:are|is)\s+(?:companies|there)\s+hiring\b"
    r"|\b(?:unemployed|searching\s+for\s+(?:a\s+)?(?:developer|engineer|job|role))\b"
    r"|\b(?:list|share)\b[\s\S]{0,40}?\b(?:vacancies|openings|jobs)\b",
    re.IGNORECASE,
)

CLARIFICATION_MARKER = "job_search_prompt"

_ROLE_FILLER = {
    "please", "find", "search", "searching", "looking", "show", "get",
    "suggest", "share", "recommend", "discover", "need", "want", "require",
    "am", "is", "are", "in", "on", "for", "jobs", "job", "listings",
    "opportunities", "openings", "roles", "positions", "vacancies", "companies",
    "hiring", "a", "an", "the", "i", "my", "me", "we", "our",
}

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class TavilyError(RuntimeError):
    pass


@dataclass
class JobPreferences:
    role: str = ""
    skills: list[str] = field(default_factory=list)
    experience: str = ""
    employment_type: str = ""
    location: str = ""
    remote: bool = False
    platform: str = ""
    industry: str = ""
    salary: str = ""
    previous_company: str = ""

    def as_query_bits(self) -> list[str]:
        bits: list[str] = []
        if self.role:
            bits.append(self.role)
        if self.experience:
            bits.append(self.experience)
        if self.employment_type and self.employment_type.lower() != "remote":
            bits.append(self.employment_type)
        if self.skills:
            bits.append(" ".join(self.skills[:4]))
        if self.remote:
            bits.append("remote")
        return bits


def is_job_search(text: str) -> bool:
    return bool(JOB_SEARCH_PATTERN.search((text or "").strip()))


def _merge_list(current: list[str], added: list[str]) -> list[str]:
    result = list(current)
    for item in added:
        if item and item.casefold() not in {value.casefold() for value in result}:
            result.append(item)
    return result


def free_text_location(value: str) -> str:
    """Accept an arbitrary user-provided place name, not just KNOWN_LOCATIONS.

    Handles both a standalone answer ("Andhra Pradesh") and an explicit phrase
    ("fresher jobs in Andhra Pradesh"). Generic non-place words are ignored so
    "internship at a startup" is never mistaken for a location.
    """
    cleaned = re.sub(r"\s+", " ", (value or "").strip()).strip("?.!,").strip()
    if not cleaned:
        return ""

    def usable(candidate: str, max_words: int) -> bool:
        parts = [part.casefold().strip(".,") for part in candidate.split()]
        return (
            0 < len(parts) <= max_words
            and not any(part in _LOCATION_NON_PLACE for part in parts)
        )

    match = re.search(
        r"\b(?:in|at|near|around|across|from|location\s*:?|based\s+in)\s+"
        r"([A-Za-z][A-Za-z0-9'&.\-]*(?:\s+[A-Za-z][A-Za-z0-9'&.\-]*){0,4})",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        kept: list[str] = []
        for part in match.group(1).split():
            if part.casefold().strip(".,") in _LOCATION_NON_PLACE:
                break
            kept.append(part)
        candidate = " ".join(kept).strip(".,")
        if usable(candidate, 5):
            return normalize_location(candidate)

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'&.\-]*", cleaned)
    if len(words) <= 5 and not is_job_search(cleaned) and usable(cleaned, 5):
        return normalize_location(cleaned)
    return ""


def extract_preferences(text: str, current: JobPreferences | None = None) -> JobPreferences:
    value = (text or "").strip()
    prefs = replace(current) if current else JobPreferences()
    if not value:
        return prefs
    lowered = value.casefold()

    for pattern, role in ROLE_PATTERNS:
        if re.search(pattern, lowered):
            prefs.role = role
            break

    found_skills = [skill for skill in SKILL_TERMS if re.search(re.escape(skill.casefold()), lowered)]
    prefs.skills = _merge_list(prefs.skills, found_skills)

    if re.search(r"\b(?:freshers?|entry[\s-]?levels?|graduates?|0\s*[-–]\s*2\s*years?|interns?(?:hips?)?)\b", lowered):
        prefs.experience = "Fresher / entry-level"
    elif re.search(r"\b\d+\s*[-–]\s*\d+\s*years?\b", lowered):
        match = re.search(r"\b\d+\s*[-–]\s*\d+\s*years?\b", lowered)
        if match:
            prefs.experience = match.group(0).upper().replace("YEARS", "years")

    if re.search(r"\bfull[\s-]?time\b", lowered):
        prefs.employment_type = "Full-time"
    elif re.search(r"\bpart[\s-]?time\b", lowered):
        prefs.employment_type = "Part-time"
    elif re.search(r"\binternships?\s+(?:jobs?|openings?|opportunit(?:y|ies)|roles?|positions?)\b", lowered) or re.search(
        r"\b(?:find|search(?:ing)?|look(?:ing)?\s+for|want|need|seek(?:ing)?|apply(?:ing)?\s+for)\b[^.]{0,40}?\binternships?\b",
        lowered,
    ):
        prefs.employment_type = "Internship"

    if re.search(r"\bremote\b", lowered):
        prefs.remote = True
    elif re.search(r"\b(?:hybrid|onsite|on[\s-]site)\b", lowered):
        prefs.remote = False
        prefs.employment_type = "Hybrid" if "hybrid" in lowered else "On-site"

    found_locations = [item for item in KNOWN_LOCATIONS if re.search(rf"\b{re.escape(item)}\b", lowered)]
    if found_locations:
        locations = [item for item in found_locations if item not in ("remote", "india")]
        chosen = locations[0] if locations else ("India" if "india" in found_locations else "")
        if chosen:
            prefs.location = normalize_location(chosen) or chosen.title()
    if not prefs.location:
        # Arbitrary states/districts/cities are valid too; the list above is
        # only a normalization aid, not a restriction.
        prefs.location = free_text_location(value)

    for platform in PLATFORM_DOMAINS:
        if re.search(rf"\b{platform}\b", lowered):
            prefs.platform = platform
            break

    if re.search(r"\bsimilar\s+jobs\b", lowered):
        prefs.platform = prefs.platform or ""

    company_match = re.search(
        r"\b(?:internship|interned|worked|working)\s+at\s+([A-Z][A-Za-z0-9&.\-]+)",
        value,
    )
    if company_match:
        prefs.previous_company = company_match.group(1)

    return prefs


def fallback_role(value: str) -> str:
    """Best-effort free-text role capture for titles outside the alias table.

    Keeps user-provided titles such as "Growth Hacker" usable without hardcoding
    an exhaustive list of job titles.
    """
    cleaned = re.sub(r"[\s_]+", " ", (value or "").strip()).strip("?.! ").strip()
    words = [
        word
        for word in re.split(r"[^A-Za-z0-9&]+", cleaned)
        if word and word.casefold() not in _ROLE_FILLER
    ]
    reserved = {item.casefold() for item in KNOWN_LOCATIONS}
    candidate_words = [
        word
        for word in words
        if word.casefold() not in reserved and word.casefold() not in ("india", "remote")
    ]
    candidate = " ".join(candidate_words)
    return candidate.strip()


def missing_essential(prefs: JobPreferences) -> str:
    if not prefs.role:
        return "role"
    if not prefs.location and not prefs.remote:
        return "location"
    return ""


def clarification_question(missing: str, prefs: JobPreferences) -> str:
    if missing == "role":
        return "What role are you looking for? For example: Software Engineer, Python Developer, or Data Analyst."
    if prefs.remote:
        return "Which role and experience level should I use for the search?"
    return "Which location would you prefer? For example: Bengaluru, Delhi, Hyderabad, or anywhere in India."


def build_queries(prefs: JobPreferences) -> list[str]:
    bits = prefs.as_query_bits()
    base = " ".join(bits) if bits else "jobs"
    location = prefs.location or ("Remote" if prefs.remote else "India")
    queries = [f"{base} jobs in {location}"]
    if prefs.skills:
        queries.append(f"{' '.join(prefs.skills[:3])} {prefs.experience or 'entry level'} jobs {location}")
    if prefs.platform:
        queries.append(f"{prefs.platform} {base} jobs {location}")
    return queries[:3]


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_listing(item: dict[str, Any], prefs: JobPreferences) -> dict[str, Any] | None:
    url = _clean_text(item.get("url"))
    if not url.startswith(("http://", "https://")) or _url_quality(url) < 0:
        return None
    title = _clean_text(item.get("title"))
    content = _clean_text(item.get("content"))
    if not title:
        return None
    title = re.sub(r"\s[-|–—]\s*$", "", title).strip()

    combined = f"{title} {content}".casefold()
    platform = prefs.platform
    host = re.sub(r"^www\.", "", re.split(r"/", url.replace("https://", "").replace("http://", ""))[0])
    if not platform:
        for name, domains in PLATFORM_DOMAINS.items():
            if any(domain in host for domain in domains):
                platform = name
                break
    if not platform:
        platform = host.split(".")[0] if host else "Web"

    company = ""
    title_part = re.split(r"\s[-|–—]\s", title)[0]
    company_match = re.search(r"\bat\s+(.+)$", title_part, re.IGNORECASE)
    if company_match:
        company = _clean_text(company_match.group(1))

    # Fields are extracted from the result itself.  Never copy the user's query
    # preferences onto a result; that made every row look identical.
    location = None
    for source in (title, content):
        lowered_source = source.casefold()
        for key, canonical in LOCATION_CANONICAL.items():
            if key == "remote":
                continue
            if re.search(rf"\b{re.escape(key)}\b", lowered_source):
                location = canonical
                break
        if location:
            break

    experience = None
    if re.search(
        r"\b(?:freshers?|entry[\s-]?levels?|graduates?|0\s*[-–]\s*2\s*years?)\b",
        combined,
    ):
        experience = "Fresher / entry-level"
    else:
        match = re.search(r"\b\d+\s*[-–]\s*\d+\s*years?\b", content, re.IGNORECASE)
        if match:
            experience = match.group(0)

    employment = None
    if re.search(r"\bfull[\s-]?time\b", combined):
        employment = "Full-time"
    elif re.search(r"\bpart[\s-]?time\b", combined):
        employment = "Part-time"
    elif re.search(r"\binternships?\b", combined):
        employment = "Internship"
    elif re.search(r"\bremote\b(?!\s*\()", combined) or re.search(
        r"\bwork\s+from\s+home\b", combined
    ):
        # "Remote(10)" is a facet count on a listing page, not a job attribute.
        employment = "Remote"

    skills = [skill for skill in prefs.skills if skill.casefold() in combined]
    salary = None
    salary_match = re.search(
        r"(?:₹|\$|€|£)\s?\d[\d,.]*\s*(?:lpa|per\s+annum|k|a\s+month)?",
        content,
        re.IGNORECASE,
    )
    if salary_match:
        salary = _clean_text(salary_match.group(0))

    cleaned_content = _strip_navigation_boilerplate(content)
    description = cleaned_content[:400].rstrip() or None
    return {
        "kind": "job",
        "title": title,
        "company": company or None,
        "location": location,
        "experience": experience,
        "employment_type": employment,
        "salary": salary,
        "description": description,
        "skills": skills,
        "url": url,
        "source": platform,
        "search_date": time.strftime("%Y-%m-%d"),
        "score": float(item.get("score") or 0.0),
    }


def _dedupe_and_rank(listings: list[dict[str, Any]], prefs: JobPreferences) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for listing in listings:
        key = (
            re.sub(r"[^a-z0-9]", "", listing["title"].casefold()),
            re.sub(r"[^a-z0-9]", "", str(listing.get("company") or "").casefold()),
            listing["url"].split("?")[0].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(listing)

    role_terms = [term.casefold() for term in re.findall(r"[A-Za-z]+", prefs.role)]
    for listing in unique:
        combined = f"{listing['title']} {listing.get('description') or ''}".casefold()
        relevance = 0.0
        if any(term in combined for term in role_terms):
            relevance += 4.0
        relevance += 2.0 * _url_quality(listing["url"])
        relevance += min(len([skill for skill in prefs.skills if skill.casefold() in combined]), 4) * 1.5
        if prefs.location and prefs.location.casefold() in combined:
            relevance += 2.0
        if prefs.remote and "remote" in combined:
            relevance += 2.0
        if prefs.experience and "fresher" in prefs.experience.casefold():
            if re.search(r"\b(?:fresher|entry[\s-]?level|graduate|0\s*[-–]\s*2)\b", combined):
                relevance += 3.0
        if prefs.platform and listing["source"].casefold() == prefs.platform.casefold():
            relevance += 2.0
        listing["relevance"] = relevance + listing["score"]

    unique.sort(key=lambda item: item["relevance"], reverse=True)
    return unique[:TAVILY_MAX_RESULTS]


def _cache_key(queries: list[str], platform: str) -> str:
    return "|".join(queries) + "::" + platform


async def search_jobs(prefs: JobPreferences) -> list[dict[str, Any]]:
    """JSearch first; fall back to Tavily when it returns nothing or fails."""
    queries = build_queries(prefs)
    key = _cache_key(queries, prefs.platform)
    cached = _cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    listings: list[dict[str, Any]] = []
    try:
        from app.services.job_providers import JSearchProvider

        listings = await JSearchProvider().search(prefs)
    except Exception:
        # A provider outage must not break the whole search.
        listings = []

    if not listings:
        listings = await _search_tavily(prefs, queries=queries)

    results = _dedupe_and_rank(listings, prefs)
    _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, results)
    return results


async def _search_tavily(
    prefs: JobPreferences, queries: list[str] | None = None
) -> list[dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise TavilyError("Job search is not configured. Please add the Tavily API key on the server.")

    queries = queries if queries is not None else build_queries(prefs)
    domains = PLATFORM_DOMAINS.get(prefs.platform, [])
    validate_with_llm = os.getenv("JOB_SEARCH_LLM_VALIDATION", "true").strip().casefold() in {
        "1", "true", "yes"
    }
    llm_client = _tavily_llm_client() if validate_with_llm else None
    listings: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=TAVILY_TIMEOUT_SECONDS) as client:
            for query in queries:
                payload: dict[str, Any] = {
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5,
                    "include_answer": False,
                    "include_raw_content": False,
                    "exclude_domains": list(_TAVILY_EXCLUDE_DOMAINS),
                    "time_range": "month",
                }
                if domains:
                    payload["include_domains"] = domains
                response = await client.post(TAVILY_API_URL, json=payload)
                response.raise_for_status()
                data = response.json()
                for item in data.get("results") or []:
                    if not isinstance(item, dict):
                        continue
                    parsed = _parse_listing(item, prefs)
                    if not parsed:
                        continue
                    extraction = await _extract_job_posting(item, llm_client)
                    if extraction is not None:
                        if not extraction.is_single_posting:
                            continue
                        if extraction.title:
                            parsed["title"] = _clean_text(extraction.title)
                        if extraction.company:
                            parsed["company"] = _clean_text(extraction.company)
                        if extraction.location:
                            parsed["location"] = normalize_location(extraction.location) or _clean_text(extraction.location)
                        if extraction.employment_type:
                            parsed["employment_type"] = _clean_text(extraction.employment_type)
                        if extraction.apply_url and extraction.apply_url.startswith(("http://", "https://")):
                            parsed["url"] = extraction.apply_url
                    listings.append(parsed)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise TavilyError("Job search is not configured correctly. Please check the Tavily API key on the server.") from exc
        if exc.response.status_code == 429:
            raise TavilyError("The job search service is rate limited. Please try again shortly.") from exc
        raise TavilyError("The job search service could not complete the request. Please try again.") from exc
    except httpx.HTTPError as exc:
        raise TavilyError("The job search service could not be reached. Please try again shortly.") from exc
    except ValueError as exc:
        raise TavilyError("The job search service returned an unreadable response.") from exc

    return listings


def job_sources(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in listing.items() if key not in ("relevance", "score")}
        for listing in listings
    ]


def format_job_answer(listings: list[dict[str, Any]], prefs: JobPreferences) -> str:
    if not listings:
        return "I could not find any public job listings matching those preferences. Try a broader role, a different location, or fewer skill filters."
    scope = f"{prefs.role or 'your search'}"
    if prefs.location:
        scope += f" in {prefs.location}"
    elif prefs.remote:
        scope += " (remote)"
    lines = [
        f"I found {len(listings)} public job listing(s) for {scope}. "
        "These are publicly indexed results, not verified open positions. "
        "Check the original posting before applying."
    ]
    for listing in listings[:TAVILY_MAX_RESULTS]:
        title = listing.get("title") or "Untitled role"
        company = listing.get("company") or "Not specified"
        location = listing.get("location") or "Not specified"
        experience = listing.get("experience") or "Not specified"
        lines.append(
            f"- {title} at {company} | {location} | {experience} | "
            f"{listing.get('employment_type') or 'Not specified'}"
        )
        if listing.get("url"):
            lines.append(f"  Apply: {listing['url']}")
    return "\n".join(lines)


def clear_cache() -> None:
    _cache.clear()
