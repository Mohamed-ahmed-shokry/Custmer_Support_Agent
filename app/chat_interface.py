import contextlib
import json

import streamlit as st
from api.pydantic_models import model_from_value
from api.settings import settings

from app.api_utils import get_api_response, get_api_stream_response, parse_sse_line


def _render_assistant_message(answer, selected_model, session_id, sources):
    """Render the assistant message with details expander."""
    with st.chat_message("assistant"):
        st.markdown(answer)

        with st.expander("Details"):
            st.subheader("Generated Answer")
            st.code(answer)
            st.subheader("Model Used")
            st.code(selected_model)
            st.subheader("Session ID")
            st.code(session_id)
        if sources:
            with st.expander("Sources"):
                for source in sources:
                    label = source.get("filename") or "Unknown source"
                    page = source.get("page")
                    if page is not None:
                        label = f"{label}, page {page}"
                    st.markdown(f"**{label}**")
                    st.caption(source.get("preview", ""))


def _handle_streaming_response(prompt, session_id, selected_model, collections=None):
    """Handle streaming response from API."""
    stream = get_api_stream_response(prompt, session_id, selected_model, collections)
    if not stream:
        return None, None, None

    full_answer = ""
    sources = []
    session_id_result = session_id

    with st.chat_message("assistant"):
        placeholder = st.empty()
        for line in stream:
            event_type, data = parse_sse_line(line)
            if not data:
                continue

            if event_type == "message":
                full_answer += data
                placeholder.markdown(full_answer + "▌")
            elif event_type == "sources":
                with contextlib.suppress(json.JSONDecodeError):
                    sources = json.loads(data)
            elif event_type == "error":
                st.error(data)
                return None, None, None

        placeholder.markdown(full_answer)

    return full_answer, sources, session_id_result


def _handle_non_streaming_response(prompt, session_id, selected_model, collections=None):
    """Handle non-streaming response from API."""
    response = get_api_response(prompt, session_id, selected_model, collections)
    if not response:
        return None, None, None

    return response["answer"], response.get("sources", []), response.get("session_id")


def display_chat_interface():
    # Streaming toggle
    use_streaming = st.sidebar.checkbox("Use Streaming", value=True, key="use_streaming")

    # Chat interface
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Query:"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        selected_model = st.session_state.get(
            "model", model_from_value(settings.default_model).value
        )
        active_collection = st.session_state.get("active_collection")
        collections = [active_collection] if active_collection else None

        with st.spinner("Generating response..."):
            if use_streaming:
                answer, sources, new_session_id = _handle_streaming_response(
                    prompt, st.session_state.session_id, selected_model, collections
                )
            else:
                answer, sources, new_session_id = _handle_non_streaming_response(
                    prompt, st.session_state.session_id, selected_model, collections
                )

        if answer:
            st.session_state.session_id = new_session_id
            st.session_state.messages.append({"role": "assistant", "content": answer})
            _render_assistant_message(answer, selected_model, new_session_id, sources)
        else:
            st.error("Failed to get a response from the API. Please try again.")
