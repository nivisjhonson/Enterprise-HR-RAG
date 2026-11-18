from __future__ import annotations

from config.settings import get_settings
from src.authentication import bootstrap_admin_from_environment
from src.database import initialize_database


def main() -> None:
    settings = get_settings()
    initialize_database(settings)
    created = bootstrap_admin_from_environment(settings)
    print(f"SQLite database ready: {settings.database_path}")
    if created:
        print("Initial administrator created from environment variables.")
    else:
        print("No administrator created. Configure BOOTSTRAP_ADMIN_USERNAME and "
              "BOOTSTRAP_ADMIN_PASSWORD in .env before first use.")


if __name__ == "__main__":
    main()
