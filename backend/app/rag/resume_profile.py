

from __future__ import annotations

import re

MAX_SKILLS = 60
MAX_EXPERIENCE_ENTRIES = 20
MAX_EDUCATION = 20
MAX_CERTIFICATIONS = 20
MAX_SUMMARY_CHARS = 2_000

# Section header detection. A header line is short and contains no sentence
# punctuation beyond the header words themselves.
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary",
        "professional summary",
        "profile",
        "professional profile",
        "about me",
        "about",
        "objective",
    ),
    "skills": (
        "skills",
        "technical skills",
        "core skills",
        "key skills",
        "technologies",
        "technical expertise",
        "skills & tools",
        "tools & technologies",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "career history",
        "work history",
    ),
    "education": (
        "education",
        "academic background",
        "academics",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses",
        "licences",
        "certifications & licenses",
    ),
}

_HEADER_LINE = re.compile(
    r"^(?:[\W\d]+)?(?P<header>[A-Za-z][A-Za-z &/]{1,40})(?:[\W\d]+)?$"
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# A phone-like run: optional international prefix, digit groups separated by
# spaces/dots/dashes/parens, at least 9 digits in total (so year ranges such
# as "2019 - 2023" never qualify).
_PHONE = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,5}\)|\d{1,5})(?:[\s.-]?\d{1,5}){1,5}"
)
_PHONE_MIN_DIGITS = 9
_YEARS = re.compile(
    r"(?P<years>\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)\b(?:\s+of\s+)?",
    re.IGNORECASE,
)
_YEARS_CONTEXT = re.compile(r"experience|expertise|working|industry", re.IGNORECASE)

# "Senior Engineer | Acme Corp | 2019 - 2023" / "Acme Corp — Engineer (2020-2024)"
# "Engineer at Acme Corp, 2019 to Present"
_PERIOD = re.compile(
    r"(?:(?P<start>(?:19|20)\d{2})\s*(?:-|–|—|to|until)\s*"
    r"(?P<end>(?:19|20)\d{2}|present|current|now|ongoing))",
    re.IGNORECASE,
)
_YEARS_IN_ENTRY = re.compile(
    r"\b(?P<years>\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE
)

_BULLET = re.compile(r"^\s*(?:[-–—*•·]|\d+[.)])\s+")


# Role words used to tell a job title apart from a company name in
# comma-separated entry lines ("Globex, Junior Developer, 2014 - 2016").
_ROLE_WORDS = (
    "engineer",
    "developer",
    "architect",
    "manager",
    "analyst",
    "designer",
    "consultant",
    "administrator",
    "specialist",
    "scientist",
    "intern",
    "associate",
    "coordinator",
    "director",
    "lead",
    "officer",
    "writer",
    "support",
    "accountant",
    "recruiter",
    "generalist",
    "technician",
    "operator",
    "executive",
)


def _clean_line(line: str) -> str:
    return _BULLET.sub("", (line or "").strip())


def _match_header(line: str) -> tuple[str, str] | None:
    """Return (header_key, rest) when the line opens a known section.

    Handles both standalone headers ("Experience") and inline ones with the
    content on the same line ("Skills: AWS, Azure, ..."). For inline headers
    only the head must look like a header: the content may be long (wrapped
    skill lists are common).
    """
    candidate = (line or "").strip()
    if not candidate:
        return None
    rest = ""
    if ":" in candidate:
        head, rest = candidate.split(":", 1)
        if not head.strip() or len(head.strip()) > 45:
            return None
        key = _header_key(head)
        return (key, rest.strip()) if key else None
    if len(candidate) > 45:
        return None
    key = _header_key(candidate)
    return (key, "") if key else None


def _header_key(candidate: str) -> str | None:
    candidate = candidate.rstrip(":").strip()
    match = _HEADER_LINE.match(candidate)
    if not match:
        return None
    words = re.sub(r"\s+", " ", match.group("header").strip().lower())
    for key, aliases in _HEADER_ALIASES.items():
        if words in aliases:
            return key
    return None


