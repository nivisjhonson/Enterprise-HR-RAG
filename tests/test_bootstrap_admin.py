from __future__ import annotations

import pytest

from config.settings import get_settings
from src import database
from src.authentication import authenticate, create_user
from scripts import bootstrap_admin


def test_interactive_bootstrap_creates_admin_without_echoing_password(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "bootstrap.sqlite3"))
    monkeypatch.setattr("builtins.input", lambda _: "admin01")
    prompts = iter(("a sufficiently long password", "a sufficiently long password"))
    monkeypatch.setattr(bootstrap_admin, "getpass", lambda _: next(prompts))

    bootstrap_admin.main()

    settings = get_settings()
    assert authenticate(settings, "admin01", "a sufficiently long password") == {
        "username": "admin01",
        "role": "admin",
    }
    assert "a sufficiently long password" not in capsys.readouterr().out


def test_interactive_bootstrap_rejects_mismatched_passwords(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "bootstrap.sqlite3"))
    monkeypatch.setattr("builtins.input", lambda _: "admin01")
    prompts = iter(("a sufficiently long password", "a different long password"))
    monkeypatch.setattr(bootstrap_admin, "getpass", lambda _: next(prompts))

    with pytest.raises(SystemExit, match="Passwords do not match"):
        bootstrap_admin.main()

    assert database.user_count(get_settings()) == 0


def test_interactive_bootstrap_is_refused_when_an_account_exists(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "bootstrap.sqlite3"))
    settings = get_settings()
    database.initialize_database(settings)
    create_user(settings, "admin01", "a sufficiently long password", "admin")
    monkeypatch.setattr(
        "builtins.input",
        lambda _: pytest.fail("The username prompt must not be shown again."),
    )

    with pytest.raises(SystemExit, match="already exists"):
        bootstrap_admin.main()
