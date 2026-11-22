import hashlib
import re
from dataclasses import dataclass

from app.rag.document_loader import normalize_text

MAX_UNIT_CHARS = 400
MIN_FILL_RATIO = 0.6

WHITESPACE_PATTERN = re.compile(r"\s+")

BOUNDARY_SEPARATORS = ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ")


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    content_hash: str
    char_start: int
    char_end: int


def hash_content(content: str) -> str:
    normalized = WHITESPACE_PATTERN.sub(" ", content).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _snap_end(text: str, start: int, end: int) -> int:
    floor = start + max(1, int((end - start) * MIN_FILL_RATIO))
    window = text[floor:end]

    for separator in BOUNDARY_SEPARATORS:
        position = window.rfind(separator)
        if position != -1:
            return floor + position + len(separator)

    return end


def _snap_start(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def split_text(text: str, chunk_size: int, overlap: int) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if overlap < 0:
        raise ValueError("overlap must not be negative.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    normalized = normalize_text(text)
    if not normalized:
        return []

    length = len(normalized)
    chunks: list[TextChunk] = []
    seen: set[str] = set()
    start = 0

    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            end = _snap_end(normalized, start, end)

        content = normalized[start:end].strip()
        if content:
            digest = hash_content(content)
            if digest not in seen:
                seen.add(digest)
                chunks.append(
                    TextChunk(
                        index=len(chunks),
                        content=content,
                        content_hash=digest,
                        char_start=start,
                        char_end=end,
                    )
                )

        if end >= length:
            break

        next_start = end - overlap
        if next_start <= start:
            next_start = end

        start = _snap_start(normalized, next_start)

    return chunks
