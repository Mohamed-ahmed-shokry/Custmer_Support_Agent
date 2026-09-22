import streamlit as st
from api.pydantic_models import ModelName, model_from_value
from api.settings import settings

from app.api_utils import (
    API_BASE_URL,
    delete_collection,
    delete_document,
    delete_documents,
    delete_session,
    delete_sessions,
    export_session,
    get_collections_details,
    get_config,
    get_document_details,
    get_feedback_analytics,
    get_health,
    get_metrics,
    get_quota,
    get_session_history,
    get_stats,
    list_collections,
    list_documents,
    list_feedback,
    list_sessions,
    rename_collection,
    rename_session,
    search_sessions,
    update_session,
    upload_document,
    upload_documents,
)

MODEL_OPTIONS = [model.value for model in ModelName]
SESSION_STATUS_OPTIONS = ["active", "resolved", "escalated", "closed"]
SESSION_STATUS_FILTER_OPTIONS = ["All statuses", *SESSION_STATUS_OPTIONS]
SESSION_STATUS_ICONS = {
    "active": "🟢",
    "resolved": "✅",
    "escalated": "⚠️",
    "closed": "🔒",
}


def _init_config():
    if "config" not in st.session_state or st.session_state.config is None:
        st.session_state.config = get_config()
    return st.session_state.config


def get_model_options(config=None):
    if config and config.get("supported_models"):
        return list(config["supported_models"])
    return MODEL_OPTIONS


def get_default_model_index(options=None, config=None):
    if options is None:
        options = MODEL_OPTIONS
    if config and config.get("default_model"):
        default_model = config["default_model"]
    else:
        default_model = model_from_value(settings.default_model).value
    if default_model in options:
        return options.index(default_model)
    return 0


def _render_health_status():
    health = get_health()
    if health:
        st.sidebar.success(f"Backend: {health['status']} ({health['version']})")
    else:
        st.sidebar.error("Backend unavailable")


def _render_reset_chat():
    if st.sidebar.button("Reset Chat"):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()


def _filter_sessions(sessions):
    status_filter = st.sidebar.selectbox(
        "Filter by status",
        options=SESSION_STATUS_FILTER_OPTIONS,
        key="session_status_filter",
    )
    if status_filter != "All statuses":
        sessions = [s for s in sessions if (s.get("status") or "active") == status_filter]

    search_query = st.sidebar.text_input(
        "Search conversations", key="session_search_query", placeholder="Filter by keyword..."
    )
    if not search_query.strip():
        return sessions
    search_hits = search_sessions(search_query.strip())
    matching_ids = {h["session_id"] for h in search_hits}
    return [s for s in sessions if s["session_id"] in matching_ids]


def _handle_session_actions(selected, new_label):
    rename_col, load_col, delete_col = st.sidebar.columns(3)
    if rename_col.button("Rename") and new_label.strip():
        with st.spinner("Renaming session..."):
            if rename_session(selected, new_label.strip()):
                st.session_state.sessions = list_sessions()
                st.rerun()
    if load_col.button("Load Session"):
        with st.spinner("Loading session..."):
            history = get_session_history(selected)
            st.session_state.session_id = selected
            st.session_state.messages = [
                {"role": m["role"], "content": m["content"]} for m in history
            ]
            st.rerun()
    if delete_col.button("Delete"):
        with st.spinner("Deleting session..."):
            if delete_session(selected):
                st.sidebar.success("Session deleted.")
                st.session_state.sessions = list_sessions()
                if st.session_state.session_id == selected:
                    st.session_state.session_id = None
                    st.session_state.messages = []
                st.session_state.pop("export_text", None)
                st.session_state.pop("export_session_id", None)
                st.rerun()


