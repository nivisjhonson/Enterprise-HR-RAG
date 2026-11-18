from __future__ import annotations

from config.settings import get_settings
from src import database
from src.ingestion import ingest_document
from src.vector_store import get_vector_store


def main() -> None:
    settings = get_settings()
    database.initialize_database(settings)
    folder = settings.documents_directory
    folder.mkdir(parents=True, exist_ok=True)
    store = get_vector_store(settings)
    operators = [
        user
        for user in database.list_users(settings)
        if user["role"] == "admin" and user["is_active"]
    ]
    if not operators:
        raise RuntimeError(
            "Create an active administrator account before running CLI ingestion."
        )
    actor = {"username": operators[0]["username"], "role": "admin"}
    successes = 0
    failures = 0
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > settings.max_upload_size_mb * 1024 * 1024:
                raise ValueError(
                    f"File exceeds the {settings.max_upload_size_mb} MB upload limit."
                )
            result = ingest_document(
                settings,
                store,
                path.name,
                path.read_bytes(),
                category="General",
                access_level="employee",
                actor=actor,
            )
            print(f"Indexed {result['filename']}: {result['chunk_count']} chunks.")
            successes += 1
        except Exception as exc:
            print(f"Failed {path.name}: {exc}")
            failures += 1
    print(f"Complete: {successes} successful, {failures} failed.")


if __name__ == "__main__":
    main()
