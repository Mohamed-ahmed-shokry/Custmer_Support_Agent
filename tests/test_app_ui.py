from pathlib import Path

import pytest
from app import chat_interface, sidebar
from tests.fake_streamlit import FakeStreamlit


def _session_state(messages=None, session_id=None):
    st = FakeStreamlit()
    st.session_state["messages"] = messages if messages is not None else []
    st.session_state["session_id"] = session_id
    return st


# --- chat_interface -------------------------------------------------------


def test_render_feedback_widget_posts_once(monkeypatch):
    st = _session_state(messages=[{"role": "human", "content": "q"}])
    st.values["feedback_s1_1"] = 0  # thumbs up
    monkeypatch.setattr(chat_interface, "st", st)

    submitted = []

    def fake_submit(sid, rating):
        submitted.append((sid, rating))
        return True

    monkeypatch.setattr(chat_interface, "submit_feedback", fake_submit)

    chat_interface._render_feedback_widget("s1")
    chat_interface._render_feedback_widget("s1")

    assert submitted == [("s1", 1)]
    assert st.toasts == ["Thanks for the feedback!"]
    assert st.session_state["rated_feedback"]["feedback_s1_1"] == 0


def test_render_feedback_widget_no_selection_does_not_submit(monkeypatch):
    st = _session_state(messages=[{"role": "human", "content": "q"}])
    monkeypatch.setattr(chat_interface, "st", st)
    called = []
    monkeypatch.setattr(chat_interface, "submit_feedback", lambda sid, rating: called.append(rating))  # noqa: E501

    chat_interface._render_feedback_widget("s1")

    assert called == []