def _render_session_history():
    st.sidebar.header("Past Sessions")
    if st.sidebar.button("Refresh Sessions"):
        st.session_state.sessions = list_sessions()

    if "sessions" not in st.session_state:
        st.session_state.sessions = list_sessions()

    sessions = st.session_state.sessions
    if not sessions:
        st.sidebar.caption("No past sessions yet.")
        return

    sessions = _filter_sessions(sessions)
    if not sessions:
        st.sidebar.caption("No matching conversations found.")
        return

    labels = {"(current)": "(current)"}
    for session in sessions:
        title = session.get("label") or session.get("preview") or session["session_id"][:8]
        status = session.get("status") or "active"
        icon = SESSION_STATUS_ICONS.get(status, "🟢")
        tags = session.get("tags") or []
        tags_str = f" [{', '.join(tags)}]" if tags else ""
        labels[session["session_id"]] = (
            f"{icon} {title} ({session['message_count']} msgs){tags_str}"
        )

    bulk_delete = st.sidebar.checkbox(
        "Bulk delete sessions", value=False, key="bulk_delete_sessions_mode"
    )
    if bulk_delete:
        to_delete = st.sidebar.multiselect(
            "Select sessions to delete",
            options=[s["session_id"] for s in sessions],
            format_func=lambda sid: labels.get(sid, sid),
            key="bulk_delete_session_ids",
        )
        if st.sidebar.button("Delete Selected Sessions") and to_delete:
            with st.spinner("Deleting sessions..."):
                res = delete_sessions(to_delete)
                if res and res.get("deleted", 0) > 0:
                    st.sidebar.success(f"Deleted {res['deleted']} session(s).")
                    st.session_state.sessions = list_sessions()
                    if st.session_state.session_id in to_delete:
                        st.session_state.session_id = None
                        st.session_state.messages = []
                    if st.session_state.get("export_session_id") in to_delete:
                        st.session_state.pop("export_text", None)
                        st.session_state.pop("export_session_id", None)
                    st.rerun()
                else:
                    st.sidebar.error("Failed to delete sessions.")
        return

    options = ["(current)"] + [s["session_id"] for s in sessions]
    selected = st.sidebar.selectbox(
        "Open a session",
        options=options,
        format_func=lambda session_id: labels.get(session_id, session_id),
        key="session_picker",
    )
    if selected == "(current)":
        return
    new_label = st.sidebar.text_input("Rename session", key="rename_session", max_chars=80)
    _handle_session_actions(selected, new_label)
    _render_session_metadata(selected, sessions)
    _render_session_export(selected)


def _render_session_metadata(selected, sessions):
    current = next((s for s in sessions if s.get("session_id") == selected), None)
    curr_status = (current.get("status") or "active") if current else "active"
    status_idx = (
        SESSION_STATUS_OPTIONS.index(curr_status)
        if curr_status in SESSION_STATUS_OPTIONS
        else 0
    )
    new_status = st.sidebar.selectbox(
        "Session status",
        options=SESSION_STATUS_OPTIONS,
        index=status_idx,
        key=f"session_status_{selected}",
    )
    curr_tags = ", ".join(current.get("tags") or []) if current else ""
    new_tags_str = st.sidebar.text_input(
        "Tags (comma-separated)",
        value=curr_tags,
        key=f"session_tags_{selected}",
        placeholder="e.g. billing, urgent",
    )
    if st.sidebar.button("Update Metadata", key=f"btn_update_meta_{selected}"):
        tag_list = [t.strip() for t in new_tags_str.split(",") if t.strip()]
        with st.spinner("Updating session metadata..."):
            if update_session(selected, status=new_status, tags=tag_list):
                st.sidebar.success("Session metadata updated.")
                st.session_state.sessions = list_sessions()
                st.rerun()
            else:
                st.sidebar.error("Failed to update session metadata.")


EXPORT_FORMAT_META = {
    "markdown": {"ext": ".md", "mime": "text/markdown", "label": "Markdown (.md)"},
    "json": {"ext": ".json", "mime": "application/json", "label": "JSON (.json)"},
    "csv": {"ext": ".csv", "mime": "text/csv", "label": "CSV (.csv)"},
}


