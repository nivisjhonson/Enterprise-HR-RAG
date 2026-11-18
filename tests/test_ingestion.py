from __future__ import annotations

from typing import Any

import pytest
from langchain_core.documents import Document

from config.settings import get_settings
from src import database
from src.authentication import create_user
from src.ingestion import (
    DuplicateDocumentError,
    cleanup_obsolete_version,
    delete_document,
    ingest_document,
)
from src.rag_chain import INSUFFICIENT_EVIDENCE, answer_question


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.last_filter: dict[str, Any] | None = None

    def add_documents(self, documents: list[Document], ids: list[str]) -> None:
        self.documents.update(zip(ids, documents))

    def delete(self, where: dict[str, Any]) -> None:
        delete_ids = [
            vector_id
            for vector_id, document in self.documents.items()
            if _matches(document.metadata, where)
        ]
        for vector_id in delete_ids:
            del self.documents[vector_id]

    def similarity_search(
        self, query: str, k: int, filter: dict[str, Any]
    ) -> list[Document]:
        self.last_filter = filter
        allowed = [
            document
            for document in self.documents.values()
            if _matches(document.metadata, filter)
        ]
        return allowed[:k]


def _matches(metadata: dict[str, Any], expression: dict[str, Any]) -> bool:
    if "$and" in expression:
        return all(_matches(metadata, clause) for clause in expression["$and"])
    if "$or" in expression:
        return any(_matches(metadata, clause) for clause in expression["$or"])
    for key, expected in expression.items():
        if isinstance(expected, dict) and "$eq" in expected:
            if metadata.get(key) != expected["$eq"]:
                return False
        elif metadata.get(key) != expected:
            return False
    return True


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "ingestion.sqlite3"))
    monkeypatch.setenv("CHUNK_SIZE", "64")
    monkeypatch.setenv("CHUNK_OVERLAP", "8")
    settings = get_settings()
    database.initialize_database(settings)
    admin = {"username": "admin01", "role": "admin"}
    create_user(settings, "admin01", "a sufficiently long password", "admin")
    create_user(
        settings,
        "employee01",
        "another sufficiently long password",
        "employee",
        actor=admin,
    )
    return settings, FakeVectorStore(), admin


def test_ingestion_replacement_duplicate_and_deletion(application):
    settings, store, admin = application
    first_content = b"Employees request annual leave from their manager."
    first = ingest_document(
        settings, store, "leave.txt", first_content, "Leave", "employee", admin
    )
    assert first["version"] == 1
    assert first["chunk_count"] > 0
    indexed_document = database.get_document(settings, first["document_id"])
    assert indexed_document["status"] == "indexed"
    indexed_chunk = next(iter(store.documents.values()))
    assert indexed_chunk.metadata["chunk_id"]
    assert indexed_chunk.metadata["uploaded_at"] == indexed_document["uploaded_at"]

    unchanged = ingest_document(
        settings, store, "leave.txt", first_content, "Leave", "employee", admin
    )
    assert unchanged["unchanged"] is True

    with pytest.raises(DuplicateDocumentError):
        ingest_document(
            settings, store, "other-name.txt", first_content, "Leave", "employee", admin
        )

    second = ingest_document(
        settings,
        store,
        "leave.txt",
        b"Employees submit a leave request and wait for manager approval.",
        "Leave",
        "employee",
        admin,
    )
    assert second["document_id"] == first["document_id"]
    assert second["version"] == 2
    assert {
        document.metadata["version"] for document in store.documents.values()
    } == {2}

    delete_document(settings, store, second["document_id"], admin)
    assert store.documents == {}
    assert database.get_document(settings, second["document_id"])["status"] == "deleted"


def test_failed_ingestion_is_recorded_and_previous_versions_remain(application):
    settings, store, admin = application
    with pytest.raises(ValueError, match="Could not read PDF"):
        ingest_document(
            settings, store, "broken.pdf", b"not a pdf", "General", "employee", admin
        )
    failed_jobs = [
        job
        for job in database.list_recent_indexing_jobs(settings)
        if job["status"] == "failed"
    ]
    assert len(failed_jobs) == 1
    assert failed_jobs[0]["filename"] == "broken.pdf"
    assert database.document_statistics(settings)["failed_jobs"] == 1


