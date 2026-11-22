from dataclasses import dataclass
from typing import Any, Sequence

from app.rag.config import RagSettings, rag_settings
from app.rag.vector_store import LocalVectorStore, SearchHit


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    top_k: int
    hits: tuple[SearchHit, ...]
    has_evidence: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "top_k": self.top_k,
            "has_evidence": self.has_evidence,
            "hits": [
                {
                    "document_id": hit.document_id,
                    "chunk_id": hit.chunk_id,
                    "chunk_index": hit.chunk_index,
                    "content": hit.content,
                    "score": hit.score,
                    "source_type": hit.source_type,
                    "filename": hit.filename,
                    "candidate_id": hit.candidate_id,
                    "job_id": hit.job_id,
                    "created_at": hit.created_at,
                }
                for hit in self.hits
            ],
        }


class Retriever:
    def __init__(
        self,
        store: LocalVectorStore | None = None,
        settings: RagSettings | None = None,
    ) -> None:
        self.settings = settings or rag_settings
        self._store = store or LocalVectorStore(self.settings)

    @property
    def store(self) -> LocalVectorStore:
        return self._store

    def retrieve(
        self,
        owner_user_id: str,
        query: str,
        top_k: int | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        source_types: Sequence[str] | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> RetrievalResult:
        text = (query or "").strip()
        if not text:
            raise ValueError("A search query is required.")
        if len(text) > self.settings.max_query_chars:
            raise ValueError("The search query is too long.")

        limit = self._store.validate_top_k(top_k)
        search_kwargs: dict[str, Any] = {
            "owner_user_id": owner_user_id,
            "query": text,
            "top_k": limit,
            "candidate_id": candidate_id,
            "job_id": job_id,
            "source_types": tuple(source_types) if source_types else None,
        }
        if document_ids:
            search_kwargs["document_ids"] = document_ids
        hits = self._store.search(**search_kwargs)

        return RetrievalResult(
            query=text,
            top_k=limit,
            hits=tuple(hits),
            has_evidence=bool(hits),
        )


_retriever: Retriever | None = None


def get_retriever(settings: RagSettings | None = None) -> Retriever:
    global _retriever

    if _retriever is None:
        active = settings or rag_settings
        _retriever = Retriever(
            store=LocalVectorStore(active),
            settings=active,
        )

    return _retriever


def reset_retriever() -> None:
    global _retriever
    _retriever = None