from __future__ import annotations

from getpass import getpass

from config.settings import get_settings
from src import database
from src.authentication import create_user


def main() -> None:
    settings = get_settings()
    database.initialize_database(settings)
    if database.user_count(settings) != 0:
        raise SystemExit("An administrator already exists; bootstrap is available only once.")

    username = input("Choose an administrator username: ").strip()
    password = getpass("Choose an administrator password (12+ characters): ")
    confirmation = getpass("Enter the password again: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    try:
        create_user(settings, username, password, "admin")
    except (ValueError, PermissionError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Created administrator account '{username}'. Sign in to the open app.")


if __name__ == "__main__":
    main()
