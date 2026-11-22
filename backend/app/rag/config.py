import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = BACKEND_DIR / "data" / "rag"

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIMENSION = 384

SOURCE_TYPES = ("resume", "job_description", "knowledge")
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


def _text_env(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc


def _path_env(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return Path(raw).expanduser()


@dataclass(frozen=True)
class RagSettings:
    data_dir: Path
    embeddings_dir: Path
    metadata_dir: Path
    documents_dir: Path
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    embedding_batch_size: int = 32
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_upload_bytes: int = 5 * 1024 * 1024
    max_text_chars: int = 200_000
    max_query_chars: int = 1_000
    default_top_k: int = 5
    max_top_k: int = 20
    min_similarity: float = 0.0
    evidence_min_score: float = 0.18
    allowed_extensions: tuple[str, ...] = ALLOWED_EXTENSIONS
    source_types: tuple[str, ...] = SOURCE_TYPES

    def __post_init__(self) -> None:
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be greater than zero.")
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be greater than zero.")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero.")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must not be negative.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        if self.max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be greater than zero.")
        if self.max_text_chars <= 0:
            raise ValueError("max_text_chars must be greater than zero.")
        if self.max_query_chars <= 0:
            raise ValueError("max_query_chars must be greater than zero.")
        if self.default_top_k <= 0:
            raise ValueError("default_top_k must be greater than zero.")
        if self.max_top_k < self.default_top_k:
            raise ValueError("max_top_k must be greater than or equal to default_top_k.")
        if not -1.0 <= self.min_similarity <= 1.0:
            raise ValueError("min_similarity must be between -1 and 1.")
        if not -1.0 <= self.evidence_min_score <= 1.0:
            raise ValueError("evidence_min_score must be between -1 and 1.")

    @property
    def allow_model_download(self) -> bool:
        return os.getenv("RAG_ALLOW_MODEL_DOWNLOAD", "").strip() == "1"

    def ensure_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.embeddings_dir,
            self.metadata_dir,
            self.documents_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def load_settings(base_dir: Path | str | None = None, **overrides: Any) -> RagSettings:
    data_dir = _path_env("RAG_DATA_DIR", Path(base_dir) if base_dir else DEFAULT_DATA_DIR)
    values: dict[str, Any] = {
        "embedding_model": _text_env("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        "embedding_dimension": _int_env("RAG_EMBEDDING_DIMENSION", DEFAULT_EMBEDDING_DIMENSION),
        "embedding_batch_size": _int_env("RAG_EMBEDDING_BATCH_SIZE", 32),
        "chunk_size": _int_env("RAG_CHUNK_SIZE", 1000),
        "chunk_overlap": _int_env("RAG_CHUNK_OVERLAP", 200),
        "max_upload_bytes": _int_env("RAG_MAX_UPLOAD_BYTES", 5 * 1024 * 1024),
        "max_text_chars": _int_env("RAG_MAX_TEXT_CHARS", 200_000),
        "max_query_chars": _int_env("RAG_MAX_QUERY_CHARS", 1_000),
        "default_top_k": _int_env("RAG_DEFAULT_TOP_K", 5),
        "max_top_k": _int_env("RAG_MAX_TOP_K", 20),
        "min_similarity": _float_env("RAG_MIN_SIMILARITY", 0.0),
        "evidence_min_score": _float_env("RAG_EVIDENCE_MIN_SCORE", 0.18),
    }
    values.update(overrides)

    resolved = Path(values.pop("data_dir", data_dir)).expanduser().resolve()
    return RagSettings(
        data_dir=resolved,
        embeddings_dir=resolved / "embeddings",
        metadata_dir=resolved / "metadata",
        documents_dir=resolved / "documents",
        **values,
    )


rag_settings = load_settings()
