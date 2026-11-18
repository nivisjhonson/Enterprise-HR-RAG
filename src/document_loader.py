from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from docx import Document as WordDocument
from pypdf import PdfReader


@dataclass(frozen=True)
class PageText:
    text: str
    page_number: int | None


class DocumentLoadError(ValueError):
    """Raised when an uploaded document cannot be safely read."""


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def validate_upload(
    filename: str, content: bytes, max_upload_size_mb: int
) -> str:
    safe_name = PurePath(filename.replace("\\", "/")).name.strip()
    suffix = PurePath(safe_name).suffix.lower()
    if not safe_name or safe_name in {".", ".."}:
        raise DocumentLoadError("The uploaded file must have a valid filename.")
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentLoadError("Upload a PDF, DOCX, or TXT file.")
    if not content:
        raise DocumentLoadError("The uploaded file is empty.")
    if len(content) > max_upload_size_mb * 1024 * 1024:
        raise DocumentLoadError(f"File exceeds the {max_upload_size_mb} MB upload limit.")
    return safe_name


def load_document(filename: str, content: bytes) -> list[PageText]:
    suffix = PurePath(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = content.decode("utf-8-sig").strip()
            pages = [PageText(text=text, page_number=None)] if text else []
        elif suffix == ".pdf":
            reader = PdfReader(BytesIO(content))
            pages = [
                PageText(text=(page.extract_text() or "").strip(), page_number=index)
                for index, page in enumerate(reader.pages, start=1)
            ]
        elif suffix == ".docx":
            document = WordDocument(BytesIO(content))
            parts = [
                paragraph.text.strip()
                for paragraph in document.paragraphs
                if paragraph.text.strip()
            ]
            for table in document.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        parts.append(" | ".join(cells))
            for section in document.sections:
                for block in (section.header, section.footer):
                    header_footer = "\n".join(
                        paragraph.text.strip()
                        for paragraph in block.paragraphs
                        if paragraph.text.strip()
                    )
                    if header_footer:
                        parts.append(header_footer)
            text = "\n".join(parts).strip()
            pages = [PageText(text=text, page_number=None)] if text else []
        else:
            raise DocumentLoadError("Upload a PDF, DOCX, or TXT file.")
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(
            f"Could not read {suffix[1:].upper()} file. It may be damaged or password-protected."
        ) from exc
    if not any(page.text for page in pages):
        raise DocumentLoadError("No readable text was found in this document.")
    return pages