def test_metadata_only_change_reindexes_access_metadata(application):
    settings, store, admin = application
    first = ingest_document(
        settings,
        store,
        "leave.txt",
        b"Employees request annual leave from their manager.",
        "General",
        "employee",
        admin,
    )
    updated = ingest_document(
        settings,
        store,
        "leave.txt",
        b"Employees request annual leave from their manager.",
        "Restricted",
        "admin",
        admin,
    )
    assert not updated["unchanged"]
    assert updated["version"] == first["version"] + 1
    assert {
        document.metadata["access_level"] for document in store.documents.values()
    } == {"admin"}
    assert database.accessible_documents(
        settings, {"username": "employee01", "role": "employee"}
    ) == []


def test_old_version_cleanup_can_be_retried_without_exposing_old_chunks(application):
    settings, store, admin = application
    initial = ingest_document(
        settings,
        store,
        "leave.txt",
        b"Initial leave procedure for employees.",
        "Leave",
        "employee",
        admin,
    )
    original_delete = store.delete

    def fail_old_version_cleanup(where):
        if _matches({"document_id": initial["document_id"], "version": 1}, where):
            raise RuntimeError("simulated vector-store cleanup failure")
        original_delete(where)

    store.delete = fail_old_version_cleanup
    updated = ingest_document(
        settings,
        store,
        "leave.txt",
        b"Updated leave procedure approved by a manager.",
        "Leave",
        "employee",
        admin,
    )
    assert updated["cleanup_warning"]
    assert database.list_pending_vector_cleanup(settings)[0]["version"] == 1

    employee = {"username": "employee01", "role": "employee"}
    from src.retriever import retrieve_documents

    visible = retrieve_documents(settings, store, "leave", employee)
    assert visible
    assert {document.metadata["version"] for document in visible} == {2}

    store.delete = original_delete
    cleanup_obsolete_version(
        settings, store, initial["document_id"], 1, actor=admin
    )
    assert database.list_pending_vector_cleanup(settings) == []
    assert {document.metadata["version"] for document in store.documents.values()} == {2}


def test_interrupted_replacement_marker_does_not_delete_active_vectors(application):
    settings, store, admin = application
    indexed = ingest_document(
        settings,
        store,
        "leave.txt",
        b"Current leave procedure.",
        "Leave",
        "employee",
        admin,
    )
    database.record_vector_cleanup_pending(
        settings, indexed["document_id"], indexed["version"], "Simulated interruption."
    )
    vector_count = len(store.documents)

    cleanup_obsolete_version(
        settings,
        store,
        indexed["document_id"],
        indexed["version"],
        actor=admin,
    )

    assert len(store.documents) == vector_count
    assert database.list_pending_vector_cleanup(settings) == []


def test_employee_cannot_index_or_delete_documents(application):
    settings, store, admin = application
    employee = {"username": "employee01", "role": "employee"}
    with pytest.raises(PermissionError, match="Administrator"):
        ingest_document(
            settings, store, "policy.txt", b"policy", "General", "employee", employee
        )

    indexed = ingest_document(
        settings, store, "policy.txt", b"policy", "General", "employee", admin
    )
    with pytest.raises(PermissionError, match="Administrator"):
        delete_document(settings, store, indexed["document_id"], employee)


def test_empty_authorized_collection_abstains_without_calling_the_llm(application):
    settings, store, admin = application
    ingest_document(
        settings,
        store,
        "admin-policy.txt",
        b"This indexed policy is only visible to administrators.",
        "General",
        "admin",
        admin,
    )
    result = answer_question(
        settings,
        store,
        "What is the annual leave allowance?",
        {"username": "employee01", "role": "employee"},
    )
    assert result == {"answer": INSUFFICIENT_EVIDENCE, "sources": []}
