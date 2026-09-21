import pytest
from app import api_utils
from tests.fake_streamlit import FakeStreamlit


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", json_error=None, stream_lines=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self._json_error = json_error
        self._stream_lines = stream_lines or []

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload

    def iter_lines(self, decode_unicode=False):
        yield from self._stream_lines


class FakeRequests:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def _call(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response

    def post(self, url, **kwargs):
        return self._call("post", url, **kwargs)

    def get(self, url, **kwargs):
        return self._call("get", url, **kwargs)

    def patch(self, url, **kwargs):
        return self._call("patch", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._call("delete", url, **kwargs)


class BoomRequests:
    def _boom(self, *args, **kwargs):
        raise ConnectionError("network down")

    post = get = patch = delete = _boom


@pytest.fixture
def fake_requests(monkeypatch):
    transport = FakeRequests(FakeResponse())
    monkeypatch.setattr(api_utils, "requests", transport)
    return transport


@pytest.fixture
def fake_st(monkeypatch):
    st = FakeStreamlit()
    monkeypatch.setattr(api_utils, "st", st)
    return st


def test_extract_error_detail_uses_fastapi_detail():
    response = FakeResponse(
        payload={"detail": "Document was not found."}, text='{"detail":"Document was not found."}'
    )

    assert api_utils.extract_error_detail(response) == "Document was not found."


def test_extract_error_detail_formats_validation_messages():
    response = FakeResponse(
        payload={"detail": [{"msg": "Input should be greater than 0"}, {"msg": "Field required"}]},
        text="validation failed",
    )

    assert api_utils.extract_error_detail(response) == (
        "Input should be greater than 0; Field required"
    )


def test_extract_error_detail_falls_back_to_response_text_for_non_json():
    response = FakeResponse(text="Gateway timeout", json_error=ValueError("not json"))

    assert api_utils.extract_error_detail(response) == "Gateway timeout"


def test_extract_error_detail_falls_back_for_non_dict_payload():
    response = FakeResponse(payload=["not", "a", "dict"], text="raw")

    assert api_utils.extract_error_detail(response) == "raw"


def test_show_api_error_records_error_with_detail(fake_st):
    response = FakeResponse(status_code=404, payload={"detail": "Unknown session"})

    api_utils.show_api_error("API request failed", response)

    assert fake_st.errors == ["API request failed. Status 404: Unknown session"]


def test_get_api_response_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"answer": "hi", "session_id": "s1"})

    result = api_utils.get_api_response("question", "s1", "gpt-4o-mini")

    assert result == {"answer": "hi", "session_id": "s1"}
    method, url, kwargs = fake_requests.calls[0]
    assert method == "post"
    assert url.endswith("/chat")
    assert kwargs["json"] == {"question": "question", "model": "gpt-4o-mini", "session_id": "s1"}


def test_get_api_response_includes_optional_flags(fake_requests):
    fake_requests.response = FakeResponse(payload={"answer": "hi"})

    api_utils.get_api_response(
        "q", None, "gpt-4o-mini", collections=["rentals"], expand_query=True, rerank=False
    )

    _, _, kwargs = fake_requests.calls[0]
    assert kwargs["json"] == {
        "question": "q",
        "model": "gpt-4o-mini",
        "collections": ["rentals"],
        "expand_query": True,
        "rerank": False,
    }


def test_get_api_response_includes_file_and_hybrid_flags(fake_requests):
    fake_requests.response = FakeResponse(payload={"answer": "hi"})

    api_utils.get_api_response(
        "q", None, "gpt-4o-mini", file_ids=[3, 7], use_hybrid=True
    )

    _, _, kwargs = fake_requests.calls[0]
    assert kwargs["json"]["file_ids"] == [3, 7]
    assert kwargs["json"]["use_hybrid"] is True


def test_get_api_response_error_shows_error_and_returns_none(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "boom"})

    result = api_utils.get_api_response("q", None, "gpt-4o-mini")

    assert result is None
    assert fake_st.errors == ["API request failed. Status 500: boom"]


def test_get_api_response_network_error_returns_none(monkeypatch, fake_st):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())

    result = api_utils.get_api_response("q", None, "gpt-4o-mini")

    assert result is None
    assert fake_st.errors == ["An error occurred: network down"]


def test_get_api_stream_response_success_streams_lines(fake_requests):
    fake_requests.response = FakeResponse(stream_lines=["data: a", "", "data: b"])

    lines = list(api_utils.get_api_stream_response("q", "s1", "gpt-4o-mini"))

    assert lines == ["data: a", "", "data: b"]
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/chat/stream")
    assert kwargs["stream"] is True


