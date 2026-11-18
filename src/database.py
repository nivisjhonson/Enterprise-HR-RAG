from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from config.settings import Settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(settings: Settings) -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database(settings: Settings) -> None:
    with connect(settings) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'employee')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                category TEXT NOT NULL,
                access_level TEXT NOT NULL CHECK (access_level IN ('employee', 'admin')),
                content_hash TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
            CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
            CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
            CREATE TABLE IF NOT EXISTS indexing_jobs (
                id TEXT PRIMARY KEY,
                document_id TEXT,
                filename TEXT NOT NULL,
                actor TEXT NOT NULL,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS vector_cleanup (
                document_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                error_message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (document_id, version)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                document_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS answer_feedback (
                answer_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
                created_at TEXT NOT NULL
            );
            """
        )


def user_count(settings: Settings) -> int:
    with connect(settings) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def get_user(settings: Settings, username: str) -> dict[str, Any] | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT username, password_hash, role, is_active FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    return dict(row) if row else None


def insert_user(
    settings: Settings, username: str, password_hash: str, role: str
) -> None:
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role, created_at) "
            "VALUES (?, ?, ?, ?)",
            (username.strip(), password_hash, role, _now()),
        )


def set_user_active(settings: Settings, username: str, is_active: bool) -> None:
    with connect(settings) as connection:
        result = connection.execute(
            "UPDATE users SET is_active = ? WHERE username = ?",
            (int(is_active), username),
        )
        if result.rowcount != 1:
            raise LookupError("User was not found.")


def list_users(settings: Settings) -> list[dict[str, Any]]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT username, role, is_active, created_at FROM users ORDER BY username"
        ).fetchall()
    return [dict(row) for row in rows]


def add_document(settings: Settings, document: dict[str, Any]) -> None:
    now = _now()
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                id, filename, category, access_level, content_hash, version,
                status, chunk_count, uploaded_by, uploaded_at, updated_at, error_message
            ) VALUES (
                :id, :filename, :category, :access_level, :content_hash, :version,
                :status, :chunk_count, :uploaded_by, :uploaded_at, :updated_at,
                :error_message
            )
            ON CONFLICT(id) DO UPDATE SET
                filename = excluded.filename,
                category = excluded.category,
                access_level = excluded.access_level,
                content_hash = excluded.content_hash,
                version = excluded.version,
                status = excluded.status,
                chunk_count = excluded.chunk_count,
                uploaded_by = excluded.uploaded_by,
                uploaded_at = excluded.uploaded_at,
                updated_at = excluded.updated_at,
                error_message = excluded.error_message
            """,
            {
                **document,
                "uploaded_at": document.get("uploaded_at", now),
                "updated_at": now,
            },
        )


def record_failed_document(
    settings: Settings,
    document: dict[str, Any],
    error_message: str,
) -> None:
    now = _now()
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                id, filename, category, access_level, content_hash, version,
                status, chunk_count, uploaded_by, uploaded_at, updated_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, 'failed', 0, ?, ?, ?, ?)
            """,
            (
                document["id"],
                document["filename"],
                document["category"],
                document["access_level"],
                document.get("content_hash", ""),
                document["version"],
                document["uploaded_by"],
                now,
                now,
                error_message[:500],
            ),
        )


def get_document(settings: Settings, document_id: str) -> dict[str, Any] | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
    return dict(row) if row else None


def get_active_document_by_filename(
    settings: Settings, filename: str
) -> dict[str, Any] | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT * FROM documents
            WHERE filename = ? AND status = 'indexed'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (filename,),
        ).fetchone()
    return dict(row) if row else None


def get_duplicate_document(
    settings: Settings, content_hash: str, exclude_id: str | None = None
) -> dict[str, Any] | None:
    query = "SELECT * FROM documents WHERE content_hash = ? AND status = 'indexed'"
    values: list[Any] = [content_hash]
    if exclude_id:
        query += " AND id != ?"
        values.append(exclude_id)
    query += " ORDER BY updated_at DESC LIMIT 1"
    with connect(settings) as connection:
        row = connection.execute(query, values).fetchone()
    return dict(row) if row else None


def list_documents(
    settings: Settings, include_deleted: bool = True
) -> list[dict[str, Any]]:
    query = "SELECT * FROM documents"
    if not include_deleted:
        query += " WHERE status != 'deleted'"
    query += " ORDER BY updated_at DESC"
    with connect(settings) as connection:
        rows = connection.execute(query).fetchall()
    return [dict(row) for row in rows]


def accessible_documents(
    settings: Settings, user: dict[str, Any]
) -> list[dict[str, Any]]:
    query = (
        "SELECT id, version, content_hash, filename, category, access_level "
        "FROM documents WHERE status = 'indexed'"
    )
    values: tuple[Any, ...] = ()
    if user["role"] != "admin":
        query += " AND access_level = 'employee'"
    query += " ORDER BY filename"
    with connect(settings) as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def set_document_status(
    settings: Settings, document_id: str, status: str, error_message: str | None = None
) -> None:
    with connect(settings) as connection:
        result = connection.execute(
            "UPDATE documents SET status = ?, error_message = ?, updated_at = ? WHERE id = ?",
            (status, error_message, _now(), document_id),
        )
        if result.rowcount != 1:
            raise LookupError("Document was not found.")


def document_statistics(settings: Settings) -> dict[str, int]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS documents, COALESCE(SUM(chunk_count), 0) AS chunks "
            "FROM documents GROUP BY status"
        ).fetchall()
        failed_jobs = connection.execute(
            "SELECT COUNT(*) FROM indexing_jobs WHERE status = 'failed'"
        ).fetchone()[0]
        successful_jobs = connection.execute(
            "SELECT COUNT(*) FROM indexing_jobs WHERE status = 'succeeded'"
        ).fetchone()[0]
    totals = {"indexed_documents": 0, "chunks": 0, "failed_jobs": 0}
    for row in rows:
        if row["status"] == "indexed":
            totals["indexed_documents"] = int(row["documents"])
            totals["chunks"] = int(row["chunks"])
    totals["failed_jobs"] = int(failed_jobs)
    totals["successful_jobs"] = int(successful_jobs)
    return totals


def start_indexing_job(
    settings: Settings, filename: str, actor: str
) -> str:
    job_id = str(uuid.uuid4())
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO indexing_jobs (id, filename, actor, status, created_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (job_id, filename, actor, _now()),
        )
    return job_id


def finish_indexing_job(
    settings: Settings,
    job_id: str,
    status: str,
    document_id: str | None = None,
    chunk_count: int = 0,
    error_message: str | None = None,
) -> None:
    if status not in {"succeeded", "failed"}:
        raise ValueError("An indexing job must finish as succeeded or failed.")
    with connect(settings) as connection:
        result = connection.execute(
            """
            UPDATE indexing_jobs
            SET status = ?, document_id = ?, chunk_count = ?,
                error_message = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                status,
                document_id,
                chunk_count,
                error_message[:500] if error_message else None,
                _now(),
                job_id,
            ),
        )
        if result.rowcount != 1:
            raise LookupError("Indexing job was not found.")