def get_export_formats(config=None):
    if config and config.get("supported_export_formats"):
        return list(config["supported_export_formats"])
    return list(EXPORT_FORMAT_META.keys())


def _render_session_export(selected):
    config = st.session_state.get("config")
    formats = get_export_formats(config)
    selected_format = st.sidebar.selectbox(
        "Export format",
        options=formats,
        format_func=lambda fmt: EXPORT_FORMAT_META.get(fmt, {}).get("label", fmt),
        key="export_format_selector",
    )
    if st.sidebar.button("Prepare Export"):
        with st.spinner("Preparing export..."):
            try:
                text = export_session(selected, format=selected_format)
            except TypeError:
                text = export_session(selected)
            if text is not None:
                st.session_state.export_text = text
                st.session_state.export_session_id = selected
                st.session_state.export_format = selected_format
    if st.session_state.get("export_session_id") == selected and st.session_state.get(
        "export_text"
    ):
        active_fmt = st.session_state.get("export_format", "markdown")
        meta = EXPORT_FORMAT_META.get(
            active_fmt, {"ext": ".md", "mime": "text/markdown", "label": "Markdown"}
        )
        ext = meta["ext"]
        mime = meta["mime"]
        st.sidebar.download_button(
            f"Download ({ext})",
            data=st.session_state.export_text,
            file_name=f"{selected}{ext}",
            mime=mime,
            key="download_export",
        )


def _render_model_selector():
    config = st.session_state.get("config")
    options = get_model_options(config)
    default_idx = get_default_model_index(options, config)
    st.sidebar.selectbox(
        "Select Model", options=options, index=default_idx, key="model"
    )


ALL_COLLECTIONS = "All collections"


def _render_collection_picker():
    st.sidebar.header("Collection")
    if st.sidebar.button("Refresh Collections"):
        st.session_state.collections = list_collections()

    if "collections" not in st.session_state:
        st.session_state.collections = list_collections()

    known = st.session_state.collections or ["default"]
    options = [ALL_COLLECTIONS] + [c for c in known if c != ALL_COLLECTIONS]
    selected = st.sidebar.selectbox("Active collection", options=options, key="collection_picker")
    active = None if selected == ALL_COLLECTIONS else selected
    if st.session_state.get("docs_collection") != active:
        st.session_state.documents = list_documents(active)
        st.session_state.docs_collection = active
        st.session_state.selected_doc_ids = []
    st.session_state.active_collection = active
    if active and active != "default":
        new_name = st.sidebar.text_input(
            "Rename collection", key="rename_collection", placeholder="e.g. clients-globex"
        )
        rename_col, delete_col = st.sidebar.columns(2)
        if rename_col.button("Rename") and new_name.strip():
            with st.spinner("Renaming collection..."):
                renamed = rename_collection(active, new_name.strip())
                if renamed:
                    st.sidebar.success(f"Renamed to '{renamed['collection']}'.")
                    st.session_state.collections = list_collections()
                    st.session_state.documents = list_documents(renamed["collection"])
                    st.session_state.docs_collection = renamed["collection"]
                    st.session_state.active_collection = renamed["collection"]
                    st.rerun()
        if delete_col.button("Delete"):
            with st.spinner("Deleting collection..."):
                if delete_collection(active):
                    st.sidebar.success(f"Collection '{active}' deleted.")
                    st.session_state.collections = list_collections()
                    st.session_state.documents = list_documents(None)
                    st.session_state.docs_collection = None
                    st.session_state.active_collection = None
                    st.rerun()
    return active