def test_get_api_stream_response_includes_optional_flags(fake_requests):
    fake_requests.response = FakeResponse(stream_lines=["data: a"])

    list(
        api_utils.get_api_stream_response(
            "q", None, "m", collections=["x"], expand_query=True, rerank=True
        )
    )

    _, _, kwargs = fake_requests.calls[0]
    assert kwargs["json"] == {
        "question": "q",
        "model": "m",
        "collections": ["x"],
        "expand_query": True,
        "rerank": True,
    }


def test_get_api_stream_response_includes_file_and_hybrid_flags(fake_requests):
    fake_requests.response = FakeResponse(stream_lines=["data: a"])

    list(api_utils.get_api_stream_response("q", None, "m", file_ids=[3, 7], use_hybrid=True))

    _, _, kwargs = fake_requests.calls[0]
    assert kwargs["json"]["file_ids"] == [3, 7]
    assert kwargs["json"]["use_hybrid"] is True


def test_get_api_stream_response_error_returns_none(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=503, payload={"detail": "unavailable"})

    result = api_utils.get_api_stream_response("q", None, "gpt-4o-mini")

    assert result is None
    assert fake_st.errors == ["API stream request failed. Status 503: unavailable"]


def test_get_api_stream_response_network_error_returns_none(monkeypatch, fake_st):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())

    result = api_utils.get_api_stream_response("q", None, "gpt-4o-mini")

    assert result is None
    assert "network down" in fake_st.errors[0]


def test_parse_sse_line_data_frame():
    assert api_utils.parse_sse_line("data: hello") == ("message", "hello")


def test_parse_sse_line_event_frame():
    assert api_utils.parse_sse_line("event: sources") == ("sources", None)


def test_parse_sse_line_ignores_blank_and_non_sse_lines():
    assert api_utils.parse_sse_line("") == (None, None)
    assert api_utils.parse_sse_line("random text") == (None, None)
    assert api_utils.parse_sse_line(None) == (None, None)


def test_upload_document_success(fake_requests):
    upload = type("File", (), {"name": "a.pdf", "type": "application/pdf"})()
    fake_requests.response = FakeResponse(payload={"file_id": "abc"})

    result = api_utils.upload_document(upload, "rentals")

    assert result == {"file_id": "abc"}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/upload-doc")


def test_upload_documents_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"uploaded": 2, "failed": 0})
    files = [
        type("File", (), {"name": f"f{i}.pdf", "type": "application/pdf"})()
        for i in range(2)
    ]

    result = api_utils.upload_documents(files, "rentals")

    assert result == {"uploaded": 2, "failed": 0}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/upload-docs")
    assert kwargs["params"] == {"collection": "rentals"}
    assert len(kwargs["files"]) == len(files)


def test_list_collections_returns_json(fake_requests):
    fake_requests.response = FakeResponse(payload=["default", "rentals"])

    assert api_utils.list_collections() == ["default", "rentals"]


def test_list_collections_error_returns_empty(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "x"})
    assert api_utils.list_collections() == []
    assert fake_st.errors


def test_list_collections_network_error_returns_empty(monkeypatch, fake_st):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_collections() == []


def test_rename_collection_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"collection": "new"})

    result = api_utils.rename_collection("old", "new")

    assert result == {"collection": "new"}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/collections/old")
    assert kwargs["json"] == {"collection": "new"}


def test_rename_collection_error_returns_none(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "nope"})
    assert api_utils.rename_collection("old", "new") is None
    assert fake_st.errors


def test_delete_collection_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"deleted": True})

    result = api_utils.delete_collection("rentals")

    assert result == {"deleted": True}
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/collections/rentals")


def test_list_documents_without_collection_param(fake_requests):
    fake_requests.response = FakeResponse(payload=[])

    api_utils.list_documents()

    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/list-docs")
    assert kwargs.get("params") is None


def test_list_documents_with_collection_param(fake_requests):
    fake_requests.response = FakeResponse(payload=[])

    api_utils.list_documents("rentals")

    _, url, kwargs = fake_requests.calls[0]
    assert kwargs["params"] == {"collection": "rentals"}


def test_list_documents_error_returns_empty(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_documents() == []
    assert fake_st.errors


def test_list_sessions_success(fake_requests):
    fake_requests.response = FakeResponse(payload=[{"session_id": "s1"}])
    assert api_utils.list_sessions() == [{"session_id": "s1"}]


def test_delete_session_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"deleted": True})
    result = api_utils.delete_session("s1")
    assert result == {"deleted": True}
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/sessions/s1")


