from __future__ import annotations

from dataclasses import replace

from langchain_core.documents import Document

from config.settings import get_settings
from src import database, rag_chain
from src.authentication import create_user


def test_empty_policy_library_provides_labeled_general_hr_guidance(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "empty-rag.sqlite3"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    settings = get_settings()
    database.initialize_database(settings)
    prompts = []

    class Store:
        def similarity_search(self, *args, **kwargs):
            raise AssertionError("Search must not run when no policies are indexed.")

    class FakeModel:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-key"

        def invoke(self, prompt):
            prompts.append(prompt)
            return type(
                "Response",
                (),
                {
                    "content": "Prepare the relevant dates and speak with your manager."
                },
            )()

    monkeypatch.setattr(rag_chain, "ChatGoogleGenerativeAI", FakeModel)
    result = rag_chain.answer_question(
        replace(settings, google_api_key="test-key"),
        Store(),
        "How do I request annual leave?",
        {"username": "local-dev", "role": "admin"},
    )

    assert result == {
        "answer": (
            "General HR guidance (not your organization's policy):\n\n"
            "Prepare the relevant dates and speak with your manager."
        ),
        "sources": [],
    }
    assert len(prompts) == 1
    assert "How do I request annual leave?" in prompts[0]
    assert "Do not invent legal requirements" in prompts[0]


def test_empty_policy_library_requires_api_key_for_general_guidance(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "empty-rag.sqlite3"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    settings = replace(get_settings(), google_api_key="")
    database.initialize_database(settings)

    try:
        rag_chain.answer_question(
            settings,
            object(),
            "How do I request annual leave?",
            {"username": "local-dev", "role": "admin"},
        )
    except RuntimeError as exc:
        assert "GOOGLE_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected a clear configuration error without an API key.")


class FakeStore:
    def __init__(self, documents):
        self.documents = documents
        self.last_filter = None

    def similarity_search(self, query, k, filter):
        self.last_filter = filter
        return self.documents[:k]


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "rag.sqlite3"))
    settings = get_settings()
    database.initialize_database(settings)
    admin = {"username": "admin01", "role": "admin"}
    employee = {"username": "employee01", "role": "employee"}
    create_user(settings, "admin01", "a sufficiently long password", "admin")
    create_user(
        settings,
        "employee01",
        "another sufficiently long password",
        "employee",
        actor=admin,
    )
    database.add_document(
        settings,
        {
            "id": "policy-1",
            "filename": "leave.txt",
            "category": "Leave",
            "access_level": "employee",
            "content_hash": "hash-1",
            "version": 1,
            "status": "indexed",
            "chunk_count": 1,
            "uploaded_by": "admin01",
            "error_message": None,
        },
    )
    evidence = Document(
        page_content="Submit the leave request to your manager.",
        metadata={
            "document_id": "policy-1",
            "filename": "leave.txt",
            "category": "Leave",
            "access_level": "employee",
            "content_hash": "hash-1",
            "version": 1,
            "page_number": 3,
        },
    )
    return settings, employee, FakeStore([evidence])


def test_answer_uses_retrieved_evidence_and_real_citations(
    tmp_path, monkeypatch
):
    settings, employee, store = _setup(tmp_path, monkeypatch)
    model_response = type("Response", (), {"content": "Submit the request to your manager [S1]."})

    class FakeModel:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-key"

        def invoke(self, prompt):
            assert "Submit the leave request to your manager." in prompt
            return model_response()

    monkeypatch.setattr(rag_chain, "ChatGoogleGenerativeAI", FakeModel)
    result = rag_chain.answer_question(
        replace(settings, google_api_key="test-key"),
        store,
        "How do I request leave?",
        employee,
    )
    assert result["answer"] == "Submit the request to your manager [S1]."
    assert result["sources"][0]["filename"] == "leave.txt"
    assert result["sources"][0]["page_number"] == 3
    assert store.last_filter["$and"][0] == {
        "document_id": {"$eq": "policy-1"}
    }


def test_invalid_model_citations_fail_closed_to_abstention(
    tmp_path, monkeypatch
):
    settings, employee, store = _setup(tmp_path, monkeypatch)

    class FakeModel:
        def __init__(self, **kwargs):
            pass

        def invoke(self, prompt):
            return type("Response", (), {"content": "The policy says yes [S9]."})()

    monkeypatch.setattr(rag_chain, "ChatGoogleGenerativeAI", FakeModel)
    result = rag_chain.answer_question(
        replace(settings, google_api_key="test-key"),
        store,
        "What does this policy say?",
        employee,
    )
    assert result == {"answer": rag_chain.INSUFFICIENT_EVIDENCE, "sources": []}


def test_missing_api_key_is_clear_when_authorized_evidence_exists(
    tmp_path, monkeypatch
):
    settings, employee, store = _setup(tmp_path, monkeypatch)
    settings = replace(settings, google_api_key="")
    try:
        rag_chain.answer_question(
            settings,
            store,
            "How do I request leave?",
            employee,
        )
    except RuntimeError as exc:
        assert "GOOGLE_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected a configuration error without an API key.")
