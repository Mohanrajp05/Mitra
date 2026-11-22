"""In-process cache for text and profile extraction results.

Resume parsing is deterministic and can be repeated several times for the same
file (upload -> profile -> interview preparation -> replacement checks).  The
cache is keyed by the document content hash so identical bytes never trigger a
second PDF/DOCX parse or profile extraction within a process.

The cache is deliberately small and bounded: it is an optimisation only, never
a source of truth.  Any miss falls back to the stored original file.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable

_MAX_ENTRIES = 64

_lock = threading.Lock()
_texts: "OrderedDict[str, str]" = OrderedDict()
_profiles: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def _remember(
    store: "OrderedDict[str, Any]", key: str, value: Any, max_entries: int = _MAX_ENTRIES
) -> None:
    store[key] = value
    store.move_to_end(key)
    while len(store) > max_entries:
        store.popitem(last=False)


def get_document_text(content_hash: str | None) -> str | None:
    if not content_hash:
        return None
    with _lock:
        text = _texts.get(content_hash)
        if text is not None:
            _texts.move_to_end(content_hash)
        return text


def set_document_text(content_hash: str | None, text: str) -> None:
    if not content_hash or not text:
        return
    with _lock:
        _remember(_texts, content_hash, text)


def get_profile(content_hash: str | None) -> dict[str, Any] | None:
    if not content_hash:
        return None
    with _lock:
        profile = _profiles.get(content_hash)
        if profile is None:
            return None
        _profiles.move_to_end(content_hash)
        return dict(profile)


def get_or_extract_profile(
    content_hash: str | None,
    extractor: Callable[[str], dict[str, Any]],
    text: str,
) -> dict[str, Any]:
    cached = get_profile(content_hash)
    if cached is not None:
        return cached
    profile = extractor(text)
    if content_hash and isinstance(profile, dict):
        with _lock:
            _remember(_profiles, content_hash, dict(profile))
    return profile


def invalidate(content_hash: str | None) -> None:
    """Drop every derived value for a document content hash."""
    if not content_hash:
        return
    with _lock:
        _texts.pop(content_hash, None)
        _profiles.pop(content_hash, None)


def clear() -> None:
    with _lock:
        _texts.clear()
        _profiles.clear()
