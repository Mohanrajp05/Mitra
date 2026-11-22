import hashlib
import io
import re

import numpy as np
from docx import Document as DocxDocument

from app.rag.config import RagSettings, load_settings


def build_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    return bytes(output)


def build_docx(
    paragraphs: list[str],
    table_rows: list[list[str]] | None = None,
) -> bytes:
    document = DocxDocument()

    for text in paragraphs:
        document.add_paragraph(text)

    if table_rows:
        table = document.add_table(rows=0, cols=len(table_rows[0]))
        for row in table_rows:
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = value

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class FakeEmbeddingService:
    model_name = "fake-test-model"

    def __init__(self, dimension: int = 8) -> None:
        self.dimension = dimension

    def embed_texts(self, texts, batch_size: int | None = None) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"[a-z0-9]+", str(text).lower()):
                digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                bucket = int(digest, 16) % self.dimension
                vectors[row, bucket] += 1.0

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return (vectors / norms).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]


def make_settings(base_dir, **overrides) -> RagSettings:
    values = {
        "embedding_model": FakeEmbeddingService.model_name,
        "embedding_dimension": 8,
        "chunk_size": 300,
        "chunk_overlap": 50,
        "max_upload_bytes": 1024 * 1024,
        "max_text_chars": 100_000,
        "max_query_chars": 500,
        "default_top_k": 5,
        "max_top_k": 20,
        "min_similarity": 0.0,
    }
    values.update(overrides)
    return load_settings(base_dir=base_dir, **values)