def list_recent_indexing_jobs(
    settings: Settings, limit: int = 10
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("The job limit must be positive.")
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT * FROM indexing_jobs
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def record_vector_cleanup_pending(
    settings: Settings, document_id: str, version: int, error_message: str
) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO vector_cleanup (document_id, version, error_message, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(document_id, version) DO UPDATE SET
                error_message = excluded.error_message,
                created_at = excluded.created_at
            """,
            (document_id, version, error_message[:500], _now()),
        )


def list_pending_vector_cleanup(settings: Settings) -> list[dict[str, Any]]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT cleanup.document_id, cleanup.version, cleanup.error_message,
                   cleanup.created_at, documents.filename, documents.version AS current_version
            FROM vector_cleanup AS cleanup
            LEFT JOIN documents ON documents.id = cleanup.document_id
            ORDER BY cleanup.created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def clear_vector_cleanup_pending(
    settings: Settings, document_id: str, version: int | None = None
) -> None:
    with connect(settings) as connection:
        if version is None:
            connection.execute(
                "DELETE FROM vector_cleanup WHERE document_id = ?", (document_id,)
            )
        else:
            connection.execute(
                "DELETE FROM vector_cleanup WHERE document_id = ? AND version = ?",
                (document_id, version),
            )


def save_answer_feedback(
    settings: Settings, answer_id: str, username: str, rating: int
) -> None:
    if rating not in {-1, 1}:
        raise ValueError("Feedback rating must be either -1 or 1.")
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO answer_feedback (answer_id, username, rating, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(answer_id) DO UPDATE SET
                rating = excluded.rating,
                created_at = excluded.created_at
            WHERE answer_feedback.username = excluded.username
            """,
            (answer_id, username, rating, _now()),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise PermissionError("This answer feedback belongs to another account.")


def record_audit_event(
    settings: Settings, actor: str, action: str, document_id: str | None = None
) -> None:
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO audit_events (actor, action, document_id, created_at) VALUES (?, ?, ?, ?)",
            (actor, action, document_id, _now()),
        )
