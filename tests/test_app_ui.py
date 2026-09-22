import importlib
import sys

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


@pytest.mark.parametrize("streaming", [True, False])
def test_display_chat_interface_forwards_doc_filters_and_hybrid(monkeypatch, streaming):
    st = _session_state(messages=[], session_id="old")
    st.values["use_streaming"] = streaming
    st._chat_input_value = "query"
    st.session_state["selected_doc_ids"] = [3, 7]
    st.session_state["use_hybrid"] = True
    monkeypatch.setattr(chat_interface, "st", st)

    handler = "_handle_streaming_response" if streaming else "_handle_non_streaming_response"
    other = "_handle_non_streaming_response" if streaming else "_handle_streaming_response"
    captured = {}

    def fake_handler(*args, **kwargs):
        captured["file_ids"] = args[6]
        captured["use_hybrid"] = args[7]
        return ("hi", [], "new-s1")

    monkeypatch.setattr(chat_interface, handler, fake_handler)
    monkeypatch.setattr(chat_interface, other, lambda *a, **k: None)

    chat_interface.display_chat_interface()

    assert captured == {"file_ids": [3, 7], "use_hybrid": True}


def test_handle_streaming_response_forwards_file_ids_and_hybrid(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    captured = {}

    def fake_stream(*args, **kwargs):
        captured["args"] = args
        return iter(["data: hi", ""])

    monkeypatch.setattr(chat_interface, "get_api_stream_response", fake_stream)

    chat_interface._handle_streaming_response(
        "q", "s1", "m", None, None, None, [3, 7], True, None, None
    )

    assert captured["args"] == (
        "q",
        "s1",
        "m",
        None,
        None,
        None,
        [3, 7],
        True,
        None,
        None,
    )


def test_handle_non_streaming_response_forwards_file_ids_and_hybrid(monkeypatch):
    st = _session_state()
    monkeypatch.setattr(chat_interface, "st", st)
    captured = {}

    def fake_response(*args, **kwargs):
        captured["args"] = args
        return {"answer": "hi", "sources": [], "session_id": "s1"}

    monkeypatch.setattr(chat_interface, "get_api_response", fake_response)

    chat_interface._handle_non_streaming_response(
        "q", "s1", "m", None, None, None, [3, 7], True, None, None
    )

    assert captured["args"] == ("q", "s1", "m", None, None, None, [3, 7], True, None, None)


# --- sidebar ---------------------------------------------------------------


def test_default_model_index_matches_settings_default():
    expected = sidebar.MODEL_OPTIONS.index("gpt-4o-mini")
    assert sidebar.get_default_model_index() == expected


def test_render_health_status_healthy(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "get_health", lambda: {"status": "ok", "version": "0.20.0"})

    sidebar._render_health_status()

    assert st.successes == ["Backend: ok (0.20.0)"]


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
    EXPECTED_SELECTBOX_COUNT = 2
    assert len(selectbox_calls) == EXPECTED_SELECTBOX_COUNT
    # The second one is the session picker
    session_picker_call = next(c for c in selectbox_calls if c.args[0] == "Open a session")
    labels = session_picker_call.kwargs["format_func"]
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


def test_render_retrieval_filters_with_documents(monkeypatch):
    st = FakeStreamlit()
    docs = [
        {"filename": "a.pdf", "id": 3},
        {"filename": "b.pdf", "id": 7},
    ]
    st.session_state["documents"] = docs
    monkeypatch.setattr(sidebar, "st", st)
    st.values["selected_doc_ids"] = [7]

    sidebar._render_retrieval_filters()

    multiselects = [c for c in st.calls if c.fn == "multiselect"]
    assert len(multiselects) == 1
    assert multiselects[0].kwargs["options"] == [3, 7]
    assert multiselects[0].kwargs["key"] == "selected_doc_ids"
    assert multiselects[0].kwargs["format_func"](7) == "b.pdf"
    checkboxes = [c for c in st.calls if c.fn == "checkbox"]
    EXPECTED_CHECKBOX_COUNT = 2
    assert len(checkboxes) == EXPECTED_CHECKBOX_COUNT
    assert checkboxes[0].kwargs["key"] == "use_hybrid"
    assert checkboxes[1].kwargs["key"] == "use_cross_encoder_rerank"


def test_render_retrieval_filters_without_documents_resets(monkeypatch):
    st = FakeStreamlit()
    st.session_state["documents"] = []
    st.session_state["selected_doc_ids"] = [3]
    monkeypatch.setattr(sidebar, "st", st)

    sidebar._render_retrieval_filters()

    assert st.session_state["selected_doc_ids"] == []
    assert not any(c.fn == "multiselect" for c in st.calls)


def test_render_collection_picker_resets_doc_filter_on_scope_change(monkeypatch):
    st = FakeStreamlit()
    st.values["collection_picker"] = "rentals"
    st.session_state["docs_collection"] = "old"
    st.session_state["selected_doc_ids"] = [3]
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["default", "rentals"])
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_collection_picker()

    assert st.session_state["selected_doc_ids"] == []


