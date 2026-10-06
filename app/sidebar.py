import streamlit as st
from api.macros import extract_template_variables
from api.pydantic_models import ModelName, model_from_value
from api.settings import settings

from app.api_utils import (
    API_BASE_URL,
    apply_macro_to_session,
    create_macro,
    create_webhook,
    delete_collection,
    delete_document,
    delete_documents,
    delete_macro,
    delete_session,
    delete_sessions,
    delete_webhook,
    export_session,
    get_collection_analytics,
    get_collections_details,
    get_config,
    get_document_details,
    get_feedback_analytics,
    get_health,
    get_metrics,
    get_quota,
    get_session_history,
    get_session_macro_suggestions,
    get_stats,
    get_support_triage_analytics,
    list_collections,
    list_documents,
    list_feedback,
    list_macro_categories,
    list_macros,
    list_sessions,
    list_webhook_deliveries,
    list_webhooks,
    ping_webhook,
    rechunk_collection,
    rechunk_document,
    rename_collection,
    rename_session,
    render_macro,
    search_sessions,
    suggest_macros,
    summarize_session,
    update_session,
    update_webhook,
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
    raw_tags = current.get("tags") if current else ""
    if isinstance(raw_tags, list):
        curr_tags = ", ".join(raw_tags)
    elif isinstance(raw_tags, str):
        curr_tags = raw_tags
    else:
        curr_tags = ""

    new_tags_str = st.sidebar.text_input(
        "Tags (comma-separated)",
        value=curr_tags,
        key=f"session_tags_{selected}",
        placeholder="e.g. billing, urgent",
    )

    curr_summary = current.get("summary") if current else None
    if curr_summary:
        st.sidebar.caption(f"**Summary:** {curr_summary}")

    if st.sidebar.button("Auto-Summarize Dialogue", key=f"btn_summarize_{selected}"):
        with st.spinner("Summarizing dialogue..."):
            summary_res = summarize_session(selected, save_summary=True)
            if summary_res:
                st.sidebar.success("Session summarized!")
                if summary_res.get("sentiment"):
                    st.sidebar.info(f"Sentiment: {summary_res['sentiment']}")
                st.session_state.sessions = list_sessions()
                st.rerun()
            else:
                st.sidebar.error("Failed to summarize session.")

    curr_notes = (current.get("resolution_notes") or "") if current else ""
    new_notes = st.sidebar.text_area(
        "Resolution Notes",
        value=curr_notes,
        key=f"session_notes_{selected}",
        placeholder="Add resolution or follow-up notes...",
    )

    if st.sidebar.button("Update Metadata", key=f"btn_update_meta_{selected}"):
        tag_list = [t.strip() for t in new_tags_str.split(",") if t.strip()]
        with st.spinner("Updating session metadata..."):
            if update_session(
                selected,
                status=new_status,
                tags=tag_list,
                resolution_notes=new_notes.strip() if new_notes.strip() else None,
            ):
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
    """Render collection metadata and chunk distribution statistics."""
    if not active_collection:
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

            analytics = get_collection_analytics(active_collection)
            if analytics and analytics.get("total_chunks", 0) > 0:
                avg_len = analytics.get("avg_chunk_length", 0)
                st.metric("Avg Chunk Length", f"{avg_len:.0f} chars")
                min_len = analytics.get("min_chunk_length", 0)
                max_len = analytics.get("max_chunk_length", 0)
                st.caption(f"Min / Max chunk size: {min_len} / {max_len} chars")

                strategies = analytics.get("strategy_distribution", {})
                if strategies:
                    strat_pills = " · ".join(
                        f"{k}: {v}" for k, v in sorted(strategies.items())
                    )
                    st.caption(f"Strategies: {strat_pills}")

                histogram = analytics.get("length_histogram", {})
                if histogram and any(v > 0 for v in histogram.values()):
                    st.caption("Length distribution:")
                    for bucket, count in histogram.items():
                        if count > 0:
                            st.write(f"  {bucket} chars: {count}")

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


def _render_batch_rechunk(active_collection):
    """Render batch collection re-chunking controls in the sidebar."""
    if not active_collection:
        return
    with st.sidebar.expander("Batch Re-chunk Collection"):
        rechunk_strategy_options = ["recursive", "semantic", "markdown"]
        col_strat = st.selectbox(
            "Collection Strategy",
            options=rechunk_strategy_options,
            index=0,
            format_func=lambda s: s.capitalize(),
            key=f"batch_rechunk_strat_{active_collection}",
        )
        col_size = st.number_input(
            "Batch Chunk Size",
            min_value=100,
            max_value=4000,
            value=1000,
            step=50,
            key=f"batch_rechunk_size_{active_collection}",
        )
        max_col_overlap = max(0, int(col_size) - 1)
        col_overlap = st.number_input(
            "Batch Chunk Overlap",
            min_value=0,
            max_value=max_col_overlap,
            value=min(200, max_col_overlap),
            step=20,
            key=f"batch_rechunk_overlap_{active_collection}",
        )
        if st.button("Re-chunk Entire Collection", key=f"btn_batch_rechunk_{active_collection}"):
            with st.spinner(f"Re-chunking all documents in '{active_collection}'..."):
                res = rechunk_collection(
                    active_collection,
                    chunking_strategy=col_strat,
                    chunk_size=int(col_size),
                    chunk_overlap=int(col_overlap),
                )
                if res:
                    msg = (
                        f"Collection '{active_collection}' re-chunked: "
                        f"{res.get('rechunked_documents', 0)} re-chunked, "
                        f"{res.get('skipped_documents', 0)} skipped."
                    )
                    st.success(msg)
                    st.session_state.documents = list_documents(active_collection)
                    st.rerun()
                else:
                    st.error("Batch re-chunking failed.")


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
            if details.get("chunking_strategy"):
                strategy_label = str(details["chunking_strategy"]).capitalize()
                chunk_size = details.get("chunk_size", 1000)
                chunk_overlap = details.get("chunk_overlap", 200)
                st.markdown(
                    f"**Strategy:** `{strategy_label}`  \n"
                    f"**Chunk size:** `{chunk_size}` | **Overlap:** `{chunk_overlap}`"
                )
            if details.get("sha256"):
                st.caption(f"SHA-256: `{details['sha256'][:16]}...`")

            # Re-chunking controls
            rechunk_strategy_options = ["recursive", "semantic", "markdown"]
            current_strat = details.get("chunking_strategy") or "recursive"
            strat_idx = (
                rechunk_strategy_options.index(current_strat)
                if current_strat in rechunk_strategy_options
                else 0
            )
            new_strat = st.selectbox(
                "Re-chunk Strategy",
                options=rechunk_strategy_options,
                index=strat_idx,
                format_func=lambda s: s.capitalize(),
                key=f"rechunk_strat_{inspect_id}",
            )
            new_size = st.number_input(
                "Re-chunk Size",
                min_value=100,
                max_value=4000,
                value=int(details.get("chunk_size") or 1000),
                step=50,
                key=f"rechunk_size_{inspect_id}",
            )
            max_overlap = max(0, int(new_size) - 1)
            current_overlap = min(int(details.get("chunk_overlap") or 200), max_overlap)
            new_overlap = st.number_input(
                "Re-chunk Overlap",
                min_value=0,
                max_value=max_overlap,
                value=current_overlap,
                step=20,
                key=f"rechunk_overlap_{inspect_id}",
            )
            if st.button("Apply Re-chunk", key=f"rechunk_btn_{inspect_id}"):
                with st.spinner("Re-chunking document..."):
                    updated = rechunk_document(
                        inspect_id,
                        chunking_strategy=new_strat,
                        chunk_size=int(new_size),
                        chunk_overlap=int(new_overlap),
                    )
                    if updated:
                        st.session_state["inspect_doc_details"] = updated
                        st.success("Document re-chunked successfully!")
                        st.rerun()

            for chunk in details.get("chunks", [])[:10]:
                pg = f", p.{chunk['page']}" if chunk.get("page") else ""
                score = chunk.get("score")
                score_badge = f" (score: {score:.3f})" if score is not None else ""
                st.caption(f"Chunk {chunk['chunk_index']}{pg}{score_badge}:")
                st.text(chunk.get("preview", ""))


def _render_retrieval_filters():
    st.sidebar.header("Retrieval Filters")
    documents = st.session_state.get("documents", [])
    if not documents:
        st.session_state.selected_doc_ids = []
        st.sidebar.caption("No documents in the active collection.")
        st.sidebar.checkbox("Hybrid search (BM25 + vector)", value=False, key="use_hybrid")
        st.sidebar.checkbox(
    "Cross-encoder rerank (semantic)", value=False, key="use_cross_encoder_rerank"
)
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
    st.sidebar.checkbox(
    "Cross-encoder rerank (semantic)", value=False, key="use_cross_encoder_rerank"
)


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


def _render_support_triage_analytics():
    with st.sidebar.expander("Support Triage Analytics"):
        try:
            analytics = get_support_triage_analytics()
            if not analytics:
                st.caption("No triage analytics available.")
                return
            total = analytics.get("total_sessions", 0)
            res_rate = analytics.get("resolution_rate", 0.0)
            esc_rate = analytics.get("escalation_rate", 0.0)
            avg_turns = analytics.get("avg_turns_per_session", 0.0)

            col1, col2 = st.columns(2)
            col1.metric("Total Sessions", total)
            col2.metric("Resolution Rate", f"{res_rate:.1f}%")

            col3, col4 = st.columns(2)
            col3.metric("Escalation Rate", f"{esc_rate:.1f}%")
            col4.metric("Avg Turns", f"{avg_turns:.1f}")

            active = analytics.get("active_count", 0)
            resolved = analytics.get("resolved_count", 0)
            escalated = analytics.get("escalated_count", 0)
            closed = analytics.get("closed_count", 0)
            st.caption(
                f"🟢 Active: {active} · ✅ Resolved: {resolved} · "
                f"⚠️ Escalated: {escalated} · 🔒 Closed: {closed}"
            )

            top_tags = analytics.get("top_tags", [])
            if top_tags:
                tag_badges = " ".join([f"`{t['tag']}` ({t['count']})" for t in top_tags[:5]])
                st.markdown(f"**Top Tags:** {tag_badges}")
        except Exception as e:
            st.caption(f"Error loading triage analytics: {e}")


def _render_webhook_subscriptions():
    st.markdown("##### Subscriptions")
    hooks = list_webhooks()
    if not hooks:
        st.caption("No webhooks registered.")
        return

    for wh in hooks:
        wid = wh["id"]
        active_icon = "🟢" if wh.get("is_active") else "⚪"
        events_pill = wh.get("events", "*")
        failures = wh.get("failure_count", 0)
        fail_badge = f" · ⚠️ {failures} fails" if failures > 0 else ""
        st.markdown(
            f"**#{wid}** {active_icon} `{events_pill}`{fail_badge}  \n"
            f"`{wh['url']}`"
        )

        col1, col2, col3 = st.columns(3)
        if col1.button("Ping", key=f"ping_wh_{wid}"):
            res = ping_webhook(wid)
            if res and res.get("success"):
                st.success("Ping delivered!")
            else:
                err = res.get("error") if res else "Failed"
                st.error(f"Ping failed: {err}")

        toggle_label = "Disable" if wh.get("is_active") else "Enable"
        if col2.button(toggle_label, key=f"toggle_wh_{wid}"):
            update_webhook(wid, is_active=not wh.get("is_active"))
            st.rerun()

        if col3.button("Delete", key=f"del_wh_{wid}") and delete_webhook(wid):
            st.success("Deleted!")
            st.rerun()


def _render_webhook_register():
    st.markdown("---")
    st.markdown("##### Register Webhook")
    new_url = st.text_input(
        "Webhook URL",
        key="new_webhook_url",
        placeholder="https://example.com/alerts",
    )
    new_events = st.text_input(
        "Events (*, session.escalated, ...)",
        value="*",
        key="new_webhook_events",
    )
    new_secret = st.text_input(
        "Secret (HMAC-SHA256)",
        type="password",
        key="new_webhook_secret",
    )
    new_active = st.checkbox("Active", value=True, key="new_webhook_active")

    if st.button("Register Webhook", key="submit_new_webhook"):
        if not new_url.strip():
            st.error("Webhook URL is required.")
            return
        created = create_webhook(
            url=new_url.strip(),
            events=new_events.strip() or "*",
            secret=new_secret.strip() if new_secret else None,
            is_active=new_active,
        )
        if created:
            st.success(f"Webhook #{created['id']} registered!")
            st.rerun()


def _render_webhook_audit_log():
    st.markdown("---")
    st.markdown("##### Recent Deliveries")
    deliveries_data = list_webhook_deliveries(limit=5)
    items = deliveries_data.get("items", []) if deliveries_data else []
    if not items:
        st.caption("No delivery logs yet.")
        return

    for log in items:
        status_icon = "✅" if log.get("success") else "❌"
        code = log.get("status_code") or "ERR"
        st.markdown(
            f"{status_icon} **{log.get('event')}** (HTTP {code})  \n"
            f"`{log.get('url')}`"
        )
        if log.get("error_message"):
            st.caption(f"Error: {log['error_message']}")


def _render_macro_variable_inputs(macro_id: int, template_content: str) -> dict[str, str]:
    vars_found = extract_template_variables(template_content)
    var_values: dict[str, str] = {}
    if not vars_found:
        return var_values

    st.markdown("###### Template Variables")
    current_sid = st.session_state.get("session_id") or ""
    for var in vars_found:
        default_val = current_sid if var == "session_id" else ""
        val = st.text_input(
            f"{{{var}}}",
            value=default_val,
            key=f"macro_var_{macro_id}_{var}",
            placeholder=f"Value for {var}",
        )
        if val.strip():
            var_values[var] = val.strip()
    return var_values


def _render_macro_preview_and_apply(macro: dict, var_values: dict[str, str]):
    col_preview, col_apply = st.columns(2)
    if col_preview.button("Preview", key=f"preview_macro_{macro['id']}"):
        res = render_macro(macro["id"], variables=var_values, fallback_defaults=True)
        if res:
            st.session_state[f"macro_preview_{macro['id']}"] = res.get("rendered_content", "")

    preview_cached = st.session_state.get(f"macro_preview_{macro['id']}")
    if preview_cached:
        st.markdown("**Rendered Preview:**")
        st.info(preview_cached)

    if col_apply.button("Apply to Session", key=f"apply_macro_{macro['id']}"):
        current_sid = st.session_state.get("session_id")
        if not current_sid:
            st.error("No active chat session. Please start or load a session first.")
            return

        with st.spinner("Applying macro to session..."):
            res = apply_macro_to_session(
                session_id=current_sid,
                macro_id=macro["id"],
                variables=var_values,
                update_status=True,
                append_tags=True,
            )
            if res:
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append(
                    {"role": "user", "content": f"[Applied Macro: {macro['title']}]"}
                )
                st.session_state.messages.append(
                    {"role": "assistant", "content": res.get("rendered_content", "")}
                )
                st.session_state.sessions = list_sessions()
                st.success("Macro applied!")
                st.rerun()


def _render_macro_browser():
    st.markdown("##### Pre-approved Templates")
    categories = list_macro_categories()
    cat_filter_options = ["All Categories", *categories]
    selected_cat = st.selectbox(
        "Filter by category",
        options=cat_filter_options,
        key="macro_category_filter",
    )
    filter_arg = None if selected_cat == "All Categories" else selected_cat
    macros_list = list_macros(category=filter_arg)
    if not macros_list:
        st.caption("No macro templates found.")
        return

    macro_options = {f"{m['title']} ({m['shortcut']})": m for m in macros_list}
    chosen_label = st.selectbox(
        "Select macro",
        options=list(macro_options.keys()),
        key="selected_macro_choice",
    )
    chosen_macro = macro_options[chosen_label]

    status_str = (
        f" · 🎯 Sets status to `{chosen_macro['status_action']}`"
        if chosen_macro.get("status_action")
        else ""
    )
    st.caption(f"Category: **{chosen_macro['category']}**{status_str}")
    if chosen_macro.get("tags"):
        tag_pills = " ".join([f"`{t}`" for t in chosen_macro["tags"]])
        st.caption(f"Tags: {tag_pills}")

    var_values = _render_macro_variable_inputs(chosen_macro["id"], chosen_macro["content"])
    _render_macro_preview_and_apply(chosen_macro, var_values)

    if st.button("Delete Macro", key=f"del_macro_{chosen_macro['id']}") and delete_macro(
        chosen_macro["id"]
    ):
        st.success("Macro deleted.")
        st.rerun()


def _render_macro_creator():
    st.markdown("---")
    st.markdown("##### Create New Template")
    new_title = st.text_input(
        "Title", key="new_macro_title", placeholder="E.g., Move-in Instructions"
    )
    new_shortcut = st.text_input(
        "Shortcut", key="new_macro_shortcut", placeholder="E.g., /move-in"
    )
    new_cat = st.text_input("Category", key="new_macro_category", value="General")
    new_action = st.selectbox(
        "Status Action",
        options=["None", *SESSION_STATUS_OPTIONS],
        key="new_macro_status_action",
    )
    new_tags = st.text_input(
        "Tags (comma separated)",
        key="new_macro_tags",
        placeholder="e.g., leasing, onboarding",
    )
    new_content = st.text_area(
        "Content Template",
        key="new_macro_content",
        placeholder="Hello {customer_name}, welcome to unit {unit_id}!\nContact: {support_contact}",
    )

    if st.button("Save Template", key="save_new_macro"):
        if not new_title.strip() or not new_shortcut.strip() or not new_content.strip():
            st.error("Title, shortcut, and content are required.")
            return
        tags_list = [t.strip() for t in new_tags.split(",") if t.strip()]
        action_val = None if new_action == "None" else new_action
        created = create_macro(
            title=new_title.strip(),
            shortcut=new_shortcut.strip(),
            category=new_cat.strip() or "General",
            content=new_content.strip(),
            tags=tags_list,
            status_action=action_val,
        )
        if created:
            st.success(f"Macro '{created['title']}' created!")
            st.rerun()


def _render_smart_macro_suggestions():
    current_sid = st.session_state.get("session_id")
    if not current_sid:
        return

    res = get_session_macro_suggestions(current_sid, top_k=2, min_score=0.3)
    if not res or not res.get("suggestions"):
        return

    st.markdown("##### 💡 Smart Suggestions")
    detected_intent = res.get("detected_intent", "unknown")
    if detected_intent and detected_intent != "unknown":
        pretty_intent = detected_intent.replace("_", " ").title()
        st.caption(f"🎯 Detected Intent: **{pretty_intent}**")

    for sug in res.get("suggestions", []):
        score_pct = int(sug.get("score", 0.0) * 100)
        st.markdown(f"**{sug['title']}** (`{sug['shortcut']}`) — **{score_pct}% Match**")
        reasons = sug.get("match_reasons", [])
        if reasons:
            st.caption(" · ".join(reasons))

        if st.button("Apply Suggestion", key=f"apply_sug_{sug['macro_id']}"):
            with st.spinner("Applying suggestion..."):
                applied = apply_macro_to_session(
                    session_id=current_sid,
                    macro_id=sug["macro_id"],
                    variables=sug.get("suggested_variables", {}),
                    update_status=True,
                    append_tags=True,
                )
                if applied:
                    if "messages" not in st.session_state:
                        st.session_state["messages"] = []
                    st.session_state["messages"].append(
                        {"role": "user", "content": f"[Applied Suggestion: {sug['title']}]"}
                    )
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": applied.get("rendered_content", "")}
                    )
                    st.session_state["sessions"] = list_sessions()
                    st.success("Smart suggestion applied!")
                    st.rerun()

    st.markdown("---")


