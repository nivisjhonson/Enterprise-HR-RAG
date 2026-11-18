from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

from config.settings import Settings
from src import authorization
from src.citations import format_source, source_label


def retrieve_documents(
    settings: Settings,
    store: Any,
    question: str,
    user: dict[str, Any],
) -> list[Document]:
    if not question.strip():
        raise ValueError("Enter a question to search the policy library.")
    accessible = authorization.get_accessible_documents(settings, user)
    access_filter = authorization.build_chroma_access_filter(accessible)
    if access_filter is None:
        return []
    return store.similarity_search(
        question.strip(),
        k=settings.retrieval_top_k,
        filter=access_filter,
    )


def retrieve_with_sources(
    settings: Settings,
    store: Any,
    question: str,
    user: dict[str, Any],
) -> tuple[list[Document], list[dict[str, Any]]]:
    documents = retrieve_documents(settings, store, question, user)
    sources = [
        format_source(document, source_label(index))
        for index, document in enumerate(documents)
    ]
    return documents, sources
