

from __future__ import annotations

import re
from typing import Any


_SECTION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("projects", ("project", "portfolio")),
    ("experience", ("experience", "employment", "work history", "career")),
    ("skills", ("skill", "technolog", "tool", "competenc", "tech stack")),
    ("education", ("education", "academic", "qualification")),
    ("certifications", ("certification", "certificate", "licens", "credential")),
    ("summary", ("summary", "profile", "objective", "about me")),
)

_ROLE_WORDS = (
    "developer", "designer", "engineer", "architect", "manager", "analyst",
    "consultant", "specialist", "lead", "intern", "scientist", "coordinator",
    "administrator", "writer", "recruiter", "technician", "ux", "ui",
)

_COMPANY_SUFFIXES = (
    "ltd", "llc", "inc", "corp", "pvt", "limited", "technologies", "solutions",
    "systems", "digital", "products", "interactive", "labs", "studio", "group",
    "software", "consulting", "services", "company", "co",
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,5}\)|\d{2,5})(?:[\s.-]?\d{2,5}){1,5}")
_URL_RE = re.compile(r"(?:www\.|https?://)?[\w-]+(?:\.[\w-]+)+(?:/[\w\-./]*)?", re.I)
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
_DATE_PART = rf"(?:(?:{_MONTH}\s+)?\d{{4}}|Present|Current|Now|{_MONTH}\s+\d{{4}})"
_FULL_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_PART})\s*(?:[-–—]|to)\s*(?P<end>{_DATE_PART})",
    re.I,
)


def _clean(value: str) -> str:
    text = re.sub(r"-\s+", "-", str(value or "").strip())
    return re.sub(r"\s+", " ", text).strip(" \t•·-–—")


def _section_for_header(line: str) -> str | None:
    stripped = _clean(line).rstrip(":").strip()
    if not stripped or len(stripped) > 60 or "(" in stripped or ")" in stripped:
        return None
    lowered = stripped.lower()
    if _EMAIL_RE.search(lowered) or _PHONE_RE.search(stripped):
        return None
    for key, keywords in _SECTION_KEYWORDS:
        if any(word in lowered for word in keywords):
            return key
    return None


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        key = _section_for_header(line)
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _contact(sections: dict[str, list[str]]) -> dict[str, Any]:
    lines = sections.get("header") or []
    result: dict[str, Any] = {
        "candidate_name": None,
        "job_title": None,
        "location": None,
        "email": None,
        "phone": None,
        "links": [],
    }

    name_re = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,59}$")
    for line in lines:
        candidate = _clean(line)
        if (
            result["candidate_name"] is None
            and name_re.fullmatch(candidate)
            and 1 <= len(candidate.split()) <= 4
            and not candidate.endswith('.')
            and (len(candidate.split()) == 1 or all(word[:1].isupper() for word in candidate.split()))
            and not any(word.lower() in {"resume", "cv", "curriculum"} for word in candidate.split())
        ):
            result["candidate_name"] = candidate
            continue
        if (
            result["job_title"] is None
            and any(word in candidate.lower() for word in _ROLE_WORDS)
            and len(candidate) < 120
            and not _EMAIL_RE.search(candidate)
            and not _PHONE_RE.search(candidate)
            and not _URL_RE.search(candidate)
        ):
            result["job_title"] = candidate

    blob = " ".join(_clean(line) for line in lines)
    email = _EMAIL_RE.search(blob)
    if email:
        result["email"] = email.group(0)
    phone = _PHONE_RE.search(blob)
    if phone and len(re.sub(r"\D", "", phone.group(0))) >= 9:
        result["phone"] = _clean(phone.group(0))

    seen_links: set[str] = set()
    for match in _URL_RE.finditer(blob):
        link = match.group(0).strip(" .|")
        if "@" in link or link.lower() in seen_links:
            continue
        seen_links.add(link.lower())
        result["links"].append(link[:200])

    for line in lines:
        for segment in re.split(r"[|]", _clean(line)):
            part = _clean(segment)
            if (
                not part
                or part in {result["email"], result["phone"], result["candidate_name"], result["job_title"]}
                or _EMAIL_RE.search(part)
                or _PHONE_RE.search(part)
                or _URL_RE.search(part)
                or any(word in part.lower() for word in _ROLE_WORDS)
            ):
                continue
            if re.fullmatch(r"[A-Za-z][A-Za-z ,.'-]{1,60}", part) and ("," in part or len(part.split()) <= 2):
                result["location"] = part[:120]
                break
        if result["location"]:
            break
    return result


def _summary(sections: dict[str, list[str]]) -> str | None:
    lines = sections.get("summary") or []
    text = _clean(" ".join(lines))
    return text or None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned[:300])
    return result


