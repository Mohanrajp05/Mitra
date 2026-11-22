from typing import Sequence

from app.rag.vector_store import SearchHit, StoredDocument

MAX_EVIDENCE_CHARS = 1_200


def assemble_document_text(document: StoredDocument) -> str:
    ordered = sorted(document.chunks, key=lambda chunk: chunk.chunk_index)
    return "\n\n".join(chunk.content for chunk in ordered).strip()


def format_evidence(hits: Sequence[SearchHit]) -> str:
    blocks: list[str] = []

    for index, hit in enumerate(hits, start=1):
        content = hit.content
        if len(content) > MAX_EVIDENCE_CHARS:
            content = content[:MAX_EVIDENCE_CHARS] + "..."
        blocks.append(
            f"[{index}] source_type={hit.source_type} file={hit.filename} "
            f"document_id={hit.document_id} chunk_index={hit.chunk_index} "
            f"score={hit.score:.4f}\n{content}"
        )

    return "\n\n".join(blocks)


def evidence_references(hits: Sequence[SearchHit]) -> list[dict]:
    return [
        {
            "document_id": hit.document_id,
            "chunk_id": hit.chunk_id,
            "chunk_index": hit.chunk_index,
            "score": round(hit.score, 4),
            "source_type": hit.source_type,
            "filename": hit.filename,
        }
        for hit in hits
    ]
