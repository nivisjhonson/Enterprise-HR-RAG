from __future__ import annotations

import logging
import uuid

import streamlit as st

from config.settings import get_settings
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

st.set_page_config(
    page_title="Enterprise HR Policy Assistant",
    page_icon="📚",
    layout="wide",
)
logger = logging.getLogger(__name__)


@st.cache_resource
def application_settings():
    return get_settings()


settings = application_settings()
try:
    database.initialize_database(settings)
    bootstrap_admin_from_environment(settings)
except Exception as exc:
    st.error(f"Could not initialize the application database: {exc}")
    st.stop()


def render_login() -> None:
    st.title("Enterprise HR Policy Assistant")
    st.caption("Intelligent HR Knowledge Retrieval for Modern Enterprises")
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.subheader("Sign in")
        if database.user_count(settings) == 0:
            st.info(
                "No administrator account exists yet. Configure "
                "`BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env`, "
                "then run `python scripts/initialize_database.py`."
            )
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            user = authenticate(settings, username, password)
            if user:
                st.session_state["user"] = user
                st.session_state["chat_history"] = []
                st.rerun()
            st.error("Sign-in failed. Check your username and password.")


def render_chat(user: dict[str, str]) -> None:
    st.subheader("Ask HR")
    st.caption("Answers are based on documents you are authorized to access.")
    suggestions = [
        "What is the annual leave policy?",
        "How does work-from-home approval work?",
        "What documents are required for onboarding?",
        "What is the reimbursement procedure?",
    ]
    if not st.session_state.get("chat_history"):
        st.write("Try a question")
        cols = st.columns(2)
        for index, suggestion in enumerate(suggestions):
            if cols[index % 2].button(suggestion, key=f"suggestion_{index}"):
                st.session_state["pending_question"] = suggestion

    for turn in st.session_state.get("chat_history", []):
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            if turn.get("sources"):
                with st.expander("View cited policy passages"):
                    for source in turn["sources"]:
                        location = (
                            f", page {source['page_number']}"
                            if source.get("page_number")
                            else ""
                        )
                        st.markdown(
                            f"**[{source['label']}] {source['filename']}{location}**"
                        )
                        st.caption(source.get("excerpt", ""))
            if turn.get("answer_id"):
                if turn.get("feedback"):
                    st.caption("Thanks for your feedback.")
                else:
                    positive, negative, _ = st.columns([1, 1, 8])
                    for column, rating, label in (
                        (positive, 1, "Helpful"),
                        (negative, -1, "Not helpful"),
                    ):
                        if column.button(
                            label,
                            key=f"feedback_{turn['answer_id']}_{rating}",
                        ):
                            try:
                                save_answer_feedback(
                                    settings,
                                    turn["answer_id"],
                                    rating,
                                    user,
                                )
                                turn["feedback"] = rating
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not save feedback: {exc}")

    prompt = st.chat_input("Ask a question about HR policies")
    if not prompt:
        prompt = st.session_state.pop("pending_question", None)
    if prompt:
        st.session_state["chat_history"].append(
            {"role": "user", "content": prompt}
        )
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Searching authorized policy documents..."):
                    result = answer_question(
                        settings, get_vector_store(settings), prompt, user
                    )
                st.markdown(result["answer"])
                if result["sources"]:
                    with st.expander("View cited policy passages"):
                        for source in result["sources"]:
                            location = (
                                f", page {source['page_number']}"
                                if source.get("page_number")
                                else ""
                            )
                            st.markdown(
                                f"**[{source['label']}] {source['filename']}{location}**"
                            )
                            st.caption(source["excerpt"])
                st.session_state["chat_history"].append(
                    {
                        "role": "assistant",
                        "content": result["answer"],
                        "sources": result["sources"],
                        "answer_id": uuid.uuid4().hex,
                    }
                )
            except Exception as exc:
                logger.exception("RAG answer generation failed.")
                if isinstance(exc, RuntimeError) and "GOOGLE_API_KEY" in str(exc):
                    message = str(exc)
                else:
                    message = (
                        "The answer service failed. Please try again; if the issue "
                        "continues, contact your administrator."
                    )
                st.error(message)
                st.session_state["chat_history"].append(
                    {"role": "assistant", "content": message, "sources": []}
                )
        st.rerun()

    if st.session_state.get("chat_history") and st.button(
        "Clear conversation", key="clear_chat"
    ):
        st.session_state["chat_history"] = []
        st.rerun()


