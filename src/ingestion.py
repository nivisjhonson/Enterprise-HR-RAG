from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from config.settings import Settings
from src import database
from src.authorization import require_admin
from src.document_loader import load_document, validate_upload
from src.text_splitter import split_pages
from src.vector_store import add_documents, delete_document_vectors

logger = logging.getLogger(__name__)
_DOCUMENT_OPERATIONS_LOCK = Lock()


class DuplicateDocumentError(ValueError):
    def __init__(self, filename: str):
        super().__init__(f"This content is already indexed as '{filename}'.")
        self.filename = filename


def _deterministic_chunk_id(
    document_id: str, version: int, index: int, content_hash: str
) -> str:
    value = f"{document_id}:{version}:{index}:{content_hash}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ingest_document(
    settings: Settings,
    store: Any,
    filename: str,
    content: bytes,
    category: str,
    access_level: str,
    actor: dict[str, Any],
) -> dict[str, Any]:
    with _DOCUMENT_OPERATIONS_LOCK:
        return _ingest_document(
            settings, store, filename, content, category, access_level, actor
        )


def _ingest_document(
    settings: Settings,
    store: Any,
    filename: str,
    content: bytes,
    category: str,
    access_level: str,
    actor: dict[str, Any],
) -> dict[str, Any]:
    require_admin(settings, actor)
    safe_filename = validate_upload(filename, content, settings.max_upload_size_mb)
    if access_level not in {"employee", "admin"}:
        raise ValueError("Access level must be 'employee' or 'admin'.")
    if not category.strip():
        raise ValueError("A document category is required.")

    content_hash = hashlib.sha256(content).hexdigest()
    existing = database.get_active_document_by_filename(settings, safe_filename)
    duplicate = database.get_duplicate_document(
        settings, content_hash, exclude_id=existing["id"] if existing else None
    )
    if duplicate:
        raise DuplicateDocumentError(duplicate["filename"])
    normalized_category = category.strip()
    if (
        existing
        and existing["content_hash"] == content_hash
        and existing["category"] == normalized_category
        and existing["access_level"] == access_level
    ):
        return {
            "document_id": existing["id"],
            "filename": safe_filename,
            "chunk_count": existing["chunk_count"],
            "version": existing["version"],
            "unchanged": True,
        }

    document_id = existing["id"] if existing else str(uuid.uuid4())
    version = int(existing["version"]) + 1 if existing else 1
    if existing:
        database.record_vector_cleanup_pending(
            settings,
            document_id,
            int(existing["version"]),
            "A replacement is being staged; cleanup will run after activation.",
        )
    job_id = database.start_indexing_job(settings, safe_filename, actor["username"])
    uploaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    document_metadata = {
        "document_id": document_id,
        "filename": safe_filename,
        "category": normalized_category,
        "access_level": access_level,
        "version": version,
        "content_hash": content_hash,
        "uploaded_at": uploaded_at,
        "uploaded_by": actor["username"],
    }
    try:
        pages = load_document(safe_filename, content)
        chunks = split_pages(
            pages,
            document_metadata,
            settings.chunk_size,
            settings.chunk_overlap,
        )
        if not chunks:
            raise ValueError("The document did not produce any searchable text chunks.")
        ids = [
            _deterministic_chunk_id(document_id, version, index, content_hash)
            for index in range(len(chunks))
        ]
        for chunk, chunk_id in zip(chunks, ids):
            chunk.metadata["chunk_id"] = chunk_id
        add_documents(store, chunks, ids)
        database.add_document(
            settings,
            {
                **document_metadata,
                "id": document_id,
                "status": "indexed",
                "chunk_count": len(chunks),
                "error_message": None,
            },
        )
    except Exception as exc:
        try:
            delete_document_vectors(store, document_id, version)
        except Exception:
            logger.exception(
                "Could not roll back staged vectors for document %s version %s",
                document_id,
                version,
            )
        if existing:
            current_document = database.get_document(settings, document_id)
            if current_document and int(current_document["version"]) == int(
                existing["version"]
            ):
                try:
                    database.clear_vector_cleanup_pending(
                        settings, document_id, int(existing["version"])
                    )
                except Exception:
                    logger.exception(
                        "Could not clear obsolete cleanup marker for failed replacement %s",
                        document_id,
                    )
        if not existing:
            try:
                database.record_failed_document(
                    settings,
                    {
                        **document_metadata,
                        "id": document_id,
                    },
                    f"Indexing failed: {type(exc).__name__}",
                )
            except Exception:
                logger.exception(
                    "Could not record failed indexing for %s", safe_filename
                )
        try:
            database.finish_indexing_job(
                settings,
                job_id,
                "failed",
                document_id=document_id,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception("Could not update indexing job %s", job_id)
        raise

    cleanup_warning = None
    try:
        database.finish_indexing_job(
            settings,
            job_id,
            "succeeded",
            document_id=document_id,
            chunk_count=len(chunks),
        )
    except Exception:
        logger.exception("Document indexed, but job status update failed: %s", job_id)
        cleanup_warning = "Document indexed, but its job status could not be updated."

    if existing:
        try:
            delete_document_vectors(store, document_id, int(existing["version"]))
        except Exception as exc:
            logger.exception(
                "New version indexed, but old vectors could not be removed for %s",
                document_id,
            )
            try:
                database.record_vector_cleanup_pending(
                    settings,
                    document_id,
                    int(existing["version"]),
                    f"{type(exc).__name__}: {exc}",
                )
                cleanup_warning = (
                    "The new version is active, but cleanup of the previous version failed. "
                    "Old vectors are excluded from retrieval; use Retry cleanup in Manage documents."
                )
            except Exception:
                logger.exception(
                    "Could not record pending vector cleanup for document %s version %s",
                    document_id,
                    existing["version"],
                )
                cleanup_warning = (
                    "The new version is active, but cleanup of previous vectors failed "
                    "and could not be queued. Only the current version is searchable."
                )
        else:
            try:
                database.clear_vector_cleanup_pending(
                    settings, document_id, int(existing["version"])
                )
            except Exception:
                logger.exception(
                    "Old vectors were removed, but cleanup marker could not be cleared."
                )
                warning = (
                    "The prior vectors were removed, but their cleanup marker remains. "
                    "Retry cleanup in Manage documents."
                )
                cleanup_warning = f"{cleanup_warning} {warning}".strip()
    try:
        database.record_audit_event(
            settings, actor["username"], "document_indexed", document_id
        )
    except Exception:
        logger.exception("Document indexed, but audit event recording failed.")
        warning = "The document is indexed, but its audit event could not be recorded."
        cleanup_warning = f"{cleanup_warning} {warning}".strip()
    return {
        "document_id": document_id,
        "filename": safe_filename,
        "chunk_count": len(chunks),
        "version": version,
        "unchanged": False,
        "cleanup_warning": cleanup_warning,
    }


def delete_document(
    settings: Settings, store: Any, document_id: str, actor: dict[str, Any]
) -> str | None:
    with _DOCUMENT_OPERATIONS_LOCK:
        return _delete_document(settings, store, document_id, actor)


def _delete_document(
    settings: Settings, store: Any, document_id: str, actor: dict[str, Any]
) -> str | None:
    require_admin(settings, actor)
    document = database.get_document(settings, document_id)
    if not document or document["status"] == "deleted":
        raise LookupError("The document is not available for deletion.")
    database.set_document_status(settings, document_id, "deleting")
    try:
        delete_document_vectors(store, document_id)
    except Exception:
        database.set_document_status(
            settings,
            document_id,
            "deleting",
            "Vector cleanup failed. Retry deletion from the admin dashboard.",
        )
        raise
    database.set_document_status(settings, document_id, "deleted")
    database.clear_vector_cleanup_pending(settings, document_id)
    try:
        database.record_audit_event(
            settings, actor["username"], "document_deleted", document_id
        )
    except Exception:
        logger.exception("Document deleted, but audit event recording failed.")
        return "Document was deleted, but its audit event could not be recorded."
    return None


def cleanup_obsolete_version(
    settings: Settings,
    store: Any,
    document_id: str,
    version: int,
    actor: dict[str, Any],
) -> str | None:
    with _DOCUMENT_OPERATIONS_LOCK:
        return _cleanup_obsolete_version(
            settings, store, document_id, version, actor
        )


def _cleanup_obsolete_version(
    settings: Settings,
    store: Any,
    document_id: str,
    version: int,
    actor: dict[str, Any],
) -> str | None:
    require_admin(settings, actor)
    document = database.get_document(settings, document_id)
    if not document or document["status"] != "indexed":
        raise ValueError(
            "Only an obsolete version of an indexed document can be cleaned up."
        )
    current_version = int(document["version"])
    if int(version) > current_version:
        raise ValueError("A document cannot be cleaned up before it becomes obsolete.")
    has_pending_marker = any(
        entry["document_id"] == document_id
        and int(entry["version"]) == int(version)
        for entry in database.list_pending_vector_cleanup(settings)
    )
    if int(version) == current_version and not has_pending_marker:
        raise ValueError("There is no interrupted cleanup to resolve for this version.")
    if int(version) < current_version:
        delete_document_vectors(store, document_id, int(version))
    database.clear_vector_cleanup_pending(settings, document_id, int(version))
    try:
        database.record_audit_event(
            settings,
            actor["username"],
            "obsolete_vectors_removed",
            document_id,
        )
    except Exception:
        logger.exception(
            "Obsolete vectors removed, but audit event recording failed."
        )
        return "Old vectors were removed, but the audit event could not be recorded."
    return None