def _split_skills(text: str) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[,;•|\n]+", text):
        skill = token.strip(" ·-–—*")
        if not skill or len(skill) > 60:
            continue
        key = re.sub(r"\s+", " ", skill.lower())
        if key in seen:
            continue
        seen.add(key)
        skills.append(skill)
        if len(skills) >= MAX_SKILLS:
            break
    return skills


def _role_word(segment: str) -> bool:
    lowered = segment.lower()
    return any(word in lowered for word in _ROLE_WORDS)


def _parse_comma_entry(text: str, period: str | None) -> dict | None:
    """Company / title assignment for comma-separated entries.

    Only used when the line has no "Title at Company" or "|" structure. The
    segment containing a role word is the title; if neither or both segments
    look like titles, the line is skipped rather than guessed.
    """
    segments = [segment.strip() for segment in text.split(",")]
    segments = [segment for segment in segments if segment and not _PERIOD.fullmatch(segment.strip())]
    if len(segments) < 2:
        return None
    dated = [segment for segment in segments if _PERIOD.search(segment)]
    undated = [segment for segment in segments if segment not in dated]
    if len(undated) != 2 or len(dated) > 1:
        return None
    first, second = undated
    if _role_word(first) and not _role_word(second):
        title, company = first, second
    elif _role_word(second) and not _role_word(first):
        title, company = second, first
    else:
        return None
    return {"title": title, "company": company, "period": period}


def _parse_experience_line(line: str) -> dict | None:
    """Recognise one structured experience entry line.

    A structured entry mentions a period ("2019 - 2023", "2019 to Present")
    and/or an "X at Y" / "X | Y" / "X — Y" title/company pair. Anything that
    is just a sentence ("Migrated a payments platform to Kubernetes") is not
    an entry; the caller keeps it as narrative text instead.
    """
    text = _clean_line(line)
    if not text or len(text) > 200:
        return None

    period = None
    period_match = _PERIOD.search(text)
    if period_match:
        start = (period_match.group("start") or "").strip()
        end = (period_match.group("end") or "").strip()
        end = end.capitalize() if end.lower() in {"present", "current", "now", "ongoing"} else end
        period = f"{start} - {end}"

    # "Title at Company" / "Title @ Company"
    at_match = re.search(
        r"^(?P<title>[A-Za-z][^|—–-]{2,80}?)\s+(?:at|@)\s+(?P<company>[A-Za-z][^,;|—–]{1,80}?)"
        r"\s*(?:[,;|(]|\b(?:19|20)\d{2}\b|$)",
        text,
        re.IGNORECASE,
    )
    if at_match:
        title = at_match.group("title").strip(" -–—|")
        company = at_match.group("company").strip(" -–—|,")
        if title and company:
            return {"title": title, "company": company, "period": period}

    segments = [segment.strip(" -–—|") for segment in re.split(r"\s*[|—–]\s*|\s{2,}", text)]
    segments = [segment for segment in segments if segment]
    if len(segments) >= 2:
        first, second = segments[0], segments[1]
        # A leading date segment means the order is "Company | Title".
        if _PERIOD.search(first) or _YEARS_IN_ENTRY.search(first):
            company, title = (second, segments[2] if len(segments) > 2 else None)
        else:
            title, company = first, second
        if title or company:
            return {"title": title or None, "company": company or None, "period": period}

    comma_entry = _parse_comma_entry(text, period)
    if comma_entry:
        return comma_entry
    return None


