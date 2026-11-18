from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from langchain_google_genai.chat_models import GoogleAPIError

from config.settings import get_settings
from src import api, database
from src.authentication import create_user


def _client(tmp_path, monkeypatch) -> tuple[TestClient, dict[str, str]]:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("AUTH_ENABLED", "true")
    settings = get_settings()
    database.initialize_database(settings)
    admin = {"username": "admin01", "role": "admin"}
    employee = {"username": "employee01", "role": "employee"}
    create_user(settings, "admin01", "a sufficiently long admin password", "admin")
    create_user(
        settings,
        "employee01",
        "a sufficiently long employee password",
        "employee",
        actor=admin,
    )
    for document_id, access_level in (
        ("employee-policy", "employee"),
        ("admin-policy", "admin"),
    ):
        database.add_document(
            settings,
            {
                "id": document_id,
                "filename": f"{document_id}.txt",
                "category": "HR",
                "access_level": access_level,
                "content_hash": document_id,
                "version": 1,
                "status": "indexed",
                "chunk_count": 1,
                "uploaded_by": "admin01",
                "error_message": None,
            },
        )
    monkeypatch.setattr(api, "settings", settings)
    return TestClient(api.app), employee


def test_local_no_login_mode_grants_local_admin_access_without_bootstrap(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "local.sqlite3"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    settings = get_settings()
    monkeypatch.setattr(api, "settings", settings)
    client = TestClient(api.app, base_url="http://127.0.0.1", client=("127.0.0.1", 12345))

    with client:
        assert client.get("/api/auth/status").json() == {
            "authentication_enabled": False,
            "administrator_ready": False,
        }
        assert client.get("/api/auth/me").json() == {
            "username": "local-dev",
            "role": "admin",
        }
        assert client.get("/api/admin/dashboard").status_code == 200
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "not-used"},
        ).status_code == 403


def test_chat_returns_general_guidance_without_initializing_vector_store(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "general-chat.sqlite3"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    settings = replace(get_settings(), google_api_key="test-key")
    monkeypatch.setattr(api, "settings", settings)
    prompts = []

    class FakeModel:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-key"

        def invoke(self, prompt):
            prompts.append(prompt)
            return type(
                "Response",
                (),
                {
                    "content": (
                        "General HR guidance (not your organization's policy):\n\n"
                        "Discuss your preferred dates with your manager."
                    )
                },
            )()

    monkeypatch.setattr(api, "get_vector_store", lambda _: pytest.fail(
        "The vector store should not initialize when no policies are indexed."
    ))
    monkeypatch.setattr("src.rag_chain.ChatGoogleGenerativeAI", FakeModel)

    client = TestClient(
        api.app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 12345),
    )
    with client:
        response = client.post(
            "/api/chat",
            json={"question": "How do I request annual leave?"},
        )

    assert response.status_code == 200
    assert response.json()["answer"].startswith(
        "General HR guidance (not your organization's policy):"
    )
    assert response.json()["sources"] == []
    assert response.json()["answer_id"]
    assert "How do I request annual leave?" in prompts[0]


def test_chat_explains_temporary_gemini_overload(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "overloaded-chat.sqlite3"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    settings = get_settings()
    monkeypatch.setattr(api, "settings", settings)

    def overloaded_model(*args, **kwargs):
        raise GoogleAPIError(
            503,
            {
                "error": {
                    "code": 503,
                    "status": "UNAVAILABLE",
                    "message": "This model is currently experiencing high demand.",
                }
            },
        )

    monkeypatch.setattr(api, "answer_question", overloaded_model)
    client = TestClient(
        api.app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 12345),
    )

    with client:
        response = client.post(
            "/api/chat",
            json={"question": "What are some general HR tips?"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Gemini is temporarily busy. Please wait a minute and try again."
    )


def test_local_no_login_mode_rejects_non_loopback_clients(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "remote.sqlite3"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    settings = get_settings()
    monkeypatch.setattr(api, "settings", settings)
    client = TestClient(api.app, base_url="http://127.0.0.1", client=("192.0.2.1", 12345))

    with client:
        response = client.get("/api/auth/me")

    assert response.status_code == 403
    assert response.json()["detail"] == "No-login mode is available only from this computer."


def test_local_no_login_mode_is_rejected_outside_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "false")

    with pytest.raises(ValueError, match="only allowed when APP_ENV=development"):
        get_settings()


def test_employee_session_is_http_only_and_cannot_access_admin_api(
    tmp_path, monkeypatch
):
    client, _ = _client(tmp_path, monkeypatch)
    with client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "employee01",
                "password": "a sufficiently long employee password",
            },
        )
        assert login.status_code == 200
        assert login.json() == {"username": "employee01", "role": "employee"}
        assert client.cookies.get("hr_policy_session")
        assert "httponly" in login.headers["set-cookie"].lower()

        assert client.get("/api/auth/me").json() == login.json()
        documents = client.get("/api/documents")
        assert documents.status_code == 200
        assert [document["id"] for document in documents.json()] == [
            "employee-policy"
        ]
        assert client.get("/api/admin/dashboard").status_code == 403

        settings_response = client.get("/api/settings")
        assert settings_response.status_code == 200
        assert settings_response.json()["max_upload_size_mb"] == 100
        assert set(settings_response.json()).isdisjoint(
            {"google_api_key", "session_secret_key"}
        )


def test_admin_upload_accepts_file_larger_than_previous_limit(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    indexed_size = 0

    def fake_ingest(settings, store, filename, content, category, access_level, user):
        nonlocal indexed_size
        indexed_size = len(content)
        return {
            "filename": filename,
            "chunk_count": 1,
            "unchanged": False,
        }

    monkeypatch.setattr(api, "get_vector_store", lambda _: object())
    monkeypatch.setattr(api, "ingest_document", fake_ingest)
    content = b"x" * (20 * 1024 * 1024 + 1)

    with client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "admin01",
                "password": "a sufficiently long admin password",
            },
        )
        assert login.status_code == 200
        response = client.post(
            "/api/admin/documents",
            data={"category": "General", "access_level": "employee"},
            files={"files": ("large-policy.txt", content, "text/plain")},
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "indexed"
    assert indexed_size == len(content)


def test_disabled_user_session_is_rejected_and_logout_clears_session(
    tmp_path, monkeypatch
):
    client, _ = _client(tmp_path, monkeypatch)
    with client:
        client.post(
            "/api/auth/login",
            json={
                "username": "employee01",
                "password": "a sufficiently long employee password",
            },
        )
        database.set_user_active(api.settings, "employee01", False)
        assert client.get("/api/auth/me").status_code == 401

        login = client.post(
            "/api/auth/login",
            json={
                "username": "admin01",
                "password": "a sufficiently long admin password",
            },
        )
        assert login.status_code == 200
        assert client.get("/api/admin/dashboard").status_code == 200
        assert client.post("/api/auth/logout").json() == {"ok": True}
        assert client.get("/api/auth/me").status_code == 401
