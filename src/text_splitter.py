from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.document_loader import PageText


def split_pages(
    pages: list[PageText],
    metadata: dict[str, Any],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )
    chunks: list[Document] = []
    for page in pages:
        if not page.text.strip():
            continue
        page_chunks = splitter.create_documents(
            [page.text],
            metadatas=[
                {
                    **metadata,
                    "page_number": page.page_number or 0,
                }
            ],
        )
        chunks.extend(page_chunks)
    return chunks
