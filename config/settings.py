from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _path_setting(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default)).expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value


def _boolean_setting(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be set to true or false.")


def _session_secret() -> str:
    value = os.getenv("SESSION_SECRET_KEY", "").strip()
    if value:
        return value

    value = secrets.token_urlsafe(48)
    env_file = PROJECT_ROOT / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8-sig").splitlines() if env_file.exists() else []
        key_line = f"SESSION_SECRET_KEY={value}"
        for index, line in enumerate(lines):
            if line.startswith("SESSION_SECRET_KEY="):
                lines[index] = key_line
                break
        else:
            lines.append(key_line)
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            "Set SESSION_SECRET_KEY to a randomly generated value of at least 32 characters in .env."
        ) from exc
    os.environ["SESSION_SECRET_KEY"] = value
    return value


@dataclass(frozen=True)
class Settings:
    google_api_key: str
    session_secret_key: str
    gemini_model: str
    chroma_persist_directory: Path
    chroma_collection_name: str
    database_path: Path
    documents_directory: Path
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    retrieval_top_k: int
    max_upload_size_mb: int
    app_env: str
    auth_enabled: bool


def get_settings() -> Settings:
    chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))
    top_k = int(os.getenv("RETRIEVAL_TOP_K", "4"))
    max_upload_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    auth_enabled = _boolean_setting("AUTH_ENABLED", True)
    if chunk_size < 1:
        raise ValueError("CHUNK_SIZE must be a positive integer.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP must be >= 0 and smaller than CHUNK_SIZE.")
    if top_k < 1:
        raise ValueError("RETRIEVAL_TOP_K must be a positive integer.")
    if max_upload_size_mb < 1:
        raise ValueError("MAX_UPLOAD_SIZE_MB must be a positive integer.")
    if not auth_enabled and app_env != "development":
        raise ValueError("AUTH_ENABLED=false is only allowed when APP_ENV=development.")

    return Settings(
        google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
        session_secret_key=_session_secret(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip(),
        chroma_persist_directory=_path_setting(
            "CHROMA_PERSIST_DIRECTORY", "./vectorstore/chroma_db"
        ),
        chroma_collection_name=os.getenv("CHROMA_COLLECTION_NAME", "hr_policies"),
        database_path=_path_setting("DATABASE_PATH", "./data/app.db"),
        documents_directory=_path_setting(
            "DOCUMENTS_DIRECTORY", "./data/documents"
        ),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        ),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        retrieval_top_k=top_k,
        max_upload_size_mb=max_upload_size_mb,
        app_env=app_env,
        auth_enabled=auth_enabled,
    )
