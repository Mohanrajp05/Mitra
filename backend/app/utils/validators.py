"""Small, reusable validation helpers used by Pydantic schemas."""

import re

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_skills(values: list[str] | None) -> list[str]:
    """Trim skills, remove blanks, and drop case-insensitive duplicates."""
    if not values:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        skill = str(value).strip()
        if not skill:
            continue
        key = skill.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(skill)
    return cleaned


def is_valid_email(value: str) -> bool:
    value = value.strip()
    return len(value) <= 254 and EMAIL_PATTERN.fullmatch(value) is not None
