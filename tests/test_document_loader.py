from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document as WordDocument

from src.document_loader import DocumentLoadError, load_document, validate_upload


def test_txt_loader_and_validation():
    filename = validate_upload("folder\\policy.txt", b"Leave policy", 1)
    assert filename == "policy.txt"
    assert load_document(filename, b"Leave policy")[0].text == "Leave policy"


def test_rejects_unsupported_empty_and_oversized_uploads():
    with pytest.raises(DocumentLoadError, match="PDF, DOCX, or TXT"):
        validate_upload("policy.csv", b"text", 1)
    with pytest.raises(DocumentLoadError, match="empty"):
        validate_upload("policy.txt", b"", 1)
    with pytest.raises(DocumentLoadError, match="exceeds"):
        validate_upload("policy.txt", b"x" * (1024 * 1024 + 1), 1)


def test_docx_loader_preserves_readable_text():
    document = WordDocument()
    document.add_paragraph("Fictional onboarding policy")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Required item"
    table.cell(0, 1).text = "Government identification"
    buffer = BytesIO()
    document.save(buffer)
    pages = load_document("onboarding.docx", buffer.getvalue())
    assert "Fictional onboarding policy" in pages[0].text
    assert "Required item | Government identification" in pages[0].text
    assert pages[0].page_number is None
