import streamlit as st
from api.pydantic_models import ModelName, model_from_value
from api.settings import settings

from app.api_utils import (
    API_BASE_URL,
    delete_document,
    delete_session,
    get_health,
    get_metrics,
    get_quota,
    get_session_history,
    list_collections,
    list_documents,
    list_sessions,
    upload_document,
)

MODEL_OPTIONS = [model.value for model in ModelName]


def get_default_model_index():
    default_model = model_from_value(settings.default_model).value
    return MODEL_OPTIONS.index(default_model)


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

    labels = {"(current)": "(current)"}
    for session in sessions:
        preview = session.get("preview") or session["session_id"][:8]
        labels[session["session_id"]] = f"{preview} ({session['message_count']} msgs)"
    options = ["(current)"] + [s["session_id"] for s in sessions]
    selected = st.sidebar.selectbox(
        "Open a session",
        options=options,
        format_func=lambda session_id: labels.get(session_id, session_id),
        key="session_picker",
    )
    if selected == "(current)":
        return
    load_col, delete_col = st.sidebar.columns(2)
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
                st.rerun()


def _render_model_selector():
    st.sidebar.selectbox(
        "Select Model", options=MODEL_OPTIONS, index=get_default_model_index(), key="model"
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
    st.session_state.active_collection = active
    return active


def _render_ops_metrics():
    st.sidebar.header("Backend Metrics")
    metrics = get_metrics()
    if not metrics:
        st.sidebar.caption("Metrics unavailable.")
        return

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
    uploaded_file = st.sidebar.file_uploader(
        "Choose a file", type=["pdf", "docx", "html", "md", "txt", "csv"]
    )
    new_collection = st.sidebar.text_input(
        "New collection (optional)", key="new_collection", placeholder="e.g. clients-acme"
    )
    if uploaded_file is not None and st.sidebar.button("Upload"):
        target = (new_collection or "").strip() or active_collection or "default"
        with st.spinner("Uploading..."):
            upload_response = upload_document(uploaded_file, target)
            if upload_response:
                st.sidebar.success(
                    f"File '{uploaded_file.name}' uploaded successfully with ID "
                    f"{upload_response['file_id']}."
                )
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


def display_sidebar():
    st.sidebar.caption(f"API: {API_BASE_URL}")
    _render_health_status()
    _render_reset_chat()
    _render_session_history()
    _render_model_selector()
    active_collection = _render_collection_picker()
    _render_upload_document(active_collection)
    _render_refresh_documents(active_collection)
    _render_document_list()
    _render_ops_metrics()