def test_render_session_export_download(monkeypatch):
    st = _session_state()
    st.session_state["export_session_id"] = "s1"
    st.session_state["export_text"] = "# transcript"
    monkeypatch.setattr(sidebar, "st", st)

    sidebar._render_session_export("s1")

    downloads = [c for c in st.calls if c.fn == "download_button"]
    assert len(downloads) == 1
    assert downloads[0].kwargs["file_name"] == "s1.md"


def test_render_session_history_refresh_and_actions(monkeypatch):
    st = _session_state()
    st.buttons["Refresh Sessions"] = True
    monkeypatch.setattr(sidebar, "st", st)
    called = []
    sessions_data = [{"session_id": "s1", "label": "First", "message_count": 2}]
    monkeypatch.setattr(
        sidebar, "list_sessions", lambda: (called.append("list"), sessions_data)[1]
    )

    sidebar._render_session_history()
    assert "list" in called
    assert st.session_state["sessions"] == sessions_data


def test_render_session_history_rename_flow(monkeypatch):
    st = _session_state()
    st.session_state["sessions"] = [{"session_id": "s1", "label": "Old", "message_count": 2}]
    st.values["session_picker"] = "s1"
    st.values["rename_session"] = "New Label"
    st.buttons["Rename"] = True
    monkeypatch.setattr(sidebar, "st", st)
    renamed = []
    monkeypatch.setattr(
        sidebar, "rename_session", lambda sid, lbl: (renamed.append((sid, lbl)), True)[1]
    )
    monkeypatch.setattr(
        sidebar,
        "list_sessions",
        lambda: [{"session_id": "s1", "label": "New Label", "message_count": 2}],
    )

    sidebar._render_session_history()
    assert renamed == [("s1", "New Label")]
    assert st.reruns == 1


def test_render_session_history_load_flow(monkeypatch):
    st = _session_state()
    st.session_state["sessions"] = [{"session_id": "s1", "label": "Old", "message_count": 1}]
    st.values["session_picker"] = "s1"
    st.buttons["Load Session"] = True
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(
        sidebar, "get_session_history", lambda sid: [{"role": "human", "content": "hello"}]
    )

    sidebar._render_session_history()
    assert st.session_state["session_id"] == "s1"
    assert st.session_state["messages"] == [{"role": "human", "content": "hello"}]
    assert st.reruns == 1


def test_render_session_history_delete_flow(monkeypatch):
    st = _session_state(session_id="s1", messages=[{"role": "human", "content": "hi"}])
    st.session_state["sessions"] = [{"session_id": "s1", "label": "Old", "message_count": 1}]
    st.session_state["export_text"] = "old text"
    st.session_state["export_session_id"] = "s1"
    st.values["session_picker"] = "s1"
    st.buttons["Delete"] = True
    monkeypatch.setattr(sidebar, "st", st)
    deleted = []
    monkeypatch.setattr(sidebar, "delete_session", lambda sid: (deleted.append(sid), True)[1])
    monkeypatch.setattr(sidebar, "list_sessions", lambda: [])

    sidebar._render_session_history()
    assert deleted == ["s1"]
    assert st.session_state["session_id"] is None
    assert st.session_state["messages"] == []
    assert "export_text" not in st.session_state
    assert st.reruns == 1