def test_handle_streaming_response_parses_answer_and_sources(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    lines = [
        "data: Hello",
        "",
        "event: sources",
        'data: [{"filename": "a.pdf", "page": 2}]',
        "",
        "data: world",
        "",
    ]
    monkeypatch.setattr(chat_interface, "get_api_stream_response", lambda *a, **k: iter(lines))

    answer, sources, session_id = chat_interface._handle_streaming_response(
        "q", "s1", "gpt-4o-mini"
    )

    assert answer == "Helloworld"
    assert sources == [{"filename": "a.pdf", "page": 2}]
    assert session_id == "s1"
    assert st.errors == []


def test_handle_streaming_response_no_stream_returns_none(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    monkeypatch.setattr(chat_interface, "get_api_stream_response", lambda *a, **k: None)

    assert chat_interface._handle_streaming_response("q", "s1", "m") == (None, None, None)


def test_handle_streaming_response_error_event_aborts(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    lines = ["data: partial", "", "event: error", "data: Failed to generate response", ""]
    monkeypatch.setattr(chat_interface, "get_api_stream_response", lambda *a, **k: iter(lines))

    result = chat_interface._handle_streaming_response("q", "s1", "m")

    assert result == (None, None, None)
    assert st.errors == ["Failed to generate response"]


def test_handle_streaming_response_ignores_invalid_sources_json(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    lines = ["data: ok", "", "event: sources", "data: {not json", ""]
    monkeypatch.setattr(chat_interface, "get_api_stream_response", lambda *a, **k: iter(lines))

    answer, sources, _ = chat_interface._handle_streaming_response("q", "s1", "m")

    assert answer == "ok"
    assert sources == []


def test_handle_non_streaming_response_success(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    monkeypatch.setattr(
        chat_interface,
        "get_api_response",
        lambda *a, **k: {"answer": "hi", "sources": [{"filename": "a.pdf"}], "session_id": "s9"},
    )

    answer, sources, session_id = chat_interface._handle_non_streaming_response("q", "s1", "m")

    assert (answer, sources, session_id) == ("hi", [{"filename": "a.pdf"}], "s9")


def test_handle_non_streaming_response_none_returns_none(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    monkeypatch.setattr(chat_interface, "get_api_response", lambda *a, **k: None)

    assert chat_interface._handle_non_streaming_response("q", "s1", "m") == (None, None, None)


@pytest.mark.parametrize("streaming", [True, False])
def test_display_chat_interface_submits_and_records_message(monkeypatch, streaming):
    st = _session_state(messages=[], session_id="old")
    st.values["use_streaming"] = streaming
    st._chat_input_value = "hello there"
    monkeypatch.setattr(chat_interface, "st", st)

    handler = "_handle_streaming_response" if streaming else "_handle_non_streaming_response"
    other = "_handle_non_streaming_response" if streaming else "_handle_streaming_response"
    monkeypatch.setattr(chat_interface, handler, lambda *a, **k: ("hi back", [], "new-s1"))
    monkeypatch.setattr(chat_interface, other, lambda *a, **k: None)

    chat_interface.display_chat_interface()

    assert st.session_state["messages"] == [
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": "hi back"},
    ]
    assert st.session_state["session_id"] == "new-s1"


def test_display_chat_interface_failed_response_keeps_session(monkeypatch):
    st = _session_state(messages=[], session_id="old")
    st.values["use_streaming"] = False
    st._chat_input_value = "hello"
    monkeypatch.setattr(chat_interface, "st", st)
    monkeypatch.setattr(
        chat_interface, "_handle_non_streaming_response", lambda *a, **k: (None, None, None)
    )

    chat_interface.display_chat_interface()

    assert st.session_state["session_id"] == "old"
    assert st.errors == ["Failed to get a response from the API. Please try again."]
    assert st.session_state["messages"] == [{"role": "user", "content": "hello"}]


# --- sidebar ---------------------------------------------------------------


def test_default_model_index_matches_settings_default():
    expected = sidebar.MODEL_OPTIONS.index("gpt-4o-mini")
    assert sidebar.get_default_model_index() == expected


def test_render_health_status_healthy(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "get_health", lambda: {"status": "ok", "version": "0.17.0"})

    sidebar._render_health_status()

    assert st.successes == ["Backend: ok (0.17.0)"]


def test_render_health_status_unavailable(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "get_health", lambda: None)

    sidebar._render_health_status()

    assert st.errors == ["Backend unavailable"]


def test_render_reset_chat(monkeypatch):
    st = _session_state(messages=[{"role": "user", "content": "x"}], session_id="s1")
    st.buttons["Reset Chat"] = True
    monkeypatch.setattr(sidebar, "st", st)

    sidebar._render_reset_chat()

    assert st.session_state["messages"] == []
    assert st.session_state["session_id"] is None
    assert st.reruns == 1


def test_render_session_history_empty(monkeypatch):
    st = FakeStreamlit()
    st.session_state["sessions"] = []
    monkeypatch.setattr(sidebar, "st", st)

    sidebar._render_session_history()

    assert any(c.fn == "caption" for c in st.calls)


@pytest.mark.parametrize(
    "session",
    [
        {"session_id": "s1", "message_count": 3, "preview": "Hi", "label": "Project"},
        {"session_id": "s1", "message_count": 3, "preview": "Hi"},
    ],
)
def test_render_session_history_builds_labels(monkeypatch, session):
    st = FakeStreamlit()
    st.session_state["sessions"] = [session]
    st.values["session_picker"] = "(current)"
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "list_sessions", lambda: [session])

    sidebar._render_session_history()

    selectbox_calls = [c for c in st.calls if c.fn == "selectbox"]
    assert len(selectbox_calls) == 1
    labels = selectbox_calls[0].kwargs["format_func"]
    assert labels(session["session_id"]).endswith("msgs)")


def test_render_session_history_load_session(monkeypatch):
    history = [{"role": "human", "content": "old q"}]
    st = _session_state(messages=[], session_id=None)
    st.session_state["sessions"] = [{"session_id": "s1", "message_count": 1, "preview": "q"}]
    st.values["session_picker"] = "s1"
    st.buttons["Load Session"] = True
    st.buttons["Delete"] = False
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "get_session_history", lambda sid: history)

    sidebar._render_session_history()

    assert st.session_state["session_id"] == "s1"
    assert st.session_state["messages"] == [{"role": "human", "content": "old q"}]
    assert st.reruns == 1


def test_render_collection_picker_all_collections(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    seen = []
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["default"])
    monkeypatch.setattr(sidebar, "list_documents", lambda collection: seen.append(collection) or [])

    active = sidebar._render_collection_picker()

    assert active is None
    assert st.session_state["active_collection"] is None
    assert seen == []  # docs_collection unset matches active None


def test_render_collection_picker_active_rename(monkeypatch):
    st = FakeStreamlit()
    st.values["collection_picker"] = "rentals"
    st.values["rename_collection"] = "rentals-v2"
    st.buttons["Rename"] = True
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["default", "rentals"])
    renamed = {"collection": "rentals-v2"}
    call_log = []

    def fake_rename(active, new):
        call_log.append((active, new))
        return renamed

    monkeypatch.setattr(sidebar, "rename_collection", fake_rename)
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_collection_picker()

    assert call_log == [("rentals", "rentals-v2")]
    assert st.reruns == 1  # renamed after success


def test_render_ops_metrics_unavailable(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "get_metrics", lambda: None)

    sidebar._render_ops_metrics()

    assert any(c.fn == "caption" for c in st.calls)


def test_render_ops_metrics_aggregates_latency(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    metrics = {
        "chat_requests": 2,
        "stream_requests": 1,
        "uploads": 1,
        "deletes": 1,
        "chat_errors": 1,
        "prompt_tokens_est": 100,
        "completion_tokens_est": 200,
        "latency_avg_seconds_chat": 1.5,
    }
    monkeypatch.setattr(sidebar, "get_metrics", lambda: metrics)
    monkeypatch.setattr(
        sidebar, "get_stats", lambda: {"documents": 3, "collections": 1, "sessions": 2}
    )
    monkeypatch.setattr(sidebar, "get_quota", lambda: {"unlimited": True})

    sidebar._render_ops_metrics()

    labels = [c.args[0] for c in st.calls if c.fn == "metric"]
    assert "Requests" in labels and "Errors" in labels
    assert "Daily token quota left (est.)" not in labels


def test_render_upload_document_single_file(monkeypatch):
    upload = type("F", (), {"name": "a.pdf", "type": "application/pdf"})()
    st = FakeStreamlit(uploads=[upload])
    st.session_state["active_collection"] = "rentals"
    st.buttons["Upload"] = True
    monkeypatch.setattr(sidebar, "st", st)
    seen = []

    def fake_upload(file, collection):
        seen.append(collection)
        return {"file_id": "abc"}

    monkeypatch.setattr(sidebar, "upload_document", fake_upload)
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["rentals"])
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_upload_document("rentals")

    assert seen == ["rentals"]
    assert st.successes == ["File 'a.pdf' uploaded successfully with ID abc."]


def test_render_document_list_delete(monkeypatch):
    st = FakeStreamlit()
    doc = {"filename": "a.pdf", "id": "doc-1", "collection": "default", "upload_timestamp": "t"}
    st.session_state["documents"] = [doc]
    st.buttons["Delete Selected Document"] = True
    monkeypatch.setattr(sidebar, "st", st)
    deleted = []
    monkeypatch.setattr(
        sidebar, "delete_document", lambda fid: deleted.append(fid) or {"deleted": True}
    )
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_document_list()

    assert deleted == ["doc-1"]
    assert st.successes == ["Document with ID doc-1 deleted successfully."]


def test_render_document_list_empty_is_noop(monkeypatch):
    st = FakeStreamlit()
    st.session_state["documents"] = []
    monkeypatch.setattr(sidebar, "st", st)

    sidebar._render_document_list()

    assert not any(c.fn in {"selectbox", "button"} for c in st.calls)


def test_render_session_export_download(monkeypatch):
    st = _session_state()
    st.session_state["export_session_id"] = "s1"
    st.session_state["export_text"] = "# transcript"
    monkeypatch.setattr(sidebar, "st", st)

    sidebar._render_session_export("s1")

    downloads = [c for c in st.calls if c.fn == "download_button"]
    assert len(downloads) == 1
    assert downloads[0].kwargs["file_name"] == "s1.md"


# --- streamlit_app entry point ----------------------------------------------


def test_streamlit_app_initializes_state():
    source = Path(__file__).resolve().parent.parent.joinpath(
        "app", "streamlit_app.py"
    ).read_text(encoding="utf-8")
    body = "\n".join(
        line
        for line in source.splitlines()
        if not line.startswith(("import streamlit", "from app."))
    )
    fake = FakeStreamlit()
    ns = {
        "st": fake,
        "display_sidebar": lambda: None,
        "display_chat_interface": lambda: None,
        "__name__": "app.streamlit_app",
    }
    exec(compile(body, "app/streamlit_app.py", "exec"), ns)

    assert fake.session_state["messages"] == []
    assert fake.session_state["session_id"] is None
    assert any(c.fn == "set_page_config" for c in fake.calls)
