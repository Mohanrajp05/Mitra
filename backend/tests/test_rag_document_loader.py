import pytest

from app.rag.document_loader import (
    DocumentError,
    EmptyDocumentError,
    FileTooLargeError,
    InvalidDocumentError,
    UnsupportedFileTypeError,
    load_document,
    normalize_text,
    validate_filename,
)
from tests.rag_helpers import build_docx, build_pdf

MAX_BYTES = 1024 * 1024
MAX_CHARS = 100_000


def load(filename, data, content_type=None):
    return load_document(filename, data, MAX_BYTES, MAX_CHARS, content_type)


def test_extracts_text_from_pdf():
    document = load(
        "resume.pdf", build_pdf("Senior Python Engineer with FastAPI experience")
    )

    assert "Senior Python Engineer" in document.text
    assert document.extension == ".pdf"
    assert document.mime_type == "application/pdf"
    assert document.byte_size > 0


def test_extracts_text_from_docx_including_tables():
    data = build_docx(
        ["Jane Doe", "Python developer with five years of experience."],
        table_rows=[["Skill", "Level"], ["Python", "Advanced"]],
    )

    document = load("resume.docx", data)

    assert "Jane Doe" in document.text
    assert "Python developer" in document.text
    assert "Advanced" in document.text


def test_extracts_text_from_plain_text():
    document = load("notes.txt", b"Recruitment knowledge base entry.")

    assert document.text == "Recruitment knowledge base entry."
    assert document.mime_type == "text/plain"


def test_extracts_text_from_markdown():
    document = load("guide.md", b"# Hiring guide\n\nInterview process steps.")

    assert "Hiring guide" in document.text


def test_normalizes_whitespace():
    assert normalize_text("  Hello \r\n\r\n\r\n  World  ") == "Hello\n\nWorld"


def test_content_hash_is_stable_for_equivalent_whitespace():
    first = load("a.txt", b"Python   developer")
    second = load("b.txt", b"Python developer")

    assert first.content_hash == second.content_hash


def test_rejects_unsupported_extension():
    with pytest.raises(UnsupportedFileTypeError):
        load("payload.exe", b"MZ")


def test_rejects_pdf_without_magic_bytes():
    with pytest.raises(InvalidDocumentError):
        load("fake.pdf", b"this is not a pdf")


def test_rejects_docx_that_is_not_a_zip():
    with pytest.raises(InvalidDocumentError):
        load("fake.docx", b"not a zip archive")


def test_rejects_docx_zip_without_document_entry():
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "hello")

    with pytest.raises(InvalidDocumentError):
        load("fake.docx", buffer.getvalue())


def test_rejects_empty_file():
    with pytest.raises(EmptyDocumentError):
        load("empty.txt", b"")


def test_rejects_oversized_file():
    with pytest.raises(FileTooLargeError):
        load_document("big.txt", b"a" * 2048, 1024, MAX_CHARS)


def test_rejects_document_without_readable_text():
    with pytest.raises(EmptyDocumentError):
        load("blank.pdf", build_pdf(""))


def test_rejects_filename_with_path_separators():
    with pytest.raises(DocumentError):
        validate_filename("../../etc/passwd")
    with pytest.raises(DocumentError):
        validate_filename("folder\\resume.pdf")


def test_rejects_blank_and_overlong_filenames():
    with pytest.raises(DocumentError):
        validate_filename("   ")
    with pytest.raises(DocumentError):
        validate_filename("a" * 300 + ".pdf")


def test_rejects_content_type_mismatch():
    with pytest.raises(UnsupportedFileTypeError):
        load("resume.pdf", build_pdf("text"), content_type="image/png")


def test_accepts_octet_stream_content_type():
    document = load(
        "resume.pdf",
        build_pdf("Python developer"),
        content_type="application/octet-stream",
    )

    assert "Python developer" in document.text


def test_accepts_plain_text_content_type_for_markdown():
    document = load("guide.md", b"# Guide", content_type="text/plain")

    assert "Guide" in document.text


def test_rejects_binary_text_file():
    with pytest.raises(InvalidDocumentError):
        load("notes.txt", b"text\x00binary")


def test_rejects_non_utf8_text_file():
    with pytest.raises(InvalidDocumentError):
        load("notes.txt", "café".encode("latin-1"))


def test_rejects_extracted_text_over_limit():
    with pytest.raises(DocumentError):
        load_document("long.txt", b"a" * 500, MAX_BYTES, 100)