def test_render_session_export_prepare_button(monkeypatch):
    st = _session_state()
    st.buttons["Prepare Export"] = True
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "export_session", lambda sid: "# Export content")

    sidebar._render_session_export("s1")
    assert st.session_state["export_text"] == "# Export content"
    assert st.session_state["export_session_id"] == "s1"


def test_render_collection_picker_rename_and_delete(monkeypatch):
    # Test rename
    st = FakeStreamlit()
    st.session_state["collections"] = ["default", "clients-old"]
    st.values["collection_picker"] = "clients-old"
    st.values["rename_collection"] = "clients-new"
    st.buttons["Rename"] = True
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(
        sidebar, "rename_collection", lambda old, new: {"collection": new}
    )
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["default", "clients-new"])
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_collection_picker()
    assert st.session_state["active_collection"] == "clients-new"
    assert st.reruns == 1

    # Test delete
    st_del = FakeStreamlit()
    st_del.session_state["collections"] = ["default", "clients-old"]
    st_del.values["collection_picker"] = "clients-old"
    st_del.buttons["Delete"] = True
    monkeypatch.setattr(sidebar, "st", st_del)
    monkeypatch.setattr(sidebar, "delete_collection", lambda name: True)
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["default"])
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_collection_picker()
    assert st_del.session_state["active_collection"] is None
    assert st_del.reruns == 1


def test_render_upload_document_bulk_results(monkeypatch):
    st = FakeStreamlit()
    f1 = type("F", (), {"name": "doc1.txt"})()
    f2 = type("F", (), {"name": "doc2.txt"})()
    st.uploads = [f1, f2]
    st.buttons["Upload"] = True
    monkeypatch.setattr(sidebar, "st", st)
    bulk_result = {
        "uploaded": 1,
        "failed": 1,
        "results": [
            {"filename": "doc1.txt", "status": "ok"},
            {"filename": "doc2.txt", "status": "error", "detail": "corrupted file"},
        ],
    }
    monkeypatch.setattr(sidebar, "upload_documents", lambda files, target: bulk_result)
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["default"])
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_upload_document("default")
    assert any("Uploaded 1 of 2 files." in s for s in st.successes)
    assert any("doc2.txt: corrupted file" in e for e in st.errors)


def test_render_refresh_documents_button(monkeypatch):
    st = FakeStreamlit()
    st.buttons["Refresh Document List"] = True
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [{"id": 99, "filename": "x.pdf"}])

    sidebar._render_refresh_documents("default")
    assert st.session_state["documents"] == [{"id": 99, "filename": "x.pdf"}]


def test_render_document_list_delete_error(monkeypatch):
    st = FakeStreamlit()
    st.session_state["documents"] = [
        {"id": 10, "filename": "contract.pdf", "upload_timestamp": "2026-09-01"}
    ]
    st.values["Select a document to delete"] = 10
    st.buttons["Delete Selected Document"] = True
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "delete_document", lambda fid: None)

    sidebar._render_document_list()
    assert any("Failed to delete document with ID 10." in e for e in st.errors)