def render_library(user: dict[str, str]) -> None:
    st.subheader("Document library")
    documents = get_accessible_documents(settings, user)
    if not documents:
        st.info("No policy documents are currently available to your account.")
        return
    categories = sorted({document["category"] for document in documents})
    selected_category = st.selectbox("Filter by category", ["All", *categories])
    search_text = st.text_input("Search document names")
    visible = [
        document
        for document in documents
        if selected_category == "All" or document["category"] == selected_category
        if search_text.casefold() in document["filename"].casefold()
    ]
    for document in visible:
        st.markdown(
            f"- **{document['filename']}** · {document['category']} · "
            f"version {document['version']}"
        )


def render_admin(user: dict[str, str]) -> None:
    require_admin(settings, user)
    st.subheader("Administrator dashboard")
    statistics = database.document_statistics(settings)
    first, second, third, fourth = st.columns(4)
    first.metric("Indexed documents", statistics["indexed_documents"])
    second.metric("Indexed chunks", statistics["chunks"])
    third.metric("Successful jobs", statistics["successful_jobs"])
    fourth.metric("Failed indexing jobs", statistics["failed_jobs"])

    upload_tab, documents_tab, users_tab = st.tabs(
        ["Upload / replace", "Manage documents", "Manage users"]
    )
    with upload_tab:
        st.caption("Uploading a different file with the same filename replaces its indexed version.")
        uploads = st.file_uploader(
            "Choose PDF, DOCX, or TXT files",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
        )
        category = st.text_input("Category", value="General")
        access_level = st.selectbox(
            "Who can retrieve these documents?",
            options=["employee", "admin"],
            format_func=lambda value: (
                "All authenticated employees" if value == "employee" else "Administrators only"
            ),
        )
        if st.button("Index selected documents", disabled=not uploads):
            try:
                store = get_vector_store(settings)
                for uploaded in uploads or []:
                    try:
                        result = ingest_document(
                            settings,
                            store,
                            uploaded.name,
                            uploaded.getvalue(),
                            category,
                            access_level,
                            user,
                        )
                        if result["unchanged"]:
                            st.info(f"{result['filename']} is already up to date.")
                        else:
                            st.success(
                                f"Indexed {result['filename']}: {result['chunk_count']} chunks."
                            )
                            if result["cleanup_warning"]:
                                st.warning(result["cleanup_warning"])
                    except Exception as exc:
                        st.error(f"{uploaded.name}: {exc}")
            except Exception as exc:
                st.error(f"Could not initialize document storage: {exc}")

    with documents_tab:
        pending_cleanup = database.list_pending_vector_cleanup(settings)
        if pending_cleanup:
            st.markdown("#### Obsolete vector cleanup")
            for pending in pending_cleanup:
                cleanup_label = (
                    f"{pending['filename']} · version {pending['version']} "
                    f"(current version {pending['current_version']})"
                )
                left, right = st.columns([4, 1])
                left.write(cleanup_label)
                left.caption(pending["error_message"])
                if right.button(
                    "Retry cleanup",
                    key=f"cleanup_{pending['document_id']}_{pending['version']}",
                ):
                    try:
                        warning = cleanup_obsolete_version(
                            settings,
                            get_vector_store(settings),
                            pending["document_id"],
                            pending["version"],
                            user,
                        )
                        st.success("Obsolete vectors removed.")
                        if warning:
                            st.warning(warning)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not remove obsolete vectors: {exc}")
        failed_jobs = [
            job
            for job in database.list_recent_indexing_jobs(settings)
            if job["status"] == "failed"
        ]
        if failed_jobs:
            st.markdown("#### Recent failed indexing jobs")
            for job in failed_jobs:
                st.error(f"{job['filename']}: {job['error_message']}")
        all_documents = database.list_documents(settings)
        if not all_documents:
            st.info("No documents have been uploaded.")
        else:
            for document in all_documents:
                with st.container(border=True):
                    left, right = st.columns([4, 1])
                    left.markdown(
                        f"**{document['filename']}** · {document['category']} · "
                        f"`{document['status']}`"
                    )
                    left.caption(
                        f"Version {document['version']} · {document['chunk_count']} chunks · "
                        f"Access: {document['access_level']} · Updated: {document['updated_at']}"
                    )
                    if document["error_message"]:
                        left.error(document["error_message"])
                    if document["status"] not in {"deleted", "deleting"}:
                        if right.button("Delete", key=f"delete_{document['id']}"):
                            try:
                                warning = delete_document(
                                    settings,
                                    get_vector_store(settings),
                                    document["id"],
                                    user,
                                )
                                st.success(f"Deleted {document['filename']}.")
                                if warning:
                                    st.warning(warning)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not delete {document['filename']}: {exc}")
                    elif document["status"] == "deleting":
                        if right.button("Retry cleanup", key=f"retry_{document['id']}"):
                            try:
                                warning = delete_document(
                                    settings,
                                    get_vector_store(settings),
                                    document["id"],
                                    user,
                                )
                                st.success(f"Deleted {document['filename']}.")
                                if warning:
                                    st.warning(warning)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Cleanup failed: {exc}")

    with users_tab:
        st.markdown("#### Create account")
        with st.form("create_user_form"):
            new_username = st.text_input("New username")
            new_password = st.text_input("Temporary password", type="password")
            new_role = st.selectbox("Role", ["employee", "admin"])
            create_submitted = st.form_submit_button("Create account")
        if create_submitted:
            try:
                create_user(
                    settings,
                    new_username,
                    new_password,
                    new_role,
                    actor=user,
                )
                st.success(f"Created {new_role} account '{new_username}'.")
            except Exception as exc:
                st.error(f"Could not create account: {exc}")

        st.markdown("#### Existing accounts")
        for account in database.list_users(settings):
            label = (
                f"{account['username']} · {account['role']} · "
                f"{'active' if account['is_active'] else 'disabled'}"
            )
            columns = st.columns([4, 1])
            columns[0].write(label)
            if account["username"] != user["username"]:
                enable = not bool(account["is_active"])
                if columns[1].button(
                    "Enable" if enable else "Disable",
                    key=f"user_{account['username']}",
                ):
                    try:
                        manage_user_active(
                            settings,
                            account["username"],
                            enable,
                            actor=user,
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not change account status: {exc}")


def main() -> None:
    user = st.session_state.get("user")
    if not user:
        render_login()
        return
    try:
        user = require_active_user(settings, user)
        st.session_state["user"] = user
    except PermissionError:
        st.session_state.pop("user", None)
        st.session_state.pop("chat_history", None)
        st.error("Your account is no longer active. Please sign in again.")
        return

    st.title("Enterprise HR Policy Assistant")
    st.caption(f"Signed in as **{user['username']}** · {user['role'].title()}")
    with st.sidebar:
        st.markdown("### HR Knowledge Assistant")
        st.caption(f"Environment: {settings.app_env}")
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("user", None)
            st.session_state.pop("chat_history", None)
            st.rerun()

    tab_names = ["Chat", "Document library"]
    if user["role"] == "admin":
        tab_names.append("Admin")
    tab_names.append("Settings")
    tabs = st.tabs(tab_names)
    with tabs[0]:
        render_chat(user)
    with tabs[1]:
        render_library(user)
    if user["role"] == "admin":
        with tabs[2]:
            render_admin(user)
        settings_tab = tabs[3]
    else:
        settings_tab = tabs[2]
    with settings_tab:
        st.subheader("Application settings")
        st.write(f"Embedding model: `{settings.embedding_model}`")
        st.write(f"Gemini model: `{settings.gemini_model}`")
        st.write(f"Retrieval top-k: `{settings.retrieval_top_k}`")
        st.write(f"Chunk size / overlap: `{settings.chunk_size}` / `{settings.chunk_overlap}`")
        st.write(f"Gemini API key configured: {'Yes' if settings.google_api_key else 'No'}")
        st.caption("Secrets are never displayed. Configure them in the local .env file.")
        if st.button("Check ChromaDB health"):
            try:
                count = vector_store_count(settings)
                st.success(f"ChromaDB is available. Indexed vector count: {count}.")
            except Exception as exc:
                st.error(f"ChromaDB health check failed: {exc}")
        completed_jobs = [
            job
            for job in database.list_recent_indexing_jobs(settings)
            if job["status"] == "succeeded"
        ]
        if completed_jobs:
            st.write(f"Last successful indexing: {completed_jobs[0]['completed_at']}")


if __name__ == "__main__":
    main()
