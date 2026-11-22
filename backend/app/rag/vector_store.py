import io
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np

from app.rag.config import RagSettings, rag_settings
from app.rag import document_cache
from app.rag.document_loader import EmptyDocumentError, load_document
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.splitter import hash_content, split_text

JSON_SUFFIX = ".json"
EMBEDDING_SUFFIX = ".npy"
DOCUMENT_SEPARATOR = "__"


class VectorStoreError(RuntimeError):
    pass


class VectorStoreIOError(VectorStoreError):
    pass


class InvalidIdentifierError(ValueError):
    pass


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    chunk_index: int
    content: str
    content_hash: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class StoredDocument:
    document_id: str
    owner_user_id: str
    source_type: str
    candidate_id: str | None
    job_id: str | None
    filename: str
    mime_type: str
    byte_size: int
    content_hash: str
    embedding_model: str
    embedding_dimension: int
    chunk_size: int
    chunk_overlap: int
    created_at: str
    updated_at: str
    chunks: tuple[StoredChunk, ...]
    created: bool = True

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def summary(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "owner_user_id": self.owner_user_id,
            "source_type": self.source_type,
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "byte_size": self.byte_size,
            "content_hash": self.content_hash,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_metadata(self) -> dict[str, Any]:
        payload = self.summary()
        payload["chunks"] = [
            {
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
            }
            for chunk in self.chunks
        ]
        return payload

    @classmethod
    def from_metadata(
        cls, data: dict[str, Any], created: bool = True
    ) -> "StoredDocument":
        chunks = tuple(
            StoredChunk(
                chunk_id=str(item.get("chunk_id") or ""),
                chunk_index=int(item.get("chunk_index", 0)),
                content=str(item.get("content") or ""),
                content_hash=str(item.get("content_hash") or ""),
                char_start=int(item.get("char_start", 0)),
                char_end=int(item.get("char_end", 0)),
            )
            for item in data.get("chunks") or []
            if isinstance(item, dict)
        )

        return cls(
            document_id=str(data.get("document_id") or ""),
            owner_user_id=str(data.get("owner_user_id") or ""),
            source_type=str(data.get("source_type") or ""),
            candidate_id=data.get("candidate_id"),
            job_id=data.get("job_id"),
            filename=str(data.get("filename") or ""),
            mime_type=str(data.get("mime_type") or ""),
            byte_size=int(data.get("byte_size", 0)),
            content_hash=str(data.get("content_hash") or ""),
            embedding_model=str(data.get("embedding_model") or ""),
            embedding_dimension=int(data.get("embedding_dimension", 0)),
            chunk_size=int(data.get("chunk_size", 0)),
            chunk_overlap=int(data.get("chunk_overlap", 0)),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            chunks=chunks,
            created=created,
        )


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    chunk_id: str
    chunk_index: int
    content: str
    score: float
    source_type: str
    filename: str
    candidate_id: str | None
    job_id: str | None
    created_at: str


@dataclass(frozen=True)
class RebuildReport:
    scanned: int
    rebuilt: int
    skipped: int
    removed: int

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "rebuilt": self.rebuilt,
            "skipped": self.skipped,
            "removed": self.removed,
        }


def _validate_uuid(value: Any, field: str) -> str:
    try:
        return str(uuid.UUID(str(value).strip()))
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidIdentifierError(
            f"{field} must be a valid UUID."
        ) from exc


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    _write_bytes(path, serialized.encode("utf-8"))


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def document_text_from_metadata(data: dict[str, Any]) -> str:
    chunks = [
        item for item in data.get("chunks") or [] if isinstance(item, dict)
    ]
    ordered = sorted(chunks, key=lambda item: item.get("chunk_index", 0))
    return "\n\n".join(
        str(item.get("content") or "") for item in ordered
    ).strip()