def test_render_ops_metrics_quota_and_latencies(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    metrics = {
        "chat_requests": 10,
        "stream_requests": 5,
        "uploads": 2,
        "deletes": 1,
        "chat_errors": 0,
        "upload_errors": 0,
        "prompt_tokens_est": 120,
        "completion_tokens_est": 80,
        "latency_avg_seconds_chat": 0.45,
        "latency_avg_seconds_search": 0.12,
    }
    monkeypatch.setattr(sidebar, "get_metrics", lambda: metrics)
    monkeypatch.setattr(
        sidebar, "get_stats", lambda: {"documents": 5, "collections": 2, "sessions": 3}
    )
    expected_remaining = 4500
    monkeypatch.setattr(
        sidebar, "get_quota", lambda: {"unlimited": False, "remaining": expected_remaining}
    )

    sidebar._render_ops_metrics()

    metric_calls = [c for c in st.calls if c.fn == "metric"]
    labels = [c.args[0] for c in metric_calls]
    assert "Daily token quota left (est.)" in labels
    assert any(
        c.args[1] == expected_remaining
        for c in metric_calls
        if c.args[0] == "Daily token quota left (est.)"
    )

    write_calls = [c for c in st.calls if c.fn == "write"]
    written_text = [c.args[0] for c in write_calls]
    assert any("chat: 0.45" in text for text in written_text)
    assert any("search: 0.12" in text for text in written_text)


def test_display_sidebar_complete(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "get_health", lambda: {"status": "ok", "version": "0.20.0"})
    monkeypatch.setattr(sidebar, "list_sessions", lambda: [])
    monkeypatch.setattr(sidebar, "list_collections", lambda: ["default"])
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])
    monkeypatch.setattr(sidebar, "get_metrics", lambda: {"chat_requests": 1})
    monkeypatch.setattr(sidebar, "get_stats", lambda: None)
    monkeypatch.setattr(sidebar, "get_quota", lambda: None)
    monkeypatch.setattr(sidebar, "list_feedback", lambda **kw: {"items": [], "total": 0})

    sidebar.display_sidebar()
    assert any(c.fn == "caption" for c in st.calls)


def test_render_session_history_search_filter(monkeypatch):
    st = _session_state()
    st.session_state["sessions"] = [
        {"session_id": "s1", "label": "Lease", "message_count": 2},
        {"session_id": "s2", "label": "Maintenance", "message_count": 1},
    ]
    st.values["session_search_query"] = "maintenance"
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "search_sessions", lambda q: [{"session_id": "s2"}])

    sidebar._render_session_history()
    picker_calls = [c for c in st.calls if c.fn == "selectbox" and c.args[0] == "Open a session"]
    assert len(picker_calls) == 1
    options = picker_calls[0].kwargs["options"]
    assert "(current)" in options
    assert "s2" in options
    assert "s1" not in options

    st_none = _session_state()
    st_none.session_state["sessions"] = [
        {"session_id": "s1", "label": "Lease", "message_count": 2},
    ]
    st_none.values["session_search_query"] = "nonexistent"
    monkeypatch.setattr(sidebar, "st", st_none)
    monkeypatch.setattr(sidebar, "search_sessions", lambda q: [])

    sidebar._render_session_history()
    captions = [c.args[0] for c in st_none.calls if c.fn == "caption"]
    assert "No matching conversations found." in captions


def test_render_document_inspector(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)

    st.session_state["documents"] = []
    sidebar._render_document_inspector()
    assert not any(c.fn == "expander" for c in st.calls)

    doc_id = 42
    st.session_state["documents"] = [{"id": doc_id, "filename": "test.pdf"}]
    st.values["inspect_doc_id"] = doc_id
    st.buttons["Load Details"] = True
    fake_details = {
        "id": doc_id,
        "filename": "test.pdf",
        "chunk_count": 1,
        "sha256": "1234567890abcdef123456",
        "chunks": [{"chunk_index": 0, "page": 1, "preview": "Hello chunk preview"}],
    }
    monkeypatch.setattr(sidebar, "get_document_details", lambda fid: fake_details)

    sidebar._render_document_inspector()
    assert st.session_state["inspect_doc_details"] == fake_details
    markdowns = [c.args[0] for c in st.calls if c.fn == "markdown"]
    assert any("Total chunks" in m for m in markdowns)
    texts = [c.args[0] for c in st.calls if c.fn == "text"]
    assert "Hello chunk preview" in texts


