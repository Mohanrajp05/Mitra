import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.rag.config import ALLOWED_EXTENSIONS

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
DOCX_ENTRY = "word/document.xml"

MAX_FILENAME_LENGTH = 200
UNSAFE_FILENAME_PATTERN = re.compile(r'[\x00-\x1f<>:"/\\|?*]')

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ),
    ".txt": "text/plain",
    ".md": "text/markdown",
}

ACCEPTED_CONTENT_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
    "",
}

ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {MIME_TYPES[".docx"]},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
}


class DocumentError(ValueError):
    pass


class UnsupportedFileTypeError(DocumentError):
    pass


class FileTooLargeError(DocumentError):
    pass


class EmptyDocumentError(DocumentError):
    pass


class InvalidDocumentError(DocumentError):
    pass


@dataclass(frozen=True)
class LoadedDocument:
    filename: str
    extension: str
    mime_type: str
    byte_size: int
    text: str
    content_hash: str


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_filename(filename: str) -> str:
    if not isinstance(filename, str) or not filename.strip():
        raise DocumentError("A filename is required.")

    name = filename.strip()
    if len(name) > MAX_FILENAME_LENGTH:
        raise DocumentError("The filename is too long.")
    if "/" in name or "\\" in name:
        raise DocumentError("The filename must not contain path separators.")
    if name in {".", ".."}:
        raise DocumentError("The filename is not valid.")
    if UNSAFE_FILENAME_PATTERN.search(name):
        raise DocumentError("The filename contains unsupported characters.")

    return name


def normalize_text(text: str) -> str:
    if not text:
        return ""

    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\x00", " ").replace("\u00a0", " ")
    lines = [line.strip() for line in value.split("\n")]
    value = "\n".join(lines)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)

    return value.strip()


def _validate_content(extension: str, data: bytes) -> None:
    if extension == ".pdf":
        if not data.startswith(PDF_MAGIC):
            raise InvalidDocumentError("The file is not a valid PDF document.")
        return

    if extension == ".docx":
        if not data.startswith(ZIP_MAGIC):
            raise InvalidDocumentError("The file is not a valid DOCX document.")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except (zipfile.BadZipFile, OSError) as exc:
            raise InvalidDocumentError(
                "The file is not a valid DOCX document."
            ) from exc
        if DOCX_ENTRY not in names:
            raise InvalidDocumentError("The file is not a valid DOCX document.")
        return

    if b"\x00" in data:
        raise InvalidDocumentError("The text file contains binary content.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidDocumentError(
            "The text file must be UTF-8 encoded."
        ) from exc


def _extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise InvalidDocumentError(
                "Password-protected PDF files are not supported."
            )
        pages = [page.extract_text() or "" for page in reader.pages]
    except DocumentError:
        raise
    except Exception as exc:
        raise InvalidDocumentError("The PDF file could not be read.") from exc

    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    try:
        document = DocxDocument(io.BytesIO(data))
    except Exception as exc:
        raise InvalidDocumentError("The DOCX file could not be read.") from exc

    parts = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text and paragraph.text.strip()
    ]
    for table in document.tables:
        for row in table.rows:
            cells = [
                cell.text.strip()
                for cell in row.cells
                if cell.text and cell.text.strip()
            ]
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts)


def _extract_plain(data: bytes) -> str:
    return data.decode("utf-8", errors="strict")


def extract_text(extension: str, data: bytes) -> str:
    if extension == ".pdf":
        return _extract_pdf(data)
    if extension == ".docx":
        return _extract_docx(data)
    return _extract_plain(data)


def load_document(
    filename: str,
    data: bytes,
    max_bytes: int,
    max_chars: int,
    content_type: str | None = None,
) -> LoadedDocument:
    name = validate_filename(filename)
    extension = Path(name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(ALLOWED_EXTENSIONS)
        raise UnsupportedFileTypeError(
            f"Unsupported file type. Allowed types: {allowed}."
        )

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared and declared not in ACCEPTED_CONTENT_TYPES:
        if declared not in ALLOWED_CONTENT_TYPES[extension]:
            raise UnsupportedFileTypeError(
                "The declared content type does not match the file extension."
            )

    if not data:
        raise EmptyDocumentError("The uploaded file is empty.")

    if len(data) > max_bytes:
        raise FileTooLargeError(
            f"The uploaded file is larger than {max_bytes} bytes."
        )

    _validate_content(extension, data)

    text = normalize_text(extract_text(extension, data))
    if not text:
        raise EmptyDocumentError("No readable text was found in the document.")

    if len(text) > max_chars:
        raise DocumentError(
            f"The extracted text is longer than {max_chars} characters."
        )

    return LoadedDocument(
        filename=name,
        extension=extension,
        mime_type=MIME_TYPES[extension],
        byte_size=len(data),
        text=text,
        content_hash=hash_text(text),
    )
