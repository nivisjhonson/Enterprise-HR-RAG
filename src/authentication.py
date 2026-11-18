from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Any

from config.settings import Settings
from src import database
from src.authorization import require_admin

_ITERATIONS = 310_000
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{2,63}$")


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Passwords must contain at least 12 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _ITERATIONS
    )
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def authenticate(
    settings: Settings, username: str, password: str
) -> dict[str, str] | None:
    user = database.get_user(settings, username)
    if not user or not user["is_active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {"username": user["username"], "role": user["role"]}


def create_user(
    settings: Settings,
    username: str,
    password: str,
    role: str,
    actor: dict[str, Any] | None = None,
) -> None:
    if actor is None:
        if database.user_count(settings) != 0:
            raise PermissionError("Bootstrap user creation is available only on an empty user store.")
        if role != "admin":
            raise PermissionError("The initial account must be an administrator.")
    else:
        require_admin(settings, actor)
    normalized_username = username.strip()
    if not _USERNAME_PATTERN.fullmatch(normalized_username):
        raise ValueError("Username must be 3-64 characters and use letters, numbers, '.', '_', '@', or '-'.")
    if role not in {"admin", "employee"}:
        raise ValueError("Role must be 'admin' or 'employee'.")
    database.insert_user(settings, normalized_username, hash_password(password), role)


def bootstrap_admin_from_environment(settings: Settings) -> bool:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username and not password:
        return False
    if not username or not password:
        raise ValueError("Set both BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD.")
    if database.user_count(settings) > 0:
        return False
    create_user(settings, username, password, "admin")
    return True


def manage_user_active(
    settings: Settings,
    username: str,
    is_active: bool,
    actor: dict[str, Any],
) -> None:
    require_admin(settings, actor)
    target = database.get_user(settings, username)
    if not target:
        raise LookupError("User was not found.")
    if not is_active and target["username"].casefold() == str(
        actor.get("username", "")
    ).casefold():
        raise ValueError("Administrators cannot disable their own account.")
    if not is_active and target["role"] == "admin":
        active_admins = [
            user
            for user in database.list_users(settings)
            if user["role"] == "admin" and user["is_active"]
        ]
        if len(active_admins) <= 1:
            raise ValueError("The last active administrator cannot be disabled.")
    database.set_user_active(settings, username, is_active)