def test_render_document_list_bulk_delete(monkeypatch):
    st = FakeStreamlit()
    doc_ids = [10, 11]
    st.session_state["documents"] = [
        {"id": 10, "filename": "a.pdf", "upload_timestamp": "2026-09-01"},
        {"id": 11, "filename": "b.pdf", "upload_timestamp": "2026-09-01"},
    ]
    st.values["bulk_delete_mode"] = True
    st.values["bulk_delete_ids"] = doc_ids
    st.buttons["Delete Selected Documents"] = True
    monkeypatch.setattr(sidebar, "st", st)
    expected_deleted = 2
    monkeypatch.setattr(sidebar, "delete_documents", lambda fids: {"deleted": expected_deleted})
    monkeypatch.setattr(sidebar, "list_documents", lambda c: [])

    sidebar._render_document_list()
    assert any("Deleted 2 document(s)." in s for s in st.successes)
    assert st.reruns == 1

    st_fail = FakeStreamlit()
    st_fail.session_state["documents"] = [
        {"id": 10, "filename": "a.pdf", "upload_timestamp": "2026-09-01"}
    ]
    st_fail.values["bulk_delete_mode"] = True
    st_fail.values["bulk_delete_ids"] = [10]
    st_fail.buttons["Delete Selected Documents"] = True
    monkeypatch.setattr(sidebar, "st", st_fail)
    monkeypatch.setattr(sidebar, "delete_documents", lambda fids: None)

    sidebar._render_document_list()
    assert any("Failed to delete documents." in e for e in st_fail.errors)


# --- streamlit_app entry point ----------------------------------------------


