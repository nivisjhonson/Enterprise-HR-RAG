from __future__ import annotations

import pytest

from config.settings import get_settings
from src import database
from src.authentication import create_user
from src.authorization import build_chroma_access_filter, get_accessible_documents
from src.retriever import retrieve_documents


def test_accessible_document_scope_and_vector_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "access.sqlite3"))
    settings = get_settings()
    database.initialize_database(settings)
    create_user(settings, "admin01", "a long enough admin password", "admin")
    create_user(
        settings,
        "employee01",
        "a long enough employee password",
        "employee",
        actor={"username": "admin01", "role": "admin"},
    )
    for document_id, level in (("public-doc", "employee"), ("private-doc", "admin")):
        database.add_document(
            settings,
            {
                "id": document_id,
                "filename": f"{document_id}.txt",
                "category": "HR",
                "access_level": level,
                "content_hash": document_id,
                "version": 1,
                "status": "indexed",
                "chunk_count": 1,
                "uploaded_by": "admin",
                "error_message": None,
            },
        )

    employee_docs = get_accessible_documents(
        settings, {"username": "employee01", "role": "employee"}
    )
    assert [doc["id"] for doc in employee_docs] == ["public-doc"]
    assert build_chroma_access_filter(employee_docs) == {
        "$and": [
            {"document_id": {"$eq": "public-doc"}},
            {"version": {"$eq": 1}},
            {"content_hash": {"$eq": "public-doc"}},
        ]
    }

    admin_docs = get_accessible_documents(
        settings, {"username": "admin01", "role": "admin"}
    )
    assert {doc["id"] for doc in admin_docs} == {"public-doc", "private-doc"}
    assert build_chroma_access_filter([]) is None


def test_disabled_users_cannot_retrieve(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "disabled.sqlite3"))
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
    database.set_user_active(settings, "employee01", False)

    class Store:
        def similarity_search(self, *args, **kwargs):
            raise AssertionError("Search must not run for a disabled account.")

    with pytest.raises(PermissionError, match="inactive"):
        retrieve_documents(
            settings,
            Store(),
            "leave",
            {"username": "employee01", "role": "employee"},
        )
