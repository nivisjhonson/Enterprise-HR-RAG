from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import asynccontextmanager
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from langchain_google_genai.chat_models import GoogleAPIError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from config.settings import Settings, get_settings
from src import database
from src.authentication import (
    authenticate,
    bootstrap_admin_from_environment,
    create_user,
    manage_user_active,
)
from src.authorization import (
    get_accessible_documents,
    require_active_user,
    require_admin,
)
from src.feedback import save_answer_feedback
from src.ingestion import (
    cleanup_obsolete_version,
    delete_document,
    ingest_document,
)
from src.rag_chain import answer_question
from src.vector_store import get_vector_store, vector_store_count

logger = logging.getLogger(__name__)
settings = get_settings()
_LOCAL_DEVELOPMENT_USER = {"username": "local-dev", "role": "admin"}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class FeedbackRequest(BaseModel):
    answer_id: str = Field(min_length=1, max_length=64)
    rating: int


class UserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=1024)
    role: str = Field(pattern="^(employee|admin)$")


class UserStatusRequest(BaseModel):
    is_active: bool


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, sqlite3.IntegrityError):
        return HTTPException(status_code=409, detail="That account already exists.")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def _google_api_error_detail(exc: GoogleAPIError) -> str:
    if exc.code == 429 or exc.status == "RESOURCE_EXHAUSTED":
        return "Gemini's request limit was reached. Wait a bit, then try again."
    if exc.code == 503 or exc.status == "UNAVAILABLE":
        return "Gemini is temporarily busy. Please wait a minute and try again."
    if exc.code == 504 or exc.status == "DEADLINE_EXCEEDED":
        return "Gemini took too long to respond. Please try again in a minute."
    return "Gemini is temporarily unavailable. Please try again later."


def _current_user(request: Request) -> dict[str, str]:
    if not settings.auth_enabled:
        client = request.client
        host = request.url.hostname
        try:
            is_loopback_client = client is not None and ip_address(client.host).is_loopback
            is_loopback_host = host is not None and (
                host.lower() == "localhost" or ip_address(host).is_loopback
            )
        except ValueError:
            is_loopback_client = False
            is_loopback_host = False
        if not is_loopback_client or not is_loopback_host:
            raise HTTPException(
                status_code=403,
                detail="No-login mode is available only from this computer.",
            )
        return dict(_LOCAL_DEVELOPMENT_USER)

    username = request.session.get("username")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    try:
        user = require_active_user(settings, {"username": username})
    except PermissionError as exc:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Your account is inactive. Sign in again.") from exc
    return user