def _render_collection_insights(active_collection):
    """Render collection metadata and storage statistics."""
    if not active_collection or active_collection == "default":
        return
    with st.sidebar.expander("Collection Insights"):
        try:
            details = get_collections_details()
            collection_detail = next(
                (d for d in details if d["collection"] == active_collection), None
            )
            if not collection_detail:
                st.caption("No details available.")
                return
            st.metric("Documents", collection_detail.get("document_count", 0))
            st.metric("Chunks", collection_detail.get("chunk_count", 0))
            file_formats = collection_detail.get("file_formats", {})
            if file_formats:
                st.caption("File formats:")
                for fmt, count in file_formats.items():
                    st.write(f"  {fmt}: {count}")
            earliest = collection_detail.get("earliest_upload")
            latest = collection_detail.get("latest_upload")
            if earliest:
                st.caption(f"First upload: {earliest}")
            if latest:
                st.caption(f"Last upload: {latest}")
        except Exception as e:
            st.caption(f"Error loading collection details: {e}")


def _render_ops_metrics():
    st.sidebar.header("Backend Metrics")
    metrics = get_metrics()
    if not metrics:
        st.sidebar.caption("Metrics unavailable.")
        return

    stats = get_stats()
    if stats:
        st.sidebar.caption(
            f"Library: {stats.get('documents', 0)} docs · "
            f"{stats.get('collections', 0)} collections · "
            f"{stats.get('sessions', 0)} sessions"
        )

    requests_total = (
        metrics.get("chat_requests", 0)
        + metrics.get("stream_requests", 0)
        + metrics.get("uploads", 0)
        + metrics.get("deletes", 0)
    )
    errors_total = metrics.get("chat_errors", 0) + metrics.get("upload_errors", 0)
    st.sidebar.metric("Requests", requests_total)
    st.sidebar.metric("Errors", errors_total)
    st.sidebar.metric("Prompt tokens (est.)", metrics.get("prompt_tokens_est", 0))
    st.sidebar.metric("Completion tokens (est.)", metrics.get("completion_tokens_est", 0))

    quota = get_quota()
    if quota and not quota.get("unlimited", True):
        st.sidebar.metric(
            "Daily token quota left (est.)",
            quota.get("remaining", 0),
            delta=None,
        )

    with st.sidebar.expander("Latency averages (s)"):
        latency_keys = sorted(key for key in metrics if key.startswith("latency_avg_seconds_"))
        if not latency_keys:
            st.caption("No latency data yet.")
        for key in latency_keys:
            group = key.removeprefix("latency_avg_seconds_")
            st.write(f"{group}: {metrics[key]}")


def _render_upload_document(active_collection):
    st.sidebar.header("Upload Document")
    config = st.session_state.get("config")
    if config and "max_upload_size_bytes" in config:
        max_mb = config["max_upload_size_bytes"] // (1024 * 1024)
    else:
        max_mb = settings.max_upload_mb
    max_files = (
        config.get("max_bulk_upload_files", settings.max_bulk_files)
        if config
        else settings.max_bulk_files
    )
    st.sidebar.caption(f"Max {max_mb} MB per file · Up to {max_files} files per batch")
    uploaded_files = st.sidebar.file_uploader(
        "Choose file(s)",
        type=["pdf", "docx", "html", "md", "txt", "csv"],
        accept_multiple_files=True,
    )
    new_collection = st.sidebar.text_input(
        "New collection (optional)", key="new_collection", placeholder="e.g. clients-acme"
    )
    if uploaded_files and st.sidebar.button("Upload"):
        if len(uploaded_files) > max_files:
            st.sidebar.error(f"Cannot upload more than {max_files} files at once.")
            return
        target = (new_collection or "").strip() or active_collection or "default"
        with st.spinner("Uploading..."):
            if len(uploaded_files) == 1:
                upload_response = upload_document(uploaded_files[0], target)
                if upload_response:
                    st.sidebar.success(
                        f"File '{uploaded_files[0].name}' uploaded successfully with ID "
                        f"{upload_response['file_id']}."
                    )
            else:
                bulk_response = upload_documents(uploaded_files, target)
                if bulk_response:
                    st.sidebar.success(
                        f"Uploaded {bulk_response['uploaded']} of "
                        f"{bulk_response['uploaded'] + bulk_response['failed']} files."
                    )
                    for item in bulk_response["results"]:
                        if item["status"] == "error":
                            st.sidebar.error(f"{item['filename']}: {item['detail']}")
            st.session_state.collections = list_collections()
            st.session_state.documents = list_documents(active_collection)