def _extract_years(text: str) -> float | None:
    from app.rag.agents.matching_postcheck import NEGATION_PATTERN

    for match in _YEARS.finditer(text):
        # "No 5 years of experience" and similar negations must not count.
        sentence_start = max(
            text.rfind(". ", 0, match.start()),
            text.rfind("\n", 0, match.start()),
        )
        before = text[sentence_start + 1 if sentence_start != -1 else 0 : match.start()]
        if NEGATION_PATTERN.search(before):
            continue
        window_start = max(0, match.start() - 40)
        window = text[window_start : match.end() + 40]
        if _YEARS_CONTEXT.search(window):
            try:
                return float(match.group("years"))
            except ValueError:
                continue
    return None


def extract_profile_sections(resume_text: str) -> dict:
    """Parse the resume text into structured sections (deterministic only).

    Returns a dict with keys ``summary``, ``skills``, ``experience``,
    ``education``, ``certifications``, ``total_years``, ``email`` and
    ``phone``. Sections the text does not clearly contain are left empty.
    """
    text = (resume_text or "").replace("\r\n", "\n").strip()
    result: dict = {
        "summary": None,
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "total_years": None,
        "email": None,
        "phone": None,
    }
    if not text:
        return result

    email = _EMAIL.search(text)
    if email:
        result["email"] = email.group(0)[:254]
    for match in _PHONE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < _PHONE_MIN_DIGITS or len(digits) > 15:
            continue
        result["phone"] = re.sub(r"\s+", " ", match.group(0)).strip()[:30]
        break
    result["total_years"] = _extract_years(text)

    current: str | None = None
    narrative: list[str] = []
    narrative_buffer: list[str] = []

    def flush_narrative() -> None:
        if current == "summary" and narrative_buffer:
            summary = re.sub(r"\s+", " ", " ".join(narrative_buffer)).strip()
            if summary:
                result["summary"] = summary[:MAX_SUMMARY_CHARS]
        elif current == "experience" and narrative_buffer:
            # Narrative experience lines without company/date structure are
            # kept out of the structured entries; they stay available to the
            # caller as plain text.
            pass
        narrative_buffer.clear()

    for raw_line in text.split("\n"):
        line = _clean_line(raw_line)
        if not line:
            continue
        header = _match_header(line)
        if header:
            flush_narrative()
            current, rest = header
            if rest:
                # Inline header content ("Skills: AWS, Azure, ...").
                if current == "skills":
                    result["skills"].extend(_split_skills(rest))
                    result["skills"] = _dedupe(result["skills"])[:MAX_SKILLS]
                elif current == "summary":
                    narrative_buffer.append(rest)
                elif current == "education" and len(rest) <= 300:
                    result["education"].append(rest)
                    result["education"] = result["education"][:MAX_EDUCATION]
                elif current == "certifications" and len(rest) <= 300:
                    result["certifications"].append(rest)
                    result["certifications"] = result["certifications"][:MAX_CERTIFICATIONS]
                elif current == "experience":
                    entry = _parse_experience_line(rest)
                    if entry and len(result["experience"]) < MAX_EXPERIENCE_ENTRIES:
                        result["experience"].append(entry)
            continue
        if current == "skills":
            result["skills"].extend(_split_skills(line))
            result["skills"] = _dedupe(result["skills"])[:MAX_SKILLS]
        elif current == "education":
            if len(line) <= 300:
                result["education"].append(line)
                result["education"] = result["education"][:MAX_EDUCATION]
        elif current == "certifications":
            if len(line) <= 300:
                result["certifications"].append(line)
                result["certifications"] = result["certifications"][:MAX_CERTIFICATIONS]
        elif current == "experience":
            entry = _parse_experience_line(line)
            if entry and len(result["experience"]) < MAX_EXPERIENCE_ENTRIES:
                result["experience"].append(entry)
            else:
                narrative_buffer.append(line)
        elif current == "summary":
            narrative_buffer.append(line)
        else:
            narrative.append(line)
    flush_narrative()

    # Narrative lines before the first header can still hold a leading
    # summary-style paragraph when no explicit header exists; keep the parse
    # conservative and leave summary empty in that case.

    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = re.sub(r"\s+", " ", value.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