def test_rename_session_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"label": "Jean"})
    result = api_utils.rename_session("s1", "Jean")
    assert result == {"label": "Jean"}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/s1")
    assert kwargs["json"] == {"label": "Jean"}


def test_export_session_returns_text_not_json(fake_requests):
    fake_requests.response = FakeResponse(text="# Convo")
    result = api_utils.export_session("s1")
    assert result == "# Convo"


def test_export_session_error_returns_none(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "no"})
    assert api_utils.export_session("s1") is None
    assert fake_st.errors


def test_submit_feedback_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"feedback_id": 7})
    result = api_utils.submit_feedback("s1", 1)
    assert result == {"feedback_id": 7}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/feedback")
    assert kwargs["json"] == {"session_id": "s1", "rating": 1}


def test_get_session_history_success(fake_requests):
    fake_requests.response = FakeResponse(payload=[{"role": "human", "content": "hi"}])
    result = api_utils.get_session_history("s1")
    assert result == [{"role": "human", "content": "hi"}]


def test_delete_document_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"deleted": True})
    result = api_utils.delete_document("doc-1")
    assert result == {"deleted": True}
    method, url, kwargs = fake_requests.calls[0]
    assert method == "post"
    assert url.endswith("/delete-doc")
    assert kwargs["json"] == {"file_id": "doc-1"}


@pytest.mark.parametrize(
    "status,patch_fn",
    [
        (200, "get_health"),
        (500, "get_health"),
        (200, "get_stats"),
        (500, "get_stats"),
        (200, "get_metrics"),
        (500, "get_metrics"),
        (200, "get_quota"),
        (500, "get_quota"),
    ],
)
def test_read_only_endpoints(fake_requests, status, patch_fn):
    ok = status == api_utils.HTTP_OK
    payload = {"ok": True} if ok else None
    fake_requests.response = FakeResponse(status_code=status, payload=payload)

    result = getattr(api_utils, patch_fn)()

    expected = {"ok": True} if ok else None
    assert result == expected


def test_upload_document_error_returns_none(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=413, payload={"detail": "too big"})
    upload = type("File", (), {"name": "a.pdf", "type": "application/pdf"})()
    assert api_utils.upload_document(upload, "rentals") is None
    assert fake_st.errors
    assert "Status 413: too big" in fake_st.errors[0]


def test_upload_documents_error_and_network_error(fake_requests, fake_st, monkeypatch):
    files = [type("File", (), {"name": "a.pdf", "type": "application/pdf"})()]
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "boom"})
    assert api_utils.upload_documents(files, "rentals") is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.upload_documents(files, "rentals") is None


def test_upload_document_network_error_returns_none(monkeypatch, fake_st):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    upload = type("File", (), {"name": "a.pdf", "type": "application/pdf"})()
    assert api_utils.upload_document(upload, "rentals") is None
    assert fake_st.errors


@pytest.mark.parametrize(
    "call,args",
    [
        (api_utils.rename_collection, ("old", "new")),
        (api_utils.delete_collection, ("rentals",)),
        (api_utils.rename_session, ("s1", "Jean")),
        (api_utils.submit_feedback, ("s1", 1)),
        (api_utils.delete_document, ("doc-1",)),
    ],
)
def test_mutating_endpoint_http_error(fake_requests, fake_st, call, args):
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "boom"})

    assert call(*args) is None
    assert fake_st.errors
    assert "Status 500: boom" in fake_st.errors[0]


@pytest.mark.parametrize(
    "call,args",
    [
        (api_utils.rename_collection, ("old", "new")),
        (api_utils.delete_collection, ("rentals",)),
        (api_utils.rename_session, ("s1", "Jean")),
        (api_utils.submit_feedback, ("s1", 1)),
        (api_utils.delete_document, ("doc-1",)),
        (api_utils.delete_session, ("s1",)),
    ],
)
def test_mutating_endpoint_network_error(monkeypatch, fake_st, call, args):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())

    assert call(*args) is None
    assert fake_st.errors
    assert "network down" in fake_st.errors[0]


def test_listing_endpoints_network_error(monkeypatch, fake_st):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())

    expected_none = [
        api_utils.get_session_history("s1"),
        api_utils.list_sessions(),
        api_utils.list_documents(),
        api_utils.list_collections(),
        api_utils.export_session("s1"),
    ]
    assert expected_none == [[], [], [], [], None]
    assert api_utils.upload_document(type("F", (), {"name": "a", "type": "text"})()) is None
    assert len(fake_st.errors) == len(expected_none) + 1