def _render_refresh_documents(active_collection):
    st.sidebar.header("Uploaded Documents")
    if st.sidebar.button("Refresh Document List"):
        with st.spinner("Refreshing..."):
            st.session_state.documents = list_documents(active_collection)

    if "documents" not in st.session_state:
        st.session_state.documents = list_documents(active_collection)


def _render_document_list():
    documents = st.session_state.documents
    if not documents:
        return

    for doc in documents:
        st.sidebar.markdown(
            f"**{doc['filename']}**  \nID: `{doc['id']}`  \nCollection: "
            f"`{doc.get('collection', 'default')}`  \nUploaded: `{doc['upload_timestamp']}`"
        )

    bulk_delete = st.sidebar.checkbox(
        "Bulk delete mode", value=False, key="bulk_delete_mode"
    )
    if bulk_delete:
        to_delete = st.sidebar.multiselect(
            "Select documents to delete",
            options=[doc["id"] for doc in documents],
            format_func=lambda x: next(doc["filename"] for doc in documents if doc["id"] == x),
            key="bulk_delete_ids",
        )
        if st.sidebar.button("Delete Selected Documents") and to_delete:
            with st.spinner("Deleting documents..."):
                res = delete_documents(to_delete)
                if res and res.get("deleted", 0) > 0:
                    st.sidebar.success(f"Deleted {res['deleted']} document(s).")
                    st.session_state.documents = list_documents(
                        st.session_state.get("active_collection")
                    )
                    st.rerun()
                else:
                    st.sidebar.error("Failed to delete documents.")
    else:
        selected_file_id = st.sidebar.selectbox(
            "Select a document to delete",
            options=[doc["id"] for doc in documents],
            format_func=lambda x: next(doc["filename"] for doc in documents if doc["id"] == x),
        )
        if st.sidebar.button("Delete Selected Document"):
            with st.spinner("Deleting..."):
                delete_response = delete_document(selected_file_id)
                if delete_response:
                    st.sidebar.success(f"Document with ID {selected_file_id} deleted successfully.")
                    st.session_state.documents = list_documents(
                        st.session_state.get("active_collection")
                    )
                else:
                    st.sidebar.error(f"Failed to delete document with ID {selected_file_id}.")


def _render_document_inspector():
    documents = st.session_state.get("documents", [])
    if not documents:
        return
    with st.sidebar.expander("Inspect Document Chunks"):
        inspect_id = st.selectbox(
            "Select document to inspect",
            options=[doc["id"] for doc in documents],
            format_func=lambda x: next(doc["filename"] for doc in documents if doc["id"] == x),
            key="inspect_doc_id",
        )
        if st.button("Load Details", key="load_doc_details"):
            with st.spinner("Loading chunks..."):
                details = get_document_details(inspect_id)
                st.session_state["inspect_doc_details"] = details

        details = st.session_state.get("inspect_doc_details")
        if details and details.get("id") == inspect_id:
            st.markdown(f"**Total chunks:** `{details.get('chunk_count', 0)}`")
            if details.get("sha256"):
                st.caption(f"SHA-256: `{details['sha256'][:16]}...`")
            for chunk in details.get("chunks", [])[:10]:
                pg = f", p.{chunk['page']}" if chunk.get("page") else ""
                st.caption(f"Chunk {chunk['chunk_index']}{pg}:")
                st.text(chunk.get("preview", ""))


def _render_retrieval_filters():
    st.sidebar.header("Retrieval Filters")
    documents = st.session_state.get("documents", [])
    if not documents:
        st.session_state.selected_doc_ids = []
        st.sidebar.caption("No documents in the active collection.")
        st.sidebar.checkbox("Hybrid search (BM25 + vector)", value=False, key="use_hybrid")
        return
    st.sidebar.multiselect(
        "Restrict to document(s)",
        options=[doc["id"] for doc in documents],
        default=[],
        format_func=lambda doc_id: next(
            doc["filename"] for doc in documents if doc["id"] == doc_id
        ),
        key="selected_doc_ids",
    )
    st.sidebar.checkbox("Hybrid search (BM25 + vector)", value=False, key="use_hybrid")