def _render_macro_query_tester():
    with st.expander("🔍 Test Query Intent & Matching"):
        test_query = st.text_input(
            "Test customer query",
            key="macro_tester_query",
            placeholder="e.g. pipe leaking in Apt 3B",
        )
        if test_query.strip():
            res = suggest_macros(test_query.strip(), top_k=3, min_score=0.2)
            if res:
                detected_intent = res.get("detected_intent", "unknown")
                intent_conf = res.get("intent_confidence", 0.0)
                conf_pct = int(intent_conf * 100)
                pretty_intent = detected_intent.replace("_", " ").title()
                st.caption(f"Intent: **{pretty_intent}** ({conf_pct}% confidence)")
                ext_vars = res.get("extracted_variables", {})
                if ext_vars:
                    vars_str = ", ".join([f"`{k}: {v}`" for k, v in ext_vars.items()])
                    st.caption(f"Entities: {vars_str}")

                suggestions = res.get("suggestions", [])
                if suggestions:
                    for s in suggestions:
                        match_pct = int(s["score"] * 100)
                        st.markdown(f"- **{s['title']}** (`{s['shortcut']}`) — {match_pct}%")
                else:
                    st.caption("No matching templates above threshold.")


def _render_quick_responses_panel():
    with st.sidebar.expander("Quick Responses & Macros"):
        _render_smart_macro_suggestions()
        _render_macro_browser()
        _render_macro_query_tester()
        _render_macro_creator()


def _render_webhook_manager():
    with st.sidebar.expander("Webhooks & Alerting"):
        _render_webhook_subscriptions()
        _render_webhook_register()
        _render_webhook_audit_log()


def display_sidebar():
    _init_config()
    st.sidebar.caption(f"API: {API_BASE_URL}")
    _render_health_status()
    _render_reset_chat()
    _render_session_history()
    _render_model_selector()
    active_collection = _render_collection_picker()
    _render_collection_insights(active_collection)
    _render_batch_rechunk(active_collection)
    _render_upload_document(active_collection)
    _render_refresh_documents(active_collection)
    _render_document_inspector()
    _render_retrieval_filters()
    _render_document_list()
    _render_feedback_analytics()
    _render_feedback_review()
    _render_support_triage_analytics()
    _render_quick_responses_panel()
    _render_webhook_manager()
    _render_ops_metrics()

