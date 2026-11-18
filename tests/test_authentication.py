from __future__ import annotations

import pytest

from config.settings import get_settings
from src import database
from src.authentication import (
    authenticate,
    create_user,
    hash_password,
    manage_user_active,
    verify_password,
)
from src.feedback import save_answer_feedback


def test_password_hash_round_trip_and_rejects_short_password():
    encoded = hash_password("a sufficiently long password")
    assert verify_password("a sufficiently long password", encoded)
    assert not verify_password("incorrect password", encoded)
    with pytest.raises(ValueError):
        hash_password("short")


def test_user_store_and_admin_access_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "auth.sqlite3"))
    settings = get_settings()
    database.initialize_database(settings)
    admin = {"username": "admin01", "role": "admin"}
    employee = {"username": "employee01", "role": "employee"}
    create_user(settings, "admin01", "long admin password", "admin")
    create_user(
        settings,
        "employee01",
        "long employee password",
        "employee",
        actor=admin,
    )

    assert authenticate(settings, "employee01", "long employee password") == employee
    assert authenticate(settings, "employee01", "wrong password") is None
    with pytest.raises(PermissionError):
        create_user(
            settings,
            "otheruser",
            "another long password",
            "admin",
            actor=employee,
        )
    with pytest.raises(ValueError, match="own account"):
        manage_user_active(settings, "admin01", False, actor=admin)
    manage_user_active(settings, "employee01", False, actor=admin)
    assert authenticate(settings, "employee01", "long employee password") is None


def test_feedback_is_scoped_to_the_answer_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "feedback.sqlite3"))
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
    save_answer_feedback(settings, "answer-1", 1, employee)
    with pytest.raises(PermissionError, match="another account"):
        save_answer_feedback(settings, "answer-1", -1, admin)