def _current_admin(
    user: dict[str, str] = Depends(_current_user),
) -> dict[str, str]:
    try:
        require_admin(settings, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return user


@asynccontextmanager
async def _lifespan(_: FastAPI):
    if len(settings.session_secret_key) < 32:
        raise RuntimeError(
            "Set SESSION_SECRET_KEY to a randomly generated value of at least 32 characters in .env."
        )
    database.initialize_database(settings)
    if settings.auth_enabled:
        bootstrap_admin_from_environment(settings)
    yield


app = FastAPI(
    title="Enterprise HR Policy Assistant API",
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="hr_policy_session",
    max_age=12 * 60 * 60,
    same_site="lax",
    https_only=settings.app_env != "development",
)


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> dict[str, str]:
    if not settings.auth_enabled:
        raise HTTPException(status_code=403, detail="Sign-in is disabled in local no-login mode.")
    user = authenticate(settings, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Sign-in failed. Check your username and password.")
    request.session.clear()
    request.session["username"] = user["username"]
    return user


@app.get("/api/auth/status")
def authentication_status() -> dict[str, bool]:
    return {
        "authentication_enabled": settings.auth_enabled,
        "administrator_ready": database.user_count(settings) > 0,
    }


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def who_am_i(user: dict[str, str] = Depends(_current_user)) -> dict[str, str]:
    return user


@app.get("/api/documents")
def documents(user: dict[str, str] = Depends(_current_user)) -> list[dict[str, Any]]:
    return get_accessible_documents(settings, user)


@app.post("/api/chat")
def chat(
    payload: ChatRequest,
    user: dict[str, str] = Depends(_current_user),
) -> dict[str, Any]:
    try:
        store = (
            get_vector_store(settings)
            if database.document_statistics(settings)["indexed_documents"] > 0
            else None
        )
        result = answer_question(
            settings,
            store,
            payload.question.strip(),
            user,
        )
    except GoogleAPIError as exc:
        logger.exception("Gemini request failed.")
        raise HTTPException(
            status_code=503,
            detail=_google_api_error_detail(exc),
        ) from exc
    except RuntimeError as exc:
        if "GOOGLE_API_KEY" in str(exc):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        logger.exception("HR answer generation failed.")
        raise HTTPException(status_code=503, detail="The answer service is temporarily unavailable.") from exc
    except Exception as exc:
        logger.exception("HR answer generation failed.")
        raise HTTPException(status_code=503, detail="The answer service is temporarily unavailable.") from exc
    return {"answer_id": uuid.uuid4().hex, **result}


@app.post("/api/feedback")
def feedback(
    payload: FeedbackRequest,
    user: dict[str, str] = Depends(_current_user),
) -> dict[str, bool]:
    try:
        save_answer_feedback(settings, payload.answer_id, payload.rating, user)
    except (PermissionError, ValueError) as exc:
        raise _service_error(exc) from exc
    return {"ok": True}


@app.get("/api/admin/dashboard")
def admin_dashboard(
    _: dict[str, str] = Depends(_current_admin),
) -> dict[str, Any]:
    jobs = database.list_recent_indexing_jobs(settings)
    return {
        "statistics": database.document_statistics(settings),
        "documents": database.list_documents(settings),
        "pending_cleanup": database.list_pending_vector_cleanup(settings),
        "failed_jobs": [job for job in jobs if job["status"] == "failed"],
        "users": database.list_users(settings),
        "max_upload_size_mb": settings.max_upload_size_mb,
    }


@app.post("/api/admin/documents")
def upload_documents(
    files: list[UploadFile] = File(...),
    category: str = Form(...),
    access_level: str = Form(...),
    user: dict[str, str] = Depends(_current_admin),
) -> dict[str, list[dict[str, Any]]]:
    store = get_vector_store(settings)
    results: list[dict[str, Any]] = []
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    for uploaded in files:
        filename = uploaded.filename or "unnamed"
        try:
            content = uploaded.file.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ValueError(
                    f"File exceeds the {settings.max_upload_size_mb} MB upload limit."
                )
            result = ingest_document(
                settings,
                store,
                filename,
                content,
                category,
                access_level,
                user,
            )
            results.append({"status": "unchanged" if result["unchanged"] else "indexed", **result})
        except (ValueError, PermissionError, LookupError) as exc:
            results.append({"filename": filename, "status": "failed", "error": str(exc)})
        except Exception:
            logger.exception("Document upload failed for %s.", filename)
            results.append(
                {
                    "filename": filename,
                    "status": "failed",
                    "error": "The document could not be indexed. Check the server logs.",
                }
            )
        finally:
            uploaded.file.close()
    return {"results": results}


@app.delete("/api/admin/documents/{document_id}")
def remove_document(
    document_id: str,
    user: dict[str, str] = Depends(_current_admin),
) -> dict[str, Any]:
    try:
        warning = delete_document(
            settings, get_vector_store(settings), document_id, user
        )
    except (ValueError, PermissionError, LookupError) as exc:
        raise _service_error(exc) from exc
    return {"ok": True, "warning": warning}


@app.post("/api/admin/documents/{document_id}/cleanup/{version}")
def retry_cleanup(
    document_id: str,
    version: int,
    user: dict[str, str] = Depends(_current_admin),
) -> dict[str, Any]:
    try:
        warning = cleanup_obsolete_version(
            settings, get_vector_store(settings), document_id, version, user
        )
    except (ValueError, PermissionError, LookupError) as exc:
        raise _service_error(exc) from exc
    return {"ok": True, "warning": warning}


@app.post("/api/admin/users", status_code=201)
def add_user(
    payload: UserRequest,
    user: dict[str, str] = Depends(_current_admin),
) -> dict[str, bool]:
    try:
        create_user(settings, payload.username, payload.password, payload.role, actor=user)
    except (ValueError, PermissionError, LookupError, sqlite3.IntegrityError) as exc:
        raise _service_error(exc) from exc
    return {"ok": True}


@app.patch("/api/admin/users/{username}")
def update_user_status(
    username: str,
    payload: UserStatusRequest,
    user: dict[str, str] = Depends(_current_admin),
) -> dict[str, bool]:
    try:
        manage_user_active(settings, username, payload.is_active, actor=user)
    except (ValueError, PermissionError, LookupError) as exc:
        raise _service_error(exc) from exc
    return {"ok": True}


@app.get("/api/settings")
def application_settings(
    _: dict[str, str] = Depends(_current_user),
) -> dict[str, Any]:
    jobs = database.list_recent_indexing_jobs(settings, limit=1)
    return {
        "environment": settings.app_env,
        "embedding_model": settings.embedding_model,
        "gemini_model": settings.gemini_model,
        "retrieval_top_k": settings.retrieval_top_k,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "max_upload_size_mb": settings.max_upload_size_mb,
        "google_api_key_configured": bool(settings.google_api_key),
        "last_indexing": jobs[0]["completed_at"] if jobs else None,
    }


@app.get("/api/settings/health")
def storage_health(
    _: dict[str, str] = Depends(_current_user),
) -> dict[str, Any]:
    try:
        return {"ok": True, "indexed_vectors": vector_store_count(settings)}
    except Exception as exc:
        logger.exception("Vector storage health check failed.")
        raise HTTPException(status_code=503, detail="Vector storage is unavailable.") from exc


_frontend_directory = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _frontend_directory.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=_frontend_directory / "assets"),
        name="frontend-assets",
    )

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found.")
        return FileResponse(_frontend_directory / "index.html")