def test_streamlit_app_initializes_state(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    sidebar_called = []
    chat_called = []
    monkeypatch.setattr(sidebar, "display_sidebar", lambda: sidebar_called.append(True))
    monkeypatch.setattr(
        chat_interface, "display_chat_interface", lambda: chat_called.append(True)
    )

    if "app.streamlit_app" in sys.modules:
        importlib.reload(sys.modules["app.streamlit_app"])
    else:
        importlib.import_module("app.streamlit_app")

    assert fake.session_state["messages"] == []
    assert fake.session_state["session_id"] is None
    assert any(c.fn == "set_page_config" for c in fake.calls)
    assert any(c.fn == "title" for c in fake.calls)
    assert sidebar_called == [True]
    assert chat_called == [True]


# --- config discovery & limit integration ----------------------------------


def test_init_config_fetches_and_caches(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    called = []

    fake_conf = {"supported_models": ["m1", "m2"], "default_model": "m2"}
    monkeypatch.setattr(sidebar, "get_config", lambda: called.append(1) or fake_conf)

    assert sidebar._init_config() == fake_conf
    assert st.session_state.config == fake_conf
    # Second call should use cache
    assert sidebar._init_config() == fake_conf
    assert len(called) == 1


def test_get_model_options_and_default_index():
    # Without config
    assert sidebar.get_model_options(None) == sidebar.MODEL_OPTIONS
    default_idx = sidebar.get_default_model_index()
    assert sidebar.MODEL_OPTIONS[default_idx] == "gpt-4o-mini"

    # With config
    conf = {"supported_models": ["custom-1", "custom-2"], "default_model": "custom-2"}
    opts = sidebar.get_model_options(conf)
    assert opts == ["custom-1", "custom-2"]
    assert sidebar.get_default_model_index(opts, conf) == 1

    # With unknown default model fallback
    conf_unknown = {"supported_models": ["a", "b"], "default_model": "c"}
    assert sidebar.get_default_model_index(["a", "b"], conf_unknown) == 0


def test_render_model_selector_uses_config(monkeypatch):
    st = FakeStreamlit()
    st.session_state.config = {
        "supported_models": ["model-a", "model-b"],
        "default_model": "model-b",
    }
    monkeypatch.setattr(sidebar, "st", st)
    sidebar._render_model_selector()

    call = next(c for c in st.calls if c.fn == "selectbox" and c.args[0] == "Select Model")
    assert call.kwargs["options"] == ["model-a", "model-b"]
    assert call.kwargs["index"] == 1


def test_render_upload_document_enforces_max_bulk_limit(monkeypatch):
    st = FakeStreamlit(
        uploads=[
            type("F", (), {"name": f"f{i}.txt", "read": lambda: b"x"})()
            for i in range(5)
        ],
        buttons={"Upload": True},
    )
    st.session_state.config = {
        "max_upload_size_bytes": 10485760,
        "max_bulk_upload_files": 3,
    }
    monkeypatch.setattr(sidebar, "st", st)
    upload_mock = []
    monkeypatch.setattr(sidebar, "upload_documents", lambda *a: upload_mock.append(a))

    sidebar._render_upload_document("default")

    assert upload_mock == []
    assert any("Cannot upload more than 3 files" in err for err in st.errors)


def test_display_sidebar_initializes_config(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "_render_health_status", lambda: None)
    monkeypatch.setattr(sidebar, "_render_reset_chat", lambda: None)
    monkeypatch.setattr(sidebar, "_render_session_history", lambda: None)
    monkeypatch.setattr(sidebar, "_render_model_selector", lambda: None)
    monkeypatch.setattr(sidebar, "_render_collection_picker", lambda: "default")
    monkeypatch.setattr(sidebar, "_render_upload_document", lambda c: None)
    monkeypatch.setattr(sidebar, "_render_refresh_documents", lambda c: None)
    monkeypatch.setattr(sidebar, "_render_document_inspector", lambda: None)
    monkeypatch.setattr(sidebar, "_render_retrieval_filters", lambda: None)
    monkeypatch.setattr(sidebar, "_render_document_list", lambda: None)
    monkeypatch.setattr(sidebar, "_render_feedback_review", lambda: None)
    monkeypatch.setattr(sidebar, "_render_ops_metrics", lambda: None)

    conf = {"version": "0.21.0"}
    monkeypatch.setattr(sidebar, "get_config", lambda: conf)

    sidebar.display_sidebar()
    assert st.session_state.config == conf


def test_render_session_history_bulk_delete_success(monkeypatch):
    sessions = [
        {"session_id": "s1", "label": "Session 1", "message_count": 2},
        {"session_id": "s2", "label": "Session 2", "message_count": 4},
    ]
    st = FakeStreamlit(
        values={"bulk_delete_sessions_mode": True, "bulk_delete_session_ids": ["s1"]},
        buttons={"Delete Selected Sessions": True},
    )
    st.session_state.sessions = list(sessions)
    st.session_state.session_id = "s1"
    st.session_state.messages = [{"role": "user", "content": "hello"}]
    st.session_state.export_session_id = "s1"
    st.session_state.export_text = "some export"
    monkeypatch.setattr(sidebar, "st", st)

    deleted_args = []
    monkeypatch.setattr(
        sidebar,
        "delete_sessions",
        lambda ids: deleted_args.append(ids) or {"deleted": len(ids), "failed": 0, "results": []},
    )
    monkeypatch.setattr(sidebar, "list_sessions", lambda: [sessions[1]])

    sidebar._render_session_history()

    assert deleted_args == [["s1"]]
    assert any("Deleted 1 session(s)." in s for s in st.successes)
    assert st.session_state.session_id is None
    assert st.session_state.messages == []
    assert "export_session_id" not in st.session_state
    assert st.reruns == 1


def test_render_session_history_bulk_delete_failure(monkeypatch):
    sessions = [{"session_id": "s1", "label": "Session 1", "message_count": 2}]
    st = FakeStreamlit(
        values={"bulk_delete_sessions_mode": True, "bulk_delete_session_ids": ["s1"]},
        buttons={"Delete Selected Sessions": True},
    )
    st.session_state.sessions = list(sessions)
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "delete_sessions", lambda ids: None)

    sidebar._render_session_history()

    assert any("Failed to delete sessions." in e for e in st.errors)


def test_get_export_formats():
    assert sidebar.get_export_formats(None) == ["markdown", "json", "csv"]
    conf = {"supported_export_formats": ["markdown", "json"]}
    assert sidebar.get_export_formats(conf) == ["markdown", "json"]


def test_render_session_export_json_and_csv(monkeypatch):
    # Test JSON export
    st_json = FakeStreamlit(
        values={"export_format_selector": "json"},
        buttons={"Prepare Export": True},
    )
    monkeypatch.setattr(sidebar, "st", st_json)
    called_args = []
    monkeypatch.setattr(
        sidebar,
        "export_session",
        lambda sid, format="markdown": called_args.append((sid, format)) or '{"session_id": "s1"}',
    )

    sidebar._render_session_export("s1")

    assert called_args == [("s1", "json")]
    assert st_json.session_state["export_text"] == '{"session_id": "s1"}'
    assert st_json.session_state["export_format"] == "json"
    download = next(c for c in st_json.calls if c.fn == "download_button")
    assert download.kwargs["file_name"] == "s1.json"
    assert download.kwargs["mime"] == "application/json"

    # Test CSV export
    st_csv = FakeStreamlit(
        values={"export_format_selector": "csv"},
        buttons={"Prepare Export": True},
    )
    monkeypatch.setattr(sidebar, "st", st_csv)
    called_csv = []
    monkeypatch.setattr(
        sidebar,
        "export_session",
        lambda sid, format="markdown": called_csv.append((sid, format)) or "role,content\n",
    )

    sidebar._render_session_export("s1")

    assert called_csv == [("s1", "csv")]
    assert st_csv.session_state["export_format"] == "csv"
    download_csv = next(c for c in st_csv.calls if c.fn == "download_button")
    assert download_csv.kwargs["file_name"] == "s1.csv"
    assert download_csv.kwargs["mime"] == "text/csv"


# --- feedback review panel -------------------------------------------------


def test_render_feedback_review_empty(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(
        sidebar, "list_feedback", lambda rating=None, limit=20: {"items": [], "total": 0}
    )

    sidebar._render_feedback_review()

    captions = [c.args[0] for c in st.calls if c.fn == "caption"]
    assert any("No feedback recorded yet." in c for c in captions)


def test_render_feedback_review_items_and_ratings(monkeypatch):
    items = [
        {
            "id": 1,
            "session_id": "sess-alpha-12345",
            "rating": 1,
            "comment": "Great answer!",
            "created_at": "2026-09-21 10:00:00",
        },
        {
            "id": 2,
            "session_id": "sess-beta-67890",
            "rating": -1,
            "comment": None,
            "created_at": "2026-09-21 10:05:00",
        },
    ]
    st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(
        sidebar, "list_feedback", lambda rating=None, limit=20: {"items": items, "total": 2}
    )

    sidebar._render_feedback_review()

    markdowns = [c.args[0] for c in st.calls if c.fn == "markdown"]
    assert any("👍 sess-alp" in m and "Great answer!" in m for m in markdowns)
    assert any("👎 sess-bet" in m and "*(no comment)*" in m for m in markdowns)


def test_render_feedback_review_rating_filters(monkeypatch):
    calls = []

    def fake_list(rating=None, limit=20):
        calls.append(rating)
        return {"items": [], "total": 0}

    monkeypatch.setattr(sidebar, "list_feedback", fake_list)

    # Filter by positive
    st_pos = FakeStreamlit(values={"feedback_rating_filter": "Positive (👍)"})
    monkeypatch.setattr(sidebar, "st", st_pos)
    sidebar._render_feedback_review()
    assert calls[-1] == 1

    # Filter by negative
    st_neg = FakeStreamlit(values={"feedback_rating_filter": "Negative (👎)"})
    monkeypatch.setattr(sidebar, "st", st_neg)
    sidebar._render_feedback_review()
    assert calls[-1] == -1


def test_render_feedback_review_open_session(monkeypatch):
    items = [
        {
            "id": 10,
            "session_id": "session-xyz",
            "rating": -1,
            "comment": "Inaccurate info",
            "created_at": "2026-09-21 10:10:00",
        }
    ]
    st = FakeStreamlit(
        buttons={"open_fb_10": True},
    )
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(
        sidebar, "list_feedback", lambda rating=None, limit=20: {"items": items, "total": 1}
    )
    history = [
        {"role": "user", "content": "What is the pet policy?"},
        {"role": "assistant", "content": "No pets allowed."},
    ]
    monkeypatch.setattr(sidebar, "get_session_history", lambda sid: history)

    sidebar._render_feedback_review()

    assert st.session_state.session_id == "session-xyz"
    assert st.session_state.messages == history
    assert st.reruns == 1


def test_render_feedback_review_refresh(monkeypatch):
    st = FakeStreamlit(
        buttons={"refresh_feedback_btn": True},
    )
    monkeypatch.setattr(sidebar, "st", st)
    called = []
    monkeypatch.setattr(
        sidebar,
        "list_feedback",
        lambda rating=None, limit=20: called.append(1) or {"items": [], "total": 0},
    )

    sidebar._render_feedback_review()

    assert len(called) >= 1