class LocalVectorStore:
    def __init__(
        self,
        settings: RagSettings | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings or rag_settings
        self._embedding_service = embedding_service
        self._lock = threading.RLock()

    @property
    def embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service(self.settings)
        return self._embedding_service

    def ensure_directories(self) -> None:
        self.settings.ensure_directories()

    def _metadata_path(self, document_id: str) -> Path:
        return self.settings.metadata_dir / f"{document_id}{JSON_SUFFIX}"

    def _embedding_path(self, document_id: str) -> Path:
        return self.settings.embeddings_dir / f"{document_id}{EMBEDDING_SUFFIX}"

    def _original_path(self, document_id: str, filename: str) -> Path:
        return self.settings.documents_dir / f"{document_id}{DOCUMENT_SEPARATOR}{filename}"

    def _iter_metadata(self) -> Iterator[dict[str, Any]]:
        directory = self.settings.metadata_dir
        if not directory.exists():
            return

        for path in sorted(directory.glob(f"*{JSON_SUFFIX}")):
            data = _read_json(path)
            if data is not None:
                yield data

    def _read_metadata(self, document_id: str) -> dict[str, Any] | None:
        return _read_json(self._metadata_path(document_id))

    def _read_embeddings(self, document_id: str) -> np.ndarray | None:
        path = self._embedding_path(document_id)
        if not path.exists():
            return None

        try:
            matrix = np.load(path, allow_pickle=False)
        except (OSError, ValueError):
            return None

        if matrix.ndim != 2:
            return None

        return matrix.astype(np.float32, copy=False)

    def _write_embeddings(self, document_id: str, vectors: np.ndarray) -> None:
        buffer = io.BytesIO()
        np.save(buffer, np.asarray(vectors, dtype=np.float32), allow_pickle=False)
        _write_bytes(self._embedding_path(document_id), buffer.getvalue())

    def _find_duplicate(
        self,
        owner_user_id: str,
        content_hash: str,
        source_type: str,
        candidate_id: str | None,
        job_id: str | None,
    ) -> StoredDocument | None:
        for data in self._iter_metadata():
            if data.get("owner_user_id") != owner_user_id:
                continue
            if data.get("content_hash") != content_hash:
                continue
            if data.get("source_type") != source_type:
                continue
            if data.get("candidate_id") != candidate_id:
                continue
            if data.get("job_id") != job_id:
                continue
            return StoredDocument.from_metadata(data, created=False)

        return None

    def save_document(
        self,
        owner_user_id: str,
        *,
        filename: str,
        data: bytes,
        source_type: str,
        candidate_id: str | None = None,
        job_id: str | None = None,
        content_type: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> StoredDocument:
        owner = _validate_uuid(owner_user_id, "owner_user_id")

        if source_type not in self.settings.source_types:
            allowed = ", ".join(self.settings.source_types)
            raise ValueError(f"source_type must be one of: {allowed}.")

        candidate = (
            _validate_uuid(candidate_id, "candidate_id") if candidate_id else None
        )
        job = _validate_uuid(job_id, "job_id") if job_id else None

        loaded = load_document(
            filename=filename,
            data=data,
            max_bytes=self.settings.max_upload_bytes,
            max_chars=self.settings.max_text_chars,
            content_type=content_type,
        )

        size = self.settings.chunk_size if chunk_size is None else int(chunk_size)
        step = self.settings.chunk_overlap if chunk_overlap is None else int(chunk_overlap)

        chunks = split_text(loaded.text, size, step)
        if not chunks:
            raise EmptyDocumentError(
                "The document did not produce any usable text chunks."
            )

        # The text was just extracted; keep it so callers (interview profile,
        # question generation) never have to parse the same file again.
        document_cache.set_document_text(loaded.content_hash, loaded.text)

        with self._lock:
            duplicate = self._find_duplicate(
                owner, loaded.content_hash, source_type, candidate, job
            )
            if duplicate is not None:
                return duplicate

            document_id = str(uuid.uuid4())
            vectors = self.embedding_service.embed_texts(
                [chunk.content for chunk in chunks]
            )
            timestamp = datetime.now(timezone.utc).isoformat()

            record = StoredDocument(
                document_id=document_id,
                owner_user_id=owner,
                source_type=source_type,
                candidate_id=candidate,
                job_id=job,
                filename=loaded.filename,
                mime_type=loaded.mime_type,
                byte_size=loaded.byte_size,
                content_hash=loaded.content_hash,
                embedding_model=self.embedding_service.model_name,
                embedding_dimension=int(vectors.shape[1]),
                chunk_size=size,
                chunk_overlap=step,
                created_at=timestamp,
                updated_at=timestamp,
                chunks=tuple(
                    StoredChunk(
                        chunk_id=str(uuid.uuid4()),
                        chunk_index=chunk.index,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                    )
                    for chunk in chunks
                ),
            )

            try:
                self.ensure_directories()
                self._write_embeddings(document_id, vectors)
                _write_json(self._metadata_path(document_id), record.to_metadata())
                _write_bytes(
                    self._original_path(document_id, loaded.filename), data
                )
            except OSError as exc:
                self._cleanup_document(document_id, loaded.filename)
                raise VectorStoreIOError(
                    "The document could not be stored locally."
                ) from exc

            return record

    def get_document(
        self, owner_user_id: str, document_id: str
    ) -> StoredDocument | None:
        owner = _validate_uuid(owner_user_id, "owner_user_id")
        document = _validate_uuid(document_id, "document_id")

        data = self._read_metadata(document)
        if data is None or data.get("owner_user_id") != owner:
            return None

        return StoredDocument.from_metadata(data)

    def open_original(
        self, owner_user_id: str, document_id: str
    ) -> tuple[Path, str, str] | None:
        """Return (path, mime_type, filename) for the stored original file.

        The document must belong to ``owner_user_id``; anything else returns
        None so callers can answer with a uniform 404 (no existence leak).
        The resolved path is verified to stay inside the documents directory
        before it is handed to a file response.
        """
        record = self.get_document(owner_user_id, document_id)
        if record is None:
            return None

        path = self._original_path(record.document_id, record.filename)
        if not path.exists():
            return None

        resolved = path.resolve()
        base = self.settings.documents_dir.resolve()
        if base not in resolved.parents:
            return None

        return resolved, record.mime_type, record.filename

    def list_documents(self, owner_user_id: str) -> list[dict[str, Any]]:
        owner = _validate_uuid(owner_user_id, "owner_user_id")

        documents = [
            StoredDocument.from_metadata(data).summary()
            for data in self._iter_metadata()
            if data.get("owner_user_id") == owner
        ]
        documents.sort(key=lambda item: item["created_at"], reverse=True)

        return documents

    def delete_document(self, owner_user_id: str, document_id: str) -> bool:
        owner = _validate_uuid(owner_user_id, "owner_user_id")
        document = _validate_uuid(document_id, "document_id")

        with self._lock:
            data = self._read_metadata(document)
            if data is None or data.get("owner_user_id") != owner:
                return False

            filename = str(data.get("filename") or "")
            content_hash = str(data.get("content_hash") or "") or None
            try:
                self._cleanup_document(document, filename)
            except OSError as exc:
                raise VectorStoreIOError(
                    "The document could not be deleted."
                ) from exc
            document_cache.invalidate(content_hash)

            return True

    def _cleanup_document(self, document_id: str, filename: str) -> None:
        paths = [
            self._metadata_path(document_id),
            self._embedding_path(document_id),
        ]
        if filename:
            paths.append(self._original_path(document_id, filename))

        for path in paths:
            path.unlink(missing_ok=True)

        if filename:
            prefix = f"{document_id}{DOCUMENT_SEPARATOR}"
            for path in self.settings.documents_dir.glob(f"{prefix}*"):
                path.unlink(missing_ok=True)

    def document_text_for(
        self,
        owner_user_id: str,
        *,
        candidate_id: str | None = None,
        job_id: str | None = None,
        source_type: str | None = None,
    ) -> str | None:
        owner = _validate_uuid(owner_user_id, "owner_user_id")
        candidate = (
            _validate_uuid(candidate_id, "candidate_id")
            if candidate_id
            else None
        )
        job = _validate_uuid(job_id, "job_id") if job_id else None

        newest: tuple[str, str] | None = None

        for data in self._iter_metadata():
            if data.get("owner_user_id") != owner:
                continue
            if candidate is not None and data.get("candidate_id") != candidate:
                continue
            if job is not None and data.get("job_id") != job:
                continue
            if source_type is not None and data.get("source_type") != source_type:
                continue

            text = document_text_from_metadata(data)
            if not text:
                continue

            created = str(data.get("created_at") or "")
            if newest is None or created >= newest[0]:
                newest = (created, text)

        return newest[1] if newest else None

    def rebuild_index(self, owner_user_id: str | None = None) -> RebuildReport:
        owner = (
            _validate_uuid(owner_user_id, "owner_user_id")
            if owner_user_id
            else None
        )
        self.ensure_directories()

        scanned = 0
        rebuilt = 0
        skipped = 0
        removed = 0
        known: set[str] = set()

        with self._lock:
            for data in self._iter_metadata():
                if owner is not None and data.get("owner_user_id") != owner:
                    continue

                scanned += 1
                document_id = str(data.get("document_id") or "")
                chunks = [
                    item
                    for item in data.get("chunks") or []
                    if isinstance(item, dict)
                ]
                if not document_id or not chunks:
                    skipped += 1
                    continue

                known.add(document_id)
                matrix = self._read_embeddings(document_id)
                is_current = (
                    matrix is not None
                    and matrix.shape
                    == (len(chunks), self.settings.embedding_dimension)
                    and data.get("embedding_model")
                    == self.embedding_service.model_name
                    and data.get("embedding_dimension")
                    == self.settings.embedding_dimension
                )
                if is_current:
                    skipped += 1
                    continue

                vectors = self.embedding_service.embed_texts(
                    [str(item.get("content") or "") for item in chunks]
                )
                self._write_embeddings(document_id, vectors)
                data["embedding_model"] = self.embedding_service.model_name
                data["embedding_dimension"] = int(vectors.shape[1])
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                _write_json(self._metadata_path(document_id), data)
                rebuilt += 1

            if owner is None:
                for path in self.settings.embeddings_dir.glob(f"*{EMBEDDING_SUFFIX}"):
                    if path.stem in known:
                        continue
                    path.unlink(missing_ok=True)
                    removed += 1

        return RebuildReport(
            scanned=scanned, rebuilt=rebuilt, skipped=skipped, removed=removed
        )

    def validate_top_k(self, top_k: int | None) -> int:
        limit = self.settings.default_top_k if top_k is None else int(top_k)
        if limit <= 0:
            raise ValueError("top_k must be greater than zero.")
        if limit > self.settings.max_top_k:
            raise ValueError(
                f"top_k must not be greater than {self.settings.max_top_k}."
            )
        return limit

    def search(
        self,
        owner_user_id: str,
        *,
        query: str | None = None,
        query_embedding: np.ndarray | None = None,
        top_k: int | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        source_types: tuple[str, ...] | list[str] | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> list[SearchHit]:
        owner = _validate_uuid(owner_user_id, "owner_user_id")
        limit = self.validate_top_k(top_k)
        candidate = (
            _validate_uuid(candidate_id, "candidate_id") if candidate_id else None
        )
        job = _validate_uuid(job_id, "job_id") if job_id else None
        allowed_sources = set(source_types) if source_types else None
        allowed_documents = (
            {
                _validate_uuid(item, "document_id")
                for item in document_ids
                if str(item).strip()
            }
            if document_ids
            else None
        )

        if query_embedding is None:
            text = (query or "").strip()
            if not text:
                raise ValueError("A search query is required.")
            if len(text) > self.settings.max_query_chars:
                raise ValueError("The search query is too long.")
            query_embedding = self.embedding_service.embed_query(text)

        vector = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        if vector.shape[0] != self.settings.embedding_dimension:
            raise ValueError(
                f"The query embedding must have {self.settings.embedding_dimension} dimensions."
            )

        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return []
        vector = vector / norm

        scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []

        for data in self._iter_metadata():
            if data.get("owner_user_id") != owner:
                continue
            if candidate is not None and data.get("candidate_id") != candidate:
                continue
            if job is not None and data.get("job_id") != job:
                continue
            if allowed_sources is not None and data.get("source_type") not in allowed_sources:
                continue
            if allowed_documents is not None and str(data.get("document_id") or "") not in allowed_documents:
                continue
            if data.get("embedding_model") != self.embedding_service.model_name:
                continue

            chunks = [
                item for item in data.get("chunks") or [] if isinstance(item, dict)
            ]
            if not chunks:
                continue

            matrix = self._read_embeddings(str(data.get("document_id") or ""))
            if matrix is None:
                continue
            if matrix.shape != (len(chunks), vector.shape[0]):
                continue

            similarities = matrix @ vector
            for chunk, score in zip(chunks, similarities):
                scored.append((float(score), data, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)

        hits: list[SearchHit] = []
        seen_content: set[str] = set()
        for score, data, chunk in scored:
            if score < self.settings.min_similarity:
                continue
            digest = str(chunk.get("content_hash") or "")
            if not digest:
                digest = hash_content(str(chunk.get("content") or ""))
            if digest in seen_content:
                continue
            seen_content.add(digest)
            hits.append(
                SearchHit(
                    document_id=str(data.get("document_id") or ""),
                    chunk_id=str(chunk.get("chunk_id") or ""),
                    chunk_index=int(chunk.get("chunk_index", 0)),
                    content=str(chunk.get("content") or ""),
                    score=score,
                    source_type=str(data.get("source_type") or ""),
                    filename=str(data.get("filename") or ""),
                    candidate_id=data.get("candidate_id"),
                    job_id=data.get("job_id"),
                    created_at=str(data.get("created_at") or ""),
                )
            )
            if len(hits) >= limit:
                break

        return hits


_document_store: LocalVectorStore | None = None


def get_document_store() -> LocalVectorStore:
    global _document_store

    if _document_store is None:
        _document_store = LocalVectorStore()

    return _document_store


def set_document_store(store: LocalVectorStore | None) -> None:
    global _document_store
    _document_store = store


def reset_document_store() -> None:
    set_document_store(None)