def test_listing_endpoints_http_error(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "boom"})

    assert api_utils.list_sessions() == []
    assert api_utils.get_session_history("s1") == []
    assert api_utils.delete_session("s1") is None
    assert len(fake_st.errors) == len(("list_sessions", "get_session_history", "delete_session"))


def test_read_only_endpoints_return_none_on_network_error(monkeypatch):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())

    for fn in ("get_health", "get_stats", "get_metrics", "get_quota"):
        assert getattr(api_utils, fn)() is None


def test_request_headers_without_api_key(monkeypatch):
    monkeypatch.setattr(api_utils.settings, "api_key", "")
    headers = api_utils._request_headers()
    assert headers == {"accept": "application/json", "Content-Type": "application/json"}
    assert "X-API-Key" not in headers


def test_request_headers_with_api_key_and_extras(monkeypatch):
    monkeypatch.setattr(api_utils.settings, "api_key", "secret-test-key")
    headers = api_utils._request_headers({"accept": "text/markdown", "Custom": "value"})
    assert headers["X-API-Key"] == "secret-test-key"
    assert headers["accept"] == "text/markdown"
    assert headers["Content-Type"] == "application/json"
    assert headers["Custom"] == "value"


def test_api_key_forwarded_in_client_requests(monkeypatch, fake_requests):
    monkeypatch.setattr(api_utils.settings, "api_key", "forward-me")
    fake_requests.response = FakeResponse(status_code=200, payload={"status": "ok"}, text="ok")

    fake_file = type("F", (), {"name": "doc.txt", "type": "text/plain"})()

    endpoints = [
        lambda: api_utils.get_api_response("q", "s1", "gpt-4o-mini"),
        lambda: api_utils.get_api_stream_response("q", "s1", "gpt-4o-mini"),
        lambda: api_utils.upload_documents([fake_file]),
        lambda: api_utils.upload_document(fake_file),
        api_utils.list_collections,
        lambda: api_utils.rename_collection("col", "new-col"),
        lambda: api_utils.delete_collection("col"),
        api_utils.list_documents,
        api_utils.list_sessions,
        lambda: api_utils.delete_session("s1"),
        lambda: api_utils.rename_session("s1", "lbl"),
        lambda: api_utils.export_session("s1"),
        lambda: api_utils.submit_feedback("s1", 1),
        lambda: api_utils.get_session_history("s1"),
        lambda: api_utils.delete_document("doc-1"),
        lambda: api_utils.get_document_details(1),
        lambda: api_utils.delete_documents([1]),
        lambda: api_utils.search_sessions("test"),
        api_utils.get_stats,
        api_utils.get_quota,
    ]

    for call_fn in endpoints:
        fake_requests.calls.clear()
        call_fn()
        assert len(fake_requests.calls) == 1
        _, _, kwargs = fake_requests.calls[0]
        assert "headers" in kwargs
        assert kwargs["headers"].get("X-API-Key") == "forward-me"


def test_get_document_details_success_and_failure(monkeypatch, fake_requests, fake_st):
    file_id = 42
    fake_payload = {"id": file_id, "filename": "lease.pdf", "chunk_count": 1, "chunks": []}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.get_document_details(file_id)
    assert result == fake_payload

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_document_details(file_id) is None
    assert any("not found" in err.lower() or "failed" in err.lower() for err in fake_st.errors)

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_document_details(file_id) is None


def test_delete_documents_success_and_failure(monkeypatch, fake_requests, fake_st):
    file_ids = [42, 43]
    fake_payload = {"deleted": 2, "failed": 0, "results": []}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.delete_documents(file_ids)
    assert result == fake_payload

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.delete_documents(file_ids) is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.delete_documents(file_ids) is None


def test_search_sessions_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_results = [{"session_id": "s1", "match_count": 1}]
    fake_requests.response = FakeResponse(
        status_code=200, payload={"query": "test", "results": fake_results}
    )
    assert api_utils.search_sessions("test") == fake_results

    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "empty"})
    assert api_utils.search_sessions("test") == []

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.search_sessions("test") == []


def test_get_config_success_and_failure(monkeypatch, fake_requests):
    fake_payload = {"app_name": "Test App", "default_model": "gpt-4o-mini"}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    assert api_utils.get_config() == fake_payload

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.get_config() is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_config() is None


