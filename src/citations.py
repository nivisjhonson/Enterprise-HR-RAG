from __future__ import annotations

import re
from typing import Any

from langchain_core.documents import Document

_CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


def source_label(index: int) -> str:
    return f"S{index + 1}"


def format_source(document: Document, label: str) -> dict[str, Any]:
    metadata = document.metadata
    page_number = metadata.get("page_number")
    return {
        "label": label,
        "filename": metadata.get("filename", "Unknown document"),
        "page_number": int(page_number) if page_number else None,
        "category": metadata.get("category", ""),
        "excerpt": document.page_content,
    }


def retain_valid_citations(
    answer: str, sources: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    valid_labels = {source["label"] for source in sources}
    referenced_labels = set(_CITATION_PATTERN.findall(answer))
    filtered_answer = _CITATION_PATTERN.sub(
        lambda match: match.group(0) if match.group(1) in valid_labels else "",
        answer,
    )
    cited_sources = [
        source for source in sources if source["label"] in referenced_labels
    ]
    return filtered_answer.strip(), cited_sources


def has_invalid_citations(answer: str, sources: list[dict[str, Any]]) -> bool:
    valid_labels = {source["label"] for source in sources}
    return any(
        label not in valid_labels for label in _CITATION_PATTERN.findall(answer)
    )
