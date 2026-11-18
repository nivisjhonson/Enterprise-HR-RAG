from __future__ import annotations

from typing import Any

from config.settings import Settings
from src import database


def require_active_user(
    settings: Settings, user: dict[str, Any]
) -> dict[str, str]:
    username = str(user.get("username", ""))
    if (
        not settings.auth_enabled
        and username == "local-dev"
        and user.get("role") == "admin"
    ):
        return {"username": username, "role": "admin"}
    stored_user = database.get_user(settings, username)
    if not stored_user or not stored_user["is_active"]:
        raise PermissionError("This account is inactive or no longer exists.")
    return {"username": stored_user["username"], "role": stored_user["role"]}


def require_admin(settings: Settings, user: dict[str, Any]) -> None:
    current_user = require_active_user(settings, user)
    if current_user["role"] != "admin":
        raise PermissionError("Administrator access is required.")


def get_accessible_documents(
    settings: Settings, user: dict[str, Any]
) -> list[dict[str, Any]]:
    current_user = require_active_user(settings, user)
    return database.accessible_documents(settings, current_user)


def build_chroma_access_filter(
    documents: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not documents:
        return None
    clauses = [
        {
            "$and": [
                {"document_id": {"$eq": document["id"]}},
                {"version": {"$eq": document["version"]}},
                {"content_hash": {"$eq": document["content_hash"]}},
            ]
        }
        for document in documents
    ]
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}
