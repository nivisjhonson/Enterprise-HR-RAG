from __future__ import annotations

from math import isfinite
from typing import Iterable


def recall_at_k(retrieved_ids: Iterable[str], expected_ids: set[str], k: int) -> float:
    if not expected_ids:
        return 1.0
    found = set(list(retrieved_ids)[:k]) & expected_ids
    return len(found) / len(expected_ids)


def reciprocal_rank(retrieved_ids: Iterable[str], expected_ids: set[str]) -> float:
    for rank, document_id in enumerate(retrieved_ids, start=1):
        if document_id in expected_ids:
            return 1.0 / rank
    return 0.0


def precision_at_k(
    retrieved_ids: Iterable[str], relevant_ids: set[str], k: int
) -> float:
    if k < 1:
        raise ValueError("k must be positive.")
    top_k = list(retrieved_ids)[:k]
    return len(set(top_k) & relevant_ids) / k


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    result = sum(values) / len(values)
    return result if isfinite(result) else 0.0