def _render_feedback_analytics():
    with st.sidebar.expander("Feedback Analytics"):
        try:
            analytics = get_feedback_analytics(recent_comments_limit=3)
            total = analytics.get("total_feedback", 0)
            positive = analytics.get("positive_feedback", 0)
            negative = analytics.get("negative_feedback", 0)
            satisfaction = analytics.get("satisfaction_rate", 0.0)
            comment_rate = analytics.get("comment_rate", 0.0)
            recent = analytics.get("recent_comments", [])

            st.metric("Satisfaction Rate", f"{satisfaction:.1f}%")
            col1, col2 = st.columns(2)
            col1.metric("👍 Positive", positive)
            col2.metric("👎 Negative", negative)

            st.caption(f"Total feedback: {total} · Comment rate: {comment_rate:.1f}%")

            if recent:
                st.caption("Recent comments:")
                for item in recent:
                    icon = "👍" if item.get("rating") == 1 else "👎"
                    sid = item.get("session_id", "")[:8]
                    comment = item.get("comment")
                    if comment:
                        st.markdown(f"{icon} `{sid}`: \"{comment[:50]}...\"")
        except Exception as e:
            st.caption(f"Error loading analytics: {e}")


def _render_feedback_review():
    with st.sidebar.expander("Feedback Review"):
        rating_filter_label = st.selectbox(
            "Filter by rating",
            options=["All", "Positive (👍)", "Negative (👎)"],
            key="feedback_rating_filter",
        )
        rating_filter = None
        if rating_filter_label == "Positive (👍)":
            rating_filter = 1
        elif rating_filter_label == "Negative (👎)":
            rating_filter = -1

        if st.button("Refresh Feedback", key="refresh_feedback_btn"):
            st.session_state.feedback_data = list_feedback(rating=rating_filter, limit=20)

        if (
            "feedback_data" not in st.session_state
            or st.session_state.get("feedback_filter") != rating_filter
        ):
            st.session_state.feedback_data = list_feedback(rating=rating_filter, limit=20)
            st.session_state.feedback_filter = rating_filter

        data = st.session_state.get("feedback_data")
        if not data or not data.get("items"):
            st.caption("No feedback recorded yet.")
            return

        items = data["items"]
        total = data.get("total", len(items))
        st.caption(f"Showing {len(items)} of {total} feedback entries")

        for item in items:
            icon = "👍" if item.get("rating") == 1 else "👎"
            sid = item.get("session_id", "")
            sid_short = sid[:8]
            created = item.get("created_at", "")
            comment = item.get("comment")
            comment_text = f'"{comment}"' if comment else "*(no comment)*"
            st.markdown(f"**{icon} {sid_short}** ({created})  \n{comment_text}")
            if st.button(f"Open {sid_short}", key=f"open_fb_{item['id']}"):
                with st.spinner("Loading session..."):
                    history = get_session_history(sid)
                    st.session_state.session_id = sid
                    st.session_state.messages = [
                        {"role": m["role"], "content": m["content"]} for m in history
                    ]
                    st.rerun()


def display_sidebar():
    _init_config()
    st.sidebar.caption(f"API: {API_BASE_URL}")
    _render_health_status()
    _render_reset_chat()
    _render_session_history()
    _render_model_selector()
    active_collection = _render_collection_picker()
    _render_collection_insights(active_collection)
    _render_upload_document(active_collection)
    _render_refresh_documents(active_collection)
    _render_document_inspector()
    _render_retrieval_filters()
    _render_document_list()
    _render_feedback_analytics()
    _render_feedback_review()
    _render_ops_metrics()