_DESIGN_TERMS = (
    "figma", "adobe xd", "sketch", "wirefram", "user flow", "prototyp",
    "micro-interaction", "usability", "persona", "information architecture",
    "heuristic", "a/b testing", "journey map", "design token", "component librar",
    "storybook", "material ui", "shadcn", "responsive", "mobile-first",
    "wcag", "aria", "core web vitals", "lighthouse", "zeplin", "miro",
    "illustrator", "design system", "accessib", "user research", "interaction design",
)


def _skills(sections: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    raw_lines = sections.get("skills") or []
    if not raw_lines:
        return [], []

    # Join wrapped category labels such as "UI/UX Design &" + "Prototyping:"
    # before splitting values, so no token is cut in half.
    lines: list[str] = []
    skip_next = False
    for index, raw in enumerate(raw_lines):
        if skip_next:
            skip_next = False
            continue
        current = _clean(raw)
        following = _clean(raw_lines[index + 1]) if index + 1 < len(raw_lines) else ""
        if (
            following.endswith(":")
            and len(following) <= 45
            and (current.endswith(("&", "/", "-")) or len(current) <= 40)
            and not current.endswith(":")
        ):
            lines.append(current + " " + following)
            skip_next = True
            continue
        lines.append(current)

    label_re = re.compile(r"^(?P<label>[A-Za-z][A-Za-z &/\-]{1,60}):\s*(?P<value>.*)$")
    values: list[str] = []
    for line in lines:
        match = label_re.match(line)
        if match and len(match.group("label")) <= 45:
            values.append(match.group("value"))
        else:
            values.append(line)

    tokens: list[str] = []
    for value in values:
        for token in re.split(r"[,;|]", value):
            token = _clean(token)
            if token and len(token) <= 80:
                tokens.append(token)

    technical: list[str] = []
    design: list[str] = []
    for token in _dedupe(tokens):
        lowered = token.lower()
        if any(term in lowered for term in _DESIGN_TERMS):
            design.append(token)
        else:
            technical.append(token)
    return technical, design


def _normalize_period(blob: str) -> str | None:
    match = _FULL_RANGE_RE.search(blob)
    if not match:
        return None
    start = _clean(match.group("start"))
    end = _clean(match.group("end"))
    if not start or not end:
        return None
    return f"{start} – {end}"


def _looks_like_role(line: str) -> bool:
    lowered = line.lower()
    return any(word in lowered for word in _ROLE_WORDS) and len(line) < 160


def _split_company_location(value: str) -> tuple[str, str | None]:
    parts = [part.strip(" .,") for part in re.split(r"\s*[|]\s*", value) if part.strip()]
    if not parts:
        return "", None
    company = parts[0]
    location = parts[1] if len(parts) > 1 else None
    tokens = company.split()
    if tokens:
        last = tokens[-1].strip(" .,")
        if (
            len(tokens) > 1
            and last[:1].isupper()
            and last.lower() not in _COMPANY_SUFFIXES
            and not last.lower().endswith(("ltd", "inc", "llc"))
        ):
            location = last
            company = " ".join(tokens[:-1])
    return _clean(company), _clean(location) if location else None


def _experience(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    lines = sections.get("experience") or []
    if not lines:
        return []

    entries: list[dict[str, Any]] = []
    header_buffer: list[str] = []
    current: dict[str, Any] | None = None

    def flush_header() -> None:
        nonlocal header_buffer, current
        if not header_buffer:
            return
        blob = _clean(" ".join(header_buffer))
        period = _normalize_period(blob)
        content = blob
        if period:
            content = _clean(content.replace(period, " "))
        if "—" in content:
            title, _, rest = content.partition("—")
        elif " - " in content:
            title, _, rest = content.partition(" - ")
        else:
            title, _, rest = _clean(content).partition(" | ")
        company, location = _split_company_location(rest)
        current = {
            "title": _clean(title) or None,
            "company": company or None,
            "location": location,
            "period": period,
            "responsibilities": [],
            "achievements": [],
        }
        entries.append(current)
        header_buffer = []

    for line in lines:
        if current is None:
            header_buffer.append(line)
            if _FULL_RANGE_RE.search(" ".join(header_buffer)) or _looks_like_role(line):
                flush_header()
            continue

        joined = _clean(" ".join(header_buffer + [line])) if header_buffer else ""
        if _FULL_RANGE_RE.search(line) or (_looks_like_role(line) and "—" in line):
            flush_header()
            header_buffer.append(line)
            if _FULL_RANGE_RE.search(line):
                flush_header()
            continue
        if header_buffer:
            header_buffer.append(line)
            if _FULL_RANGE_RE.search(joined):
                flush_header()
            continue

        cleaned = _clean(line)
        if not cleaned or re.search(r"Page\s+\d+\s+of\s+\d+", cleaned, re.I):
            continue
        bullets = current["responsibilities"]
        if bullets and (
            cleaned[0].islower()
            or not bullets[-1].endswith((".", "%", "!", "?", ":"))
        ):
            bullets[-1] = _clean(bullets[-1] + " " + cleaned)[:500]
        else:
            bullets.append(cleaned[:500])
        if re.search(
            r"\d+%|\bimproving\b|\breducing\b|\bboosting\b|\bincreasing\b|\baward\b",
            bullets[-1],
            re.I,
        ):
            current["achievements"].append(bullets[-1][:500])

    flush_header()

    result = []
    for entry in entries:
        entry["responsibilities"] = _dedupe(entry["responsibilities"])[:25]
        entry["achievements"] = _dedupe(entry["achievements"])[:15]
        if entry.get("title") or entry.get("company"):
            result.append(entry)
    return result[:20]


def _projects(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    lines = sections.get("projects") or []
    projects: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        cleaned = _clean(line)
        if "|" in cleaned:
            title, _, tech = cleaned.partition("|")
            current = {
                "title": _clean(title) or None,
                "technologies": _dedupe(re.split(r"[,;]", tech))[:20],
                "description": [],
            }
            projects.append(current)
        elif current is not None:
            current["description"].append(cleaned[:500])
        elif len(cleaned) > 8:
            current = {"title": cleaned, "technologies": [], "description": []}
            projects.append(current)

    for project in projects:
        project["description"] = _dedupe(project["description"])[:20]
    return projects[:20]


def _education_and_certifications(
    sections: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    education_lines = list(sections.get("education") or [])
    education_lines.extend(sections.get("certifications") or [])

    degree_re = re.compile(
        r"\b(?:B\.?\s?Des|B\.?\s?E\.?|B\.?\s?Tech|M\.?\s?Tech|Bachelor|Master|PhD|Diploma|degree)\b",
        re.I,
    )
    cert_re = re.compile(r"\b(?:certificate|certification|certified|specialist|w3c|credential)\b", re.I)

    education: list[str] = []
    certifications: list[str] = []
    buffer: list[str] = []

    def flush_education() -> None:
        if buffer:
            text = _clean(" ".join(buffer))
            if text:
                education.append(text[:500])
            buffer.clear()

    for line in education_lines:
        cleaned = _clean(line)
        if not cleaned or re.search(r"Page\s+\d+\s+of\s+\d+", cleaned, re.I):
            continue
        if cert_re.search(cleaned):
            flush_education()
            pieces = re.split(r"\s+&\s+", cleaned) if "&" in cleaned else [cleaned]
            for piece in pieces:
                piece = _clean(piece)
                if piece and (cert_re.search(piece) or len(pieces) == 1):
                    certifications.append(piece[:300])
            continue
        if degree_re.search(cleaned):
            flush_education()
            buffer.append(cleaned)
            continue
        if buffer:
            # Preserve wrapped date ranges such as "2017 –" + "2021".
            buffer.append(line.strip() if re.fullmatch(r"\d{4}\s*[-–—]?", line.strip()) else cleaned)
        else:
            certifications.append(cleaned[:300])

    flush_education()
    return _dedupe(education)[:20], _dedupe(certifications)[:20]


def _total_experience(text: str, summary: str | None) -> str | None:
    for source in (summary or "", text or ""):
        match = re.search(r"(\d{1,2})\s*(\+)?\s*(?:years?|yrs?)\b", source, re.I)
        if match:
            return f"{match.group(1)}{'+' if match.group(2) else ''} years"
    return None


def extract_profile(document_text: str) -> dict[str, Any]:
    text = str(document_text or "")
    sections = split_sections(text)
    contact = _contact(sections)
    summary = _summary(sections)
    skills, design_skills = _skills(sections)
    experience = _experience(sections)
    projects = _projects(sections)
    education, certifications = _education_and_certifications(sections)

    responsibilities: list[str] = []
    achievements: list[str] = []
    for entry in experience:
        responsibilities.extend(entry.get("responsibilities") or [])
        achievements.extend(entry.get("achievements") or [])

    return {
        "candidate_name": contact["candidate_name"],
        "job_title": contact["job_title"],
        "location": contact["location"],
        "email": contact["email"],
        "phone": contact["phone"],
        "professional_summary": summary,
        "total_experience": _total_experience(text, summary),
        "technical_skills": skills,
        "design_skills": design_skills,
        "work_experience": experience,
        "projects": projects,
        "education": education,
        "certifications": certifications,
        "responsibilities": _dedupe(responsibilities)[:40],
        "achievements": _dedupe(achievements)[:25],
    }
