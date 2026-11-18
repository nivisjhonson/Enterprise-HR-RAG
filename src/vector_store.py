from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from config.settings import Settings
from src.embeddings import get_embeddings


@lru_cache(maxsize=4)
def _cached_vector_store(
    persist_directory: str, collection_name: str, embedding_model: str
) -> Chroma:
    Path(persist_directory).mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_function=get_embeddings(embedding_model),
    )


def get_vector_store(settings: Settings) -> Chroma:
    return _cached_vector_store(
        str(settings.chroma_persist_directory),
        settings.chroma_collection_name,
        settings.embedding_model,
    )


def vector_store_count(settings: Settings) -> int:
    return int(get_vector_store(settings)._collection.count())


def add_documents(
    store: Any, documents: list[Document], ids: list[str]
) -> None:
    if len(documents) != len(ids):
        raise ValueError("Each document must have exactly one vector ID.")
    if documents:
        store.add_documents(documents=documents, ids=ids)


def delete_document_vectors(
    store: Any, document_id: str, version: int | None = None
) -> None:
    where: dict[str, Any] = {"document_id": document_id}
    if version is not None:
        where = {
            "$and": [
                {"document_id": {"$eq": document_id}},
                {"version": {"$eq": version}},
            ]
        }
    store.delete(where=where)
