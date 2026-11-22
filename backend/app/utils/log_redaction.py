"""Redaction helpers for diagnostic logs.

Chat messages, resumes, and candidate profiles are never logged in full. When
a free-text value must appear in a log line for debugging, pass it through
``redact_text`` first: it replaces email addresses, bearer-style tokens, and
long digit sequences so trace information stays useful without exposing
personal or confidential values.
"""

import re

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_PATTERN = re.compile(
    r"(?:bearer\s+|token[=:\s]+|api[_-]?key[=:\s]+)\S+",
    re.IGNORECASE,
)
DIGITS_PATTERN = re.compile(r"\d{7,}")


def redact_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = TOKEN_PATTERN.sub("[REDACTED]", cleaned)
    cleaned = EMAIL_PATTERN.sub("[REDACTED]", cleaned)
    cleaned = DIGITS_PATTERN.sub("[REDACTED]", cleaned)
    return cleaned
