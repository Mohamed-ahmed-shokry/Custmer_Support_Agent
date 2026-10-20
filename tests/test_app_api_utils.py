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


def test_get_collections_details_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_payload = [
        {
            "collection": "default",
            "document_count": 3,
            "chunk_count": 9,
            "file_formats": {"pdf": 3},
            "earliest_upload": "2026-09-01 00:00:00",
            "latest_upload": "2026-09-02 00:00:00",
        }
    ]
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.get_collections_details()
    assert result == fake_payload
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/collections/details")

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.get_collections_details() == []

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_collections_details() == []


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


def test_list_sessions_with_filters(fake_requests):
    fake_requests.response = FakeResponse(payload=[{"session_id": "s1", "status": "resolved"}])
    result = api_utils.list_sessions(status="resolved", tag="urgent")
    assert result == [{"session_id": "s1", "status": "resolved"}]
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions")
    assert kwargs["params"] == {"status": "resolved", "tag": "urgent"}


def test_rename_session_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"label": "Jean"})
    result = api_utils.rename_session("s1", "Jean")
    assert result == {"label": "Jean"}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/s1")
    assert kwargs["json"] == {"label": "Jean"}


def test_update_session_success(fake_requests):
    fake_requests.response = FakeResponse(payload={"session_id": "s1", "status": "resolved"})
    result = api_utils.update_session("s1", status="resolved", tags=["billing", "urgent"])
    assert result == {"session_id": "s1", "status": "resolved"}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/s1")
    assert kwargs["json"] == {"status": "resolved", "tags": ["billing", "urgent"]}


def test_update_session_error(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "failed"})
    result = api_utils.update_session("s1", status="bad")
    assert result is None
    assert fake_st.errors


def test_export_session_returns_text_not_json(fake_requests):
    fake_requests.response = FakeResponse(text="# Convo")
    result = api_utils.export_session("s1")
    assert result == "# Convo"


def test_export_session_error_returns_none(fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "no"})
    assert api_utils.export_session("s1") is None
    assert fake_st.errors


def test_export_session_passes_format(fake_requests):
    fake_requests.response = FakeResponse(text='{"session_id": "s1"}')
    result = api_utils.export_session("s1", format="json")
    assert result == '{"session_id": "s1"}'
    _, _, kwargs = fake_requests.calls[0]
    assert kwargs["params"] == {"format": "json"}



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
        lambda: api_utils.rechunk_document(1),
        lambda: api_utils.rechunk_collection("legal"),
        lambda: api_utils.get_collection_analytics("legal"),
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


def test_rechunk_document_success_and_failure(monkeypatch, fake_requests, fake_st):
    file_id = 42
    fake_payload = {
        "id": file_id,
        "filename": "lease.pdf",
        "chunk_count": 2,
        "chunking_strategy": "semantic",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "chunks": [],
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.rechunk_document(
        file_id, chunking_strategy="semantic", chunk_size=500, chunk_overlap=50
    )
    assert result == fake_payload
    assert len(fake_requests.calls) == 1
    _, _, kwargs = fake_requests.calls[0]
    assert kwargs.get("json") == {
        "chunking_strategy": "semantic",
        "chunk_size": 500,
        "chunk_overlap": 50,
    }

    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "source not found"})
    assert api_utils.rechunk_document(file_id) is None
    assert any("failed" in err.lower() or "source" in err.lower() for err in fake_st.errors)

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.rechunk_document(file_id) is None


def test_rechunk_collection_success_and_failure(monkeypatch, fake_requests, fake_st):
    collection = "legal"
    fake_payload = {
        "collection": collection,
        "strategy": "semantic",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "total_documents": 2,
        "rechunked_documents": 2,
        "skipped_documents": 0,
        "failed_documents": 0,
        "total_chunks_created": 8,
        "items": [],
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.rechunk_collection(
        collection, chunking_strategy="semantic", chunk_size=500, chunk_overlap=50
    )
    assert result == fake_payload
    expected_calls = 1
    assert len(fake_requests.calls) == expected_calls
    _, _, kwargs = fake_requests.calls[0]
    assert kwargs.get("json") == {
        "chunking_strategy": "semantic",
        "chunk_size": 500,
        "chunk_overlap": 50,
    }

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.rechunk_collection(collection) is None
    assert any("failed" in err.lower() or "not found" in err.lower() for err in fake_st.errors)

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.rechunk_collection(collection) is None


def test_get_collection_analytics_success_and_failure(monkeypatch, fake_requests, fake_st):
    collection = "legal"
    fake_payload = {
        "collection": collection,
        "total_documents": 2,
        "total_chunks": 10,
        "avg_chunk_length": 450.0,
        "min_chunk_length": 100,
        "max_chunk_length": 800,
        "median_chunk_length": 420.0,
        "strategy_distribution": {"recursive": 10},
        "length_histogram": {"200-500": 10},
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.get_collection_analytics(collection)
    assert result == fake_payload

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_collection_analytics(collection) is None
    assert any("failed" in err.lower() or "not found" in err.lower() for err in fake_st.errors)

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_collection_analytics(collection) is None


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


def test_delete_sessions_success_and_failure(monkeypatch, fake_requests, fake_st):
    session_ids = ["s1", "s2"]
    fake_payload = {"deleted": 2, "failed": 0, "results": []}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.delete_sessions(session_ids)
    assert result == fake_payload

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.delete_sessions(session_ids) is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.delete_sessions(session_ids) is None


def test_submit_feedback_with_comment_passes_payload(fake_requests):
    fake_requests.response = FakeResponse(payload={"feedback_id": 9})
    result = api_utils.submit_feedback("s1", -1, comment="Needs improvement")
    assert result == {"feedback_id": 9}
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/feedback")
    assert kwargs["json"] == {
        "session_id": "s1",
        "rating": -1,
        "comment": "Needs improvement",
    }


def test_list_feedback_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_payload = {"items": [{"id": 1}], "total": 1, "limit": 50, "offset": 0}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.list_feedback(rating=1, session_id="s1")
    assert result == fake_payload
    _, _, kwargs = fake_requests.calls[0]
    assert kwargs["params"] == {
        "limit": 50,
        "offset": 0,
        "rating": 1,
        "session_id": "s1",
    }

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.list_feedback() is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_feedback() is None


def test_get_session_feedback_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_payload = [{"id": 1, "session_id": "s1", "rating": 1}]
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.get_session_feedback("s1")
    assert result == fake_payload

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_session_feedback("s1") is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_session_feedback("s1") is None


def test_get_feedback_analytics_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_payload = {
        "total_feedback": 5,
        "positive_feedback": 4,
        "negative_feedback": 1,
        "satisfaction_rate": 80.0,
        "total_comments": 2,
        "comment_rate": 40.0,
        "recent_comments": [],
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.get_feedback_analytics(recent_comments_limit=5)
    assert result == fake_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/feedback/analytics")
    assert kwargs["params"] == {"recent_comments_limit": 5}

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.get_feedback_analytics() is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_feedback_analytics() is None


def test_update_session_with_summary_and_resolution_notes(fake_requests):
    fake_payload = {
        "session_id": "s1",
        "status": "resolved",
        "summary": "Resolved billing issue.",
        "resolution_notes": "Applied credit.",
    }
    fake_requests.response = FakeResponse(payload=fake_payload)
    result = api_utils.update_session(
        "s1",
        status="resolved",
        summary="Resolved billing issue.",
        resolution_notes="Applied credit.",
    )
    assert result == fake_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/s1")
    assert kwargs["json"]["summary"] == "Resolved billing issue."
    assert kwargs["json"]["resolution_notes"] == "Applied credit."


def test_summarize_session_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_payload = {
        "session_id": "s1",
        "summary": "Summary text",
        "key_points": ["Point 1"],
        "sentiment": "positive",
        "suggested_tags": ["tag1"],
        "saved": True,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.summarize_session("s1", model="gpt-4o-mini", save_summary=True)
    assert result == fake_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/s1/summarize")
    assert kwargs["json"] == {"model": "gpt-4o-mini", "save_summary": True}

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.summarize_session("s1") is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.summarize_session("s1") is None


def test_get_support_triage_analytics_success_and_failure(monkeypatch, fake_requests, fake_st):
    expected_total = 8
    fake_payload = {
        "total_sessions": expected_total,
        "active_count": 3,
        "resolved_count": 4,
        "escalated_count": 1,
        "closed_count": 0,
        "resolution_rate": 50.0,
        "escalation_rate": 12.5,
        "avg_turns_per_session": 3.0,
        "top_tags": [{"tag": "lease", "count": 4}],
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)
    result = api_utils.get_support_triage_analytics()
    assert result == fake_payload
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/sessions/triage-analytics")

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "server error"})
    assert api_utils.get_support_triage_analytics() is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_support_triage_analytics() is None


def test_list_webhooks_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_list = [{"id": 1, "url": "https://example.com/alerts"}]
    fake_requests.response = FakeResponse(status_code=200, payload=fake_list)

    res = api_utils.list_webhooks(active_only=True, event="session.escalated")
    assert res == fake_list
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/webhooks")
    assert kwargs["params"] == {"active_only": True, "event": "session.escalated"}

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.list_webhooks() == []
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_webhooks() == []


def test_create_webhook_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_created = {"id": 1, "url": "https://example.com/hook", "events": "*"}
    fake_requests.response = FakeResponse(status_code=201, payload=fake_created)

    res = api_utils.create_webhook(url="https://example.com/hook", secret="whsec_123")
    assert res == fake_created
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/webhooks")
    assert kwargs["json"]["url"] == "https://example.com/hook"
    assert kwargs["json"]["secret"] == "whsec_123"

    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "bad url"})
    assert api_utils.create_webhook(url="invalid") is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.create_webhook(url="https://example.com/hook") is None


def test_update_webhook_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_updated = {"id": 1, "url": "https://example.com/hook2"}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_updated)

    res = api_utils.update_webhook(
        webhook_id=1,
        url="https://example.com/hook2",
        reset_failures=True,
    )
    assert res == fake_updated
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/webhooks/1")
    assert kwargs["json"]["url"] == "https://example.com/hook2"
    assert kwargs["json"]["reset_failures"] is True

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "missing"})
    assert api_utils.update_webhook(webhook_id=999) is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.update_webhook(webhook_id=1) is None


def test_delete_webhook_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_requests.response = FakeResponse(status_code=200, payload={"message": "deleted"})
    assert api_utils.delete_webhook(1) is True
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/webhooks/1")

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "missing"})
    assert api_utils.delete_webhook(999) is False
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.delete_webhook(1) is False


def test_ping_webhook_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_ping = {"webhook_id": 1, "success": True}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_ping)

    res = api_utils.ping_webhook(1)
    assert res == fake_ping
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/webhooks/1/ping")

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "missing"})
    assert api_utils.ping_webhook(999) is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.ping_webhook(1) is None


def test_list_webhook_deliveries_success_and_failure(monkeypatch, fake_requests, fake_st):
    fake_logs = {"items": [{"id": 1, "success": True}], "total": 1}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_logs)

    res = api_utils.list_webhook_deliveries(webhook_id=1, limit=10, offset=0)
    assert res == fake_logs
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/webhooks/deliveries")
    assert kwargs["params"] == {"webhook_id": 1, "limit": 10, "offset": 0}

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.list_webhook_deliveries() == {"items": [], "total": 0}
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_webhook_deliveries() == {"items": [], "total": 0}


def test_create_macro_success_and_failure(monkeypatch, fake_requests, fake_st):
    target_id = 1
    created = {"id": target_id, "title": "Test Macro", "shortcut": "/test"}
    fake_requests.response = FakeResponse(status_code=201, payload=created)

    res = api_utils.create_macro(
        title="Test Macro",
        shortcut="/test",
        category="General",
        content="Hello {name}",
        tags=["faq"],
        status_action="resolved",
    )
    assert res == created
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/macros")
    assert kwargs["json"]["shortcut"] == "/test"

    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "Shortcut exists"})
    assert api_utils.create_macro("T", "/test", "G", "C") is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.create_macro("T", "/test", "G", "C") is None


def test_list_macros_success_and_failure(monkeypatch, fake_requests, fake_st):
    target_id = 1
    macro_list = [{"id": target_id, "title": "Test"}]
    fake_requests.response = FakeResponse(status_code=200, payload=macro_list)

    res = api_utils.list_macros(category="General", tag="faq", search="test")
    assert res == macro_list
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/macros")
    assert kwargs["params"] == {"category": "General", "tag": "faq", "search": "test"}

    # Fallback for non-list payload
    fake_requests.response = FakeResponse(status_code=200, payload={"not": "a list"})
    assert api_utils.list_macros() == []

    # API error
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.list_macros() == []
    assert fake_st.errors

    # Network error
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_macros() == []


def test_list_macro_categories_success_and_failure(monkeypatch, fake_requests, fake_st):
    categories = ["General", "Maintenance", "Billing"]
    fake_requests.response = FakeResponse(status_code=200, payload={"categories": categories})

    res = api_utils.list_macro_categories()
    assert res == categories
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/macros/categories")

    # Non-dict payload fallback
    fake_requests.response = FakeResponse(status_code=200, payload=["raw", "list"])
    assert api_utils.list_macro_categories() == []

    # API error
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.list_macro_categories() == []
    assert fake_st.errors

    # Network error
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_macro_categories() == []


def test_get_macro_success_and_failure(monkeypatch, fake_requests, fake_st):
    target_id = 1
    macro_data = {"id": target_id, "title": "Sample"}
    fake_requests.response = FakeResponse(status_code=200, payload=macro_data)

    res = api_utils.get_macro(target_id)
    assert res == macro_data
    _, url, _ = fake_requests.calls[0]
    assert url.endswith(f"/macros/{target_id}")

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_macro(target_id) is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_macro(target_id) is None


def test_update_macro_success_and_failure(monkeypatch, fake_requests, fake_st):
    target_id = 1
    updated = {"id": target_id, "title": "Updated Title"}
    fake_requests.response = FakeResponse(status_code=200, payload=updated)

    res = api_utils.update_macro(
        macro_id=target_id,
        title="Updated Title",
        shortcut="/updated",
        category="Ops",
        content="New content",
        tags=["new"],
        status_action="escalated",
    )
    assert res == updated
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith(f"/macros/{target_id}")
    assert kwargs["json"]["title"] == "Updated Title"

    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "bad request"})
    assert api_utils.update_macro(macro_id=target_id) is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.update_macro(macro_id=target_id) is None


def test_delete_macro_success_and_failure(monkeypatch, fake_requests, fake_st):
    target_id = 1
    fake_requests.response = FakeResponse(status_code=200, payload={"message": "deleted"})
    assert api_utils.delete_macro(target_id) is True
    _, url, _ = fake_requests.calls[0]
    assert url.endswith(f"/macros/{target_id}")

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.delete_macro(target_id) is False
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.delete_macro(target_id) is False


def test_render_macro_success_and_failure(monkeypatch, fake_requests, fake_st):
    target_id = 1
    rendered_payload = {
        "macro_id": target_id,
        "rendered_content": "Hello Alice",
        "unresolved_variables": [],
        "status_action": None,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=rendered_payload)

    res = api_utils.render_macro(
        macro_id=target_id,
        variables={"name": "Alice"},
        fallback_defaults=True,
    )
    assert res == rendered_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith(f"/macros/{target_id}/render")
    assert kwargs["json"]["variables"] == {"name": "Alice"}

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.render_macro(target_id) is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.render_macro(target_id) is None


def test_apply_macro_to_session_success_and_failure(monkeypatch, fake_requests, fake_st):
    target_id = 1
    apply_payload = {
        "session_id": "sess-abc",
        "macro_id": target_id,
        "macro_title": "Resolve Ticket",
        "rendered_content": "Issue resolved.",
        "applied_status": "resolved",
        "applied_tags": ["resolved"],
        "unresolved_variables": [],
        "created_at": "2026-10-01T00:00:00Z",
    }
    fake_requests.response = FakeResponse(status_code=200, payload=apply_payload)

    res = api_utils.apply_macro_to_session(
        session_id="sess-abc",
        macro_id=target_id,
        variables={"customer_name": "Bob"},
        update_status=True,
        append_tags=True,
    )
    assert res == apply_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/sess-abc/apply-macro")
    assert kwargs["json"]["macro_id"] == target_id
    assert kwargs["json"]["variables"] == {"customer_name": "Bob"}

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.apply_macro_to_session(session_id="sess-abc", macro_id=target_id) is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.apply_macro_to_session(session_id="sess-abc", macro_id=target_id) is None


def test_suggest_macros(fake_requests, fake_st, monkeypatch):
    suggest_payload = {
        "query": "leak in unit 4",
        "detected_intent": "maintenance_emergency",
        "intent_confidence": 0.9,
        "extracted_variables": {"unit_id": "Unit 4"},
        "suggestions": [],
        "total_matches": 0,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=suggest_payload)

    res = api_utils.suggest_macros(
        query="leak in unit 4",
        session_id="sess-xyz",
        category="Maintenance",
        top_k=5,
        min_score=0.4,
    )
    assert res == suggest_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/macros/suggest")
    assert kwargs["json"]["query"] == "leak in unit 4"
    assert kwargs["json"]["session_id"] == "sess-xyz"
    assert kwargs["json"]["category"] == "Maintenance"

    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "bad request"})
    assert api_utils.suggest_macros("query") is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.suggest_macros("query") is None


def test_get_session_macro_suggestions(fake_requests, fake_st, monkeypatch):
    sess_payload = {
        "session_id": "sess-xyz",
        "latest_query": "water leaking",
        "detected_intent": "maintenance_emergency",
        "extracted_variables": {"session_id": "sess-xyz"},
        "suggestions": [],
        "total_matches": 0,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=sess_payload)

    res = api_utils.get_session_macro_suggestions(
        session_id="sess-xyz",
        top_k=4,
        min_score=0.35,
        category="Maintenance",
    )
    assert res == sess_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/sess-xyz/macro-suggestions")
    assert kwargs["params"]["category"] == "Maintenance"

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_session_macro_suggestions("sess-missing") is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_session_macro_suggestions("sess-missing") is None


def test_list_sla_policies(fake_requests, fake_st, monkeypatch):
    fake_items = [{"id": 1, "name": "Emergency", "priority": "urgent"}]
    fake_requests.response = FakeResponse(
        status_code=200, payload={"items": fake_items, "total": 1}
    )

    res = api_utils.list_sla_policies(priority="urgent", active_only=True)
    expected_count = 1
    assert len(res) == expected_count
    assert res[0]["name"] == "Emergency"
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sla/policies")
    assert kwargs["params"]["priority"] == "urgent"
    assert kwargs["params"]["active_only"] is True

    # 400 failure
    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "bad request"})
    assert api_utils.list_sla_policies() == []
    assert fake_st.errors

    # Network failure
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_sla_policies() == []


def test_create_sla_policy(fake_requests, fake_st, monkeypatch):
    fake_payload = {
        "id": 1,
        "name": "Emergency",
        "priority": "urgent",
        "category": "maintenance",
        "response_time_minutes": 15,
        "resolution_time_minutes": 120,
        "is_active": True,
    }
    fake_requests.response = FakeResponse(status_code=201, payload=fake_payload)

    res = api_utils.create_sla_policy(
        name="Emergency",
        priority="urgent",
        category="maintenance",
        response_time_minutes=15,
        resolution_time_minutes=120,
    )
    assert res == fake_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sla/policies")
    assert kwargs["json"]["priority"] == "urgent"

    # 422 failure
    fake_requests.response = FakeResponse(
        status_code=422, payload={"detail": "invalid parameters"}
    )
    assert (
        api_utils.create_sla_policy(
            name="Emergency",
            priority="urgent",
        )
        is None
    )
    assert fake_st.errors

    # Network failure
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert (
        api_utils.create_sla_policy(
            name="Emergency",
            priority="urgent",
        )
        is None
    )


def test_get_and_delete_sla_policy(fake_requests, fake_st, monkeypatch):
    fake_payload = {"id": 1, "name": "Emergency", "priority": "urgent"}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)

    # Get
    res = api_utils.get_sla_policy(1)
    assert res == fake_payload
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/sla/policies/1")

    # Get 404
    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_sla_policy(999) is None
    assert fake_st.errors

    # Get Boom
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_sla_policy(1) is None

    # Reset transport for delete
    fake_requests.calls.clear()
    monkeypatch.setattr(api_utils, "requests", fake_requests)
    fake_requests.response = FakeResponse(status_code=200, payload={"message": "deleted"})
    assert api_utils.delete_sla_policy(1) is True

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.delete_sla_policy(999) is False

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.delete_sla_policy(1) is False


def test_update_sla_policy(fake_requests, fake_st, monkeypatch):
    fake_payload = {"id": 1, "name": "Updated Emergency", "priority": "urgent"}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)

    res = api_utils.update_sla_policy(1, name="Updated Emergency", response_time_minutes=20)
    assert res == fake_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sla/policies/1")
    expected_resp = 20
    assert kwargs["json"]["response_time_minutes"] == expected_resp

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.update_sla_policy(999, name="Test") is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.update_sla_policy(1, name="Test") is None


def test_get_session_sla_status(fake_requests, fake_st, monkeypatch):
    fake_payload = {
        "session_id": "sess-1",
        "priority": "urgent",
        "breach_status": "healthy",
        "minutes_to_response_deadline": 14.5,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)

    res = api_utils.get_session_sla_status("sess-1")
    assert res == fake_payload
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/sessions/sess-1/sla")

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_session_sla_status("missing") is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_session_sla_status("sess-1") is None


def test_evaluate_sla_alerts(fake_requests, fake_st, monkeypatch):
    fake_payload = {
        "total_sessions_checked": 3,
        "alerts_triggered": 1,
        "alerts": [{"session_id": "sess-1", "event": "sla.breached"}],
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)

    res = api_utils.evaluate_sla_alerts(approaching_threshold_minutes=25)
    assert res == fake_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sla/evaluate-alerts")
    expected_thresh = 25
    assert kwargs["json"]["approaching_threshold_minutes"] == expected_thresh

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.evaluate_sla_alerts() is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.evaluate_sla_alerts() is None


def test_get_sla_compliance_analytics(fake_requests, fake_st, monkeypatch):
    fake_payload = {
        "total_tracked_sessions": 5,
        "compliance_rate": 80.0,
        "breached_sessions": 1,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)

    res = api_utils.get_sla_compliance_analytics()
    assert res == fake_payload
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/sla/analytics")

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "error"})
    assert api_utils.get_sla_compliance_analytics() is None
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_sla_compliance_analytics() is None


def test_update_session_with_priority(fake_requests):
    fake_payload = {"session_id": "s1", "priority": "urgent"}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)

    res = api_utils.update_session("s1", priority="urgent")
    assert res == fake_payload
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/s1")
    assert kwargs["json"]["priority"] == "urgent"


# =====================================================================
# Support Agents, Session Assignment & Business Hours Client Tests
# =====================================================================


def test_list_support_agents_client(fake_requests, fake_st, monkeypatch):
    fake_payload = {
        "items": [
            {
                "id": "agent_sarah",
                "name": "Sarah Connor",
                "email": "sarah@example.com",
                "tier": "tier_1",
                "department": "general_leasing",
                "is_active": True,
            }
        ],
        "total": 1,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_payload)

    agents = api_utils.list_support_agents(tier="tier_1", active_only=True)
    assert len(agents) == 1
    assert agents[0]["id"] == "agent_sarah"
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/agents")
    assert kwargs["params"]["tier"] == "tier_1"

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.list_support_agents() == []
    assert fake_st.errors

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_support_agents() == []


def test_create_and_get_support_agent_client(fake_requests, fake_st, monkeypatch):
    fake_agent = {
        "id": "agent_david",
        "name": "David Miller",
        "email": "david@example.com",
        "tier": "tier_1",
        "department": "maintenance",
        "is_active": True,
    }
    fake_requests.response = FakeResponse(status_code=201, payload=fake_agent)

    created = api_utils.create_support_agent(
        agent_id="agent_david",
        name="David Miller",
        email="david@example.com",
        tier="tier_1",
        department="maintenance",
        is_active=True,
    )
    assert created == fake_agent
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/agents")
    assert kwargs["json"]["id"] == "agent_david"

    # Get agent
    fake_requests.response = FakeResponse(status_code=200, payload=fake_agent)
    got = api_utils.get_support_agent("agent_david")
    assert got == fake_agent

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.get_support_agent("missing") is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_support_agent("err") is None


def test_update_and_delete_support_agent_client(fake_requests, fake_st, monkeypatch):
    fake_agent = {"id": "agent_sarah", "tier": "tier_2", "is_active": False}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_agent)

    updated = api_utils.update_support_agent("agent_sarah", tier="tier_2", is_active=False)
    assert updated == fake_agent
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/agents/agent_sarah")
    assert kwargs["json"]["tier"] == "tier_2"

    # Delete agent
    fake_requests.response = FakeResponse(status_code=200, payload={"message": "deleted"})
    assert api_utils.delete_support_agent("agent_sarah") is True

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.delete_support_agent("agent_sarah") is False

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.delete_support_agent("agent_sarah") is False


def test_get_agent_workload_analytics_client(fake_requests, fake_st, monkeypatch):
    fake_workload = {
        "agents": [],
        "total_active_sessions": 2,
        "unassigned_active_sessions": 1,
        "tier_distribution": {"tier_1": 2},
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_workload)

    res = api_utils.get_agent_workload_analytics()
    assert res == fake_workload
    _, url, _ = fake_requests.calls[0]
    assert url.endswith("/agents/workload")

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.get_agent_workload_analytics() is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_agent_workload_analytics() is None


def test_assign_and_auto_assign_session_client(fake_requests, fake_st, monkeypatch):
    fake_session = {
        "session_id": "sess-assign",
        "assigned_agent": "agent_sarah",
        "escalation_tier": "tier_1",
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_session)

    res_manual = api_utils.assign_session("sess-assign", agent_id="agent_sarah", tier="tier_1")
    assert res_manual == fake_session
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/sessions/sess-assign/assign")
    assert kwargs["json"]["agent_id"] == "agent_sarah"

    res_auto = api_utils.auto_assign_session("sess-assign", strategy="least_busy")
    assert res_auto == fake_session

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.assign_session("s_err") is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.auto_assign_session("s_boom") is None


def test_get_session_assignment_history_and_business_hours_client(
    fake_requests, fake_st, monkeypatch
):
    fake_hist = {
        "session_id": "sess-h",
        "items": [{"id": 1, "session_id": "sess-h", "new_agent": "agent_sarah"}],
        "total": 1,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_hist)

    items = api_utils.get_session_assignment_history("sess-h")
    assert len(items) == 1
    assert items[0]["new_agent"] == "agent_sarah"

    fake_biz = {
        "is_open": True,
        "current_time": "2026-10-12T10:00:00",
        "next_open_at": None,
        "timezone": "UTC",
        "schedule": {"monday": "09:00 - 18:00"},
        "day_name": "Monday",
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_biz)

    biz_status = api_utils.get_business_hours_status()
    assert biz_status == fake_biz

    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "fail"})
    assert api_utils.get_business_hours_status() is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_business_hours_status() is None


def test_submit_csat_feedback_client(fake_requests, fake_st, monkeypatch):
    fake_payload = {"message": "CSAT feedback recorded.", "feedback_id": 77}
    fake_requests.response = FakeResponse(status_code=201, payload=fake_payload)

    res = api_utils.submit_csat_feedback(
        session_id="sess-csat",
        score=5,
        resolution_satisfaction=4,
        agent_helpfulness=5,
        response_speed=5,
        comment="Superb!",
        assigned_agent="agent_alice",
        escalation_tier="tier_1",
    )
    assert res == fake_payload
    method, url, kwargs = fake_requests.calls[0]
    assert method == "post"
    assert url.endswith("/feedback/csat")
    assert kwargs["json"]["score"] == 5  # noqa: PLR2004
    assert kwargs["json"]["comment"] == "Superb!"

    fake_requests.response = FakeResponse(status_code=404, payload={"detail": "not found"})
    assert api_utils.submit_csat_feedback("missing", score=5) is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.submit_csat_feedback("boom", score=5) is None


def test_feedback_review_queue_and_update_client(fake_requests, fake_st, monkeypatch):
    fake_queue = {
        "items": [{"id": 10, "session_id": "s-10", "score": 2}],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }
    fake_requests.response = FakeResponse(status_code=200, payload=fake_queue)

    q_res = api_utils.list_feedback_review_queue(
        review_status="pending_review",
        assigned_agent="agent_bob",
        escalation_tier="tier_2",
        min_score=1,
        max_score=2,
    )
    assert q_res == fake_queue
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/feedback/queue")
    assert kwargs["params"]["review_status"] == "pending_review"
    assert kwargs["params"]["max_score"] == 2  # noqa: PLR2004

    fake_updated = {"id": 10, "review_status": "reviewed", "reviewed_by": "qa_lead"}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_updated)
    u_res = api_utils.update_feedback_review(
        10,
        review_status="reviewed",
        reviewer_notes="Done",
        reviewed_by="qa_lead",
    )
    assert u_res == fake_updated

    # Error branches
    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "bad"})
    assert api_utils.list_feedback_review_queue()["total"] == 0
    assert api_utils.update_feedback_review(10, "reviewed") is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_feedback_review_queue()["total"] == 0
    assert api_utils.update_feedback_review(10, "reviewed") is None


def test_csat_summary_and_scorecards_client(fake_requests, fake_st, monkeypatch):
    fake_sum = {"total_responses": 12, "avg_csat_score": 4.4}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_sum)
    assert api_utils.get_csat_summary() == fake_sum

    fake_cards = {"scorecards": [{"agent_id": "agent_alice"}], "total_agents": 1}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_cards)
    assert api_utils.get_agent_scorecards() == fake_cards

    # Error branches
    fake_requests.response = FakeResponse(status_code=500, payload={"detail": "err"})
    assert api_utils.get_csat_summary() is None
    assert api_utils.get_agent_scorecards()["total_agents"] == 0

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_csat_summary() is None
    assert api_utils.get_agent_scorecards()["total_agents"] == 0


def test_knowledge_gap_client_helpers(fake_requests, fake_st, monkeypatch):
    # 1. record_knowledge_gap
    fake_gap = {"id": 1, "query": "Elevator booking", "status": "open"}
    fake_requests.response = FakeResponse(status_code=201, payload=fake_gap)
    res = api_utils.record_knowledge_gap("Elevator booking", category="policy")
    assert res == fake_gap

    fake_requests.response = FakeResponse(status_code=400, payload={"detail": "bad"})
    assert api_utils.record_knowledge_gap("Elevator booking") is None

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.record_knowledge_gap("Elevator booking") is None
    monkeypatch.setattr(api_utils, "requests", fake_requests)

    # 2. list_knowledge_gaps
    fake_gaps_resp = {"items": [fake_gap], "total": 1}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_gaps_resp)
    items, tot = api_utils.list_knowledge_gaps(status="open", category="policy", priority="high")
    assert len(items) == 1
    assert tot == 1

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_knowledge_gaps() == ([], 0)

    # 3. scan_knowledge_gaps
    fake_scan = {"scanned_sessions_count": 10, "gaps_created": 2}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_scan)
    assert api_utils.scan_knowledge_gaps(limit=20) == fake_scan

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.scan_knowledge_gaps() is None

    # 4. update_knowledge_gap & delete_knowledge_gap
    fake_updated = {**fake_gap, "status": "resolved"}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_updated)
    assert api_utils.update_knowledge_gap(1, status="resolved") == fake_updated

    fake_requests.response = FakeResponse(status_code=200, payload={"status": "deleted"})
    assert api_utils.delete_knowledge_gap(1) is True

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.update_knowledge_gap(1, status="resolved") is None
    assert api_utils.delete_knowledge_gap(1) is False


def test_knowledge_article_client_helpers(fake_requests, fake_st):
    # 1. create_knowledge_article & draft_article_from_session
    fake_art = {"id": 10, "title": "Elevator Guide", "status": "draft"}
    fake_requests.response = FakeResponse(status_code=201, payload=fake_art)
    assert api_utils.create_knowledge_article("Elevator Guide", "# Guide") == fake_art
    assert api_utils.draft_article_from_session("sess-1", author="agent_alice") == fake_art

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.create_knowledge_article("Elevator Guide", "# Guide") is None
    assert api_utils.draft_article_from_session("sess-1") is None

    # 2. list_knowledge_articles & get_knowledge_article
    fake_arts_resp = {"items": [fake_art], "total": 1}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_arts_resp)
    art_items, art_tot = api_utils.list_knowledge_articles(search="Elevator")
    assert len(art_items) == 1
    assert art_tot == 1

    fake_requests.response = FakeResponse(status_code=200, payload=fake_art)
    assert api_utils.get_knowledge_article(10) == fake_art

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.list_knowledge_articles() == ([], 0)
    assert api_utils.get_knowledge_article(10) is None

    # 3. update_knowledge_article & delete_knowledge_article
    fake_requests.response = FakeResponse(status_code=200, payload=fake_art)
    assert api_utils.update_knowledge_article(10, title="New Title") == fake_art
    assert api_utils.delete_knowledge_article(10) is True

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.update_knowledge_article(10, title="New Title") is None
    assert api_utils.delete_knowledge_article(10) is False

    # 4. publish_knowledge_article & get_knowledge_analytics
    fake_pub = {"article": fake_art, "file_id": 50, "linked_gap_resolved": True}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_pub)
    assert api_utils.publish_knowledge_article(10, collection="default") == fake_pub

    fake_an = {"total_gaps": 5, "gap_resolution_rate": 80.0}
    fake_requests.response = FakeResponse(status_code=200, payload=fake_an)
    assert api_utils.get_knowledge_analytics() == fake_an

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.publish_knowledge_article(10) is None
    assert api_utils.get_knowledge_analytics() is None


def test_property_unit_client_helpers(fake_requests, fake_st, monkeypatch):
    """Test unit CRUD client helpers."""
    # 1. list_units
    mock_units = {"items": [{"id": "unit_101", "unit_number": "101"}], "total": 1}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_units)
    res_list = api_utils.list_units(property_name="Sunset", search="101")
    assert res_list == mock_units

    # Error response
    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_units() is None

    # Exception
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_units() is None
    monkeypatch.setattr(api_utils, "requests", fake_requests)

    # 2. get_unit
    mock_unit = {"unit": {"id": "unit_101", "unit_number": "101"}}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_unit)
    assert api_utils.get_unit("unit_101") == mock_unit

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_unit("unit_101") is None

    # 3. create_unit
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_CREATED, payload=mock_unit)
    assert api_utils.create_unit({"id": "unit_101"}) == mock_unit

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.create_unit({"id": "unit_101"}) is None

    # 4. update_unit
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_unit)
    assert api_utils.update_unit("unit_101", {"monthly_rent": 1500.0}) == mock_unit

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.update_unit("unit_101", {"monthly_rent": 1500.0}) is None

    # 5. delete_unit
    del_payload = {"status": "deleted"}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=del_payload)
    assert api_utils.delete_unit("unit_101") is True

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.delete_unit("unit_101") is False

    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.delete_unit("unit_101") is False


def test_tenant_and_session_linking_client_helpers(fake_requests, fake_st, monkeypatch):
    """Test tenant CRUD, session linking, and context client helpers."""
    # 1. list_tenants
    mock_tenants = {"items": [{"id": "tenant_1", "first_name": "Sarah"}], "total": 1}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_tenants)
    res_list = api_utils.list_tenants(unit_id="unit_101", status="active", search="Sarah")
    assert res_list == mock_tenants

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_tenants() is None

    # 2. get_tenant
    mock_tenant = {"tenant": {"id": "tenant_1", "first_name": "Sarah"}}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_tenant)
    assert api_utils.get_tenant("tenant_1") == mock_tenant

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_tenant("tenant_1") is None

    # 3. create_tenant
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_CREATED, payload=mock_tenant)
    assert api_utils.create_tenant({"id": "tenant_1"}) == mock_tenant

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.create_tenant({"id": "tenant_1"}) is None

    # 4. update_tenant
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_tenant)
    assert api_utils.update_tenant("tenant_1", {"notes": "VIP"}) == mock_tenant

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.update_tenant("tenant_1", {"notes": "VIP"}) is None

    # 5. delete_tenant
    fake_del_resp = {"status": "deleted"}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=fake_del_resp)
    assert api_utils.delete_tenant("tenant_1") is True

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.delete_tenant("tenant_1") is False

    # 6. link_session_tenant
    mock_link = {"session_id": "s1", "tenant_id": "tenant_1", "unit_id": "unit_101"}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_link)
    assert api_utils.link_session_tenant("s1", tenant_id="tenant_1") == mock_link

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.link_session_tenant("s1", tenant_id="invalid") is None

    # 7. get_session_tenant_context
    mock_ctx = {"session_id": "s1", "tenant": mock_tenant["tenant"], "unit": None}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_ctx)
    assert api_utils.get_session_tenant_context("s1") == mock_ctx

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_session_tenant_context("s1") is None

    # 8. get_tenant_support_history
    mock_hist = {"tenant": mock_tenant["tenant"], "total_sessions": 1, "sessions": []}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_hist)
    assert api_utils.get_tenant_support_history("tenant_1") == mock_hist

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_tenant_support_history("tenant_1") is None

    # BoomRequests check
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.get_tenant_support_history("tenant_1") is None


def test_work_order_list_and_metrics_helpers(fake_requests, fake_st, monkeypatch):
    """Test work orders list, metrics, and unit/tenant queries."""
    mock_wo = {
        "id": "wo_101",
        "unit_id": "unit_101",
        "title": "Leaking sink",
        "category": "plumbing",
        "priority": "medium",
        "status": "submitted",
    }
    mock_list = {"items": [mock_wo], "total": 1, "limit": 50, "offset": 0}
    mock_metrics = {
        "total_work_orders": 3,
        "open_work_orders": 2,
        "emergency_work_orders": 0,
        "by_status": {"submitted": 1},
    }

    # 1. list_work_orders
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_list)
    res_list = api_utils.list_work_orders(
        unit_id="unit_101",
        tenant_id="tenant_1",
        status="submitted",
        priority="medium",
        category="plumbing",
        search="sink",
    )
    assert res_list == mock_list
    _, _, kwargs = fake_requests.calls[0]
    assert kwargs["params"]["unit_id"] == "unit_101"
    assert kwargs["params"]["tenant_id"] == "tenant_1"
    assert kwargs["params"]["status"] == "submitted"
    assert kwargs["params"]["priority"] == "medium"
    assert kwargs["params"]["category"] == "plumbing"
    assert kwargs["params"]["search"] == "sink"

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_work_orders() is None
    assert fake_st.errors

    # 2. get_work_order
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"work_order": mock_wo}
    )
    assert api_utils.get_work_order("wo_101") == {"work_order": mock_wo}

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_work_order("wo_101") is None

    # 3. get_work_order_metrics
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_metrics
    )
    assert api_utils.get_work_order_metrics() == mock_metrics

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_work_order_metrics() is None

    # 4. get_unit_work_orders
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_list)
    assert api_utils.get_unit_work_orders("unit_101", open_only=True) == mock_list

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_unit_work_orders("unit_101") is None

    # 5. get_tenant_work_orders
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_list)
    assert api_utils.get_tenant_work_orders("tenant_1", open_only=True) == mock_list

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_tenant_work_orders("tenant_1") is None

    # 6. BoomRequests check
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_work_orders() is None
    assert api_utils.get_work_order("wo_101") is None
    assert api_utils.get_work_order_metrics() is None
    assert api_utils.get_unit_work_orders("unit_101") is None
    assert api_utils.get_tenant_work_orders("tenant_1") is None


def test_work_order_crud_and_session_helpers(fake_requests, monkeypatch):
    """Test create, update, delete, and session conversion helpers."""
    mock_wo = {
        "id": "wo_101",
        "unit_id": "unit_101",
        "title": "Leaking sink",
        "category": "plumbing",
        "priority": "medium",
        "status": "submitted",
    }

    # 1. create_work_order
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"work_order": mock_wo}
    )
    assert api_utils.create_work_order(mock_wo) == {"work_order": mock_wo}

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.create_work_order(mock_wo) is None

    # 2. update_work_order
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"work_order": mock_wo}
    )
    assert api_utils.update_work_order("wo_101", {"status": "in_progress"}) == {
        "work_order": mock_wo
    }

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.update_work_order("wo_101", {"status": "in_progress"}) is None

    # 3. delete_work_order
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK)
    assert api_utils.delete_work_order("wo_101") is True

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.delete_work_order("wo_101") is False

    # 4. create_work_order_from_session
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"work_order": mock_wo}
    )
    assert api_utils.create_work_order_from_session("sess_1", mock_wo) == {
        "work_order": mock_wo
    }

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.create_work_order_from_session("sess_1", mock_wo) is None

    # 5. BoomRequests check
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.create_work_order(mock_wo) is None
    assert api_utils.update_work_order("wo_101", {}) is None
    assert api_utils.delete_work_order("wo_101") is False
    assert api_utils.create_work_order_from_session("sess_1", {}) is None


def test_billing_api_utils_helpers(fake_requests, fake_st, monkeypatch):  # noqa: PLR0915
    """Test client helpers for billing transactions, ledger, and payment operations."""
    mock_tx = {
        "id": "tx_test_1",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "amount": 1450.0,
        "transaction_type": "rent",
        "status": "posted",
        "description": "October rent",
    }
    mock_list = {"items": [mock_tx], "total": 1, "limit": 50, "offset": 0}
    mock_metrics = {"total_transactions": 5, "total_billed": 5000.0, "total_collected": 3500.0}
    mock_ledger = {
        "tenant_id": "tenant_1",
        "current_balance": 0.0,
        "recent_transactions": [mock_tx],
    }
    mock_pay_resp = {"transaction": mock_tx, "amount_paid": 1450.0, "new_balance": 0.0}

    # 1. list_billing_transactions
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_list)
    res_list = api_utils.list_billing_transactions(
        tenant_id="tenant_1", unit_id="unit_101", transaction_type="rent", status="posted"
    )
    assert res_list == mock_list

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_billing_transactions() is None
    assert fake_st.errors

    # 2. get_billing_metrics
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_metrics)
    assert api_utils.get_billing_metrics() == mock_metrics

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_billing_metrics() is None

    # 3. get_billing_transaction
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"transaction": mock_tx}
    )
    assert api_utils.get_billing_transaction("tx_test_1") == {"transaction": mock_tx}

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_billing_transaction("tx_test_1") is None

    # 4. create_billing_transaction
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"transaction": mock_tx}
    )
    assert api_utils.create_billing_transaction(mock_tx) == {"transaction": mock_tx}

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.create_billing_transaction(mock_tx) is None

    # 5. update_billing_transaction
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"transaction": mock_tx}
    )
    assert (
        api_utils.update_billing_transaction("tx_test_1", {"status": "paid"})
        == {"transaction": mock_tx}
    )

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.update_billing_transaction("tx_test_1", {"status": "paid"}) is None

    # 6. delete_billing_transaction
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK)
    assert api_utils.delete_billing_transaction("tx_test_1") is True

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.delete_billing_transaction("tx_test_1") is False

    # 7. record_tenant_payment
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_CREATED, payload=mock_pay_resp)
    assert api_utils.record_tenant_payment("tenant_1", {"amount": 1450.0}) == mock_pay_resp

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.record_tenant_payment("tenant_1", {"amount": 1450.0}) is None

    # 8. get_tenant_ledger
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=mock_ledger)
    assert api_utils.get_tenant_ledger("tenant_1") == mock_ledger

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_tenant_ledger("tenant_1") is None

    # 9. record_session_payment
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_CREATED, payload=mock_pay_resp)
    assert api_utils.record_session_payment("sess_1", {"amount": 1450.0}) == mock_pay_resp

    fake_requests.response = FakeResponse(status_code=400)
    assert api_utils.record_session_payment("sess_1", {"amount": 1450.0}) is None

    # 10. BoomRequests exception handling
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_billing_transactions() is None
    assert api_utils.get_billing_metrics() is None
    assert api_utils.get_billing_transaction("tx_1") is None
    assert api_utils.create_billing_transaction({}) is None
    assert api_utils.update_billing_transaction("tx_1", {}) is None
    assert api_utils.delete_billing_transaction("tx_1") is False
    assert api_utils.record_tenant_payment("tenant_1", {}) is None
    assert api_utils.get_tenant_ledger("tenant_1") is None
    assert api_utils.record_session_payment("sess_1", {}) is None


def test_lease_renewals_client_helpers(fake_requests, fake_st, monkeypatch):  # noqa: PLR0915
    """Test all lease renewal and document client API helpers in app/api_utils.py."""
    mock_lr = {
        "id": "lr_test_101",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "proposed_rent": 1650.0,
        "term_months": 12,
        "status": "offered",
    }
    mock_list_resp = {"items": [mock_lr], "total": 1, "limit": 50, "offset": 0}
    mock_metrics_resp = {"total_renewals": 3, "renewal_rate": 75.0}
    mock_pub_resp = {"renewal_id": "lr_test_101", "indexed_in_chroma": True}

    # 1. list_lease_renewals
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_list_resp
    )
    res = api_utils.list_lease_renewals(tenant_id="tenant_1", status="offered")
    assert res == mock_list_resp
    _, url, kwargs = fake_requests.calls[0]
    assert url.endswith("/lease-renewals")
    assert kwargs["params"]["tenant_id"] == "tenant_1"

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_lease_renewals() is None

    # 2. get_lease_renewal
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"renewal": mock_lr}
    )
    assert api_utils.get_lease_renewal("lr_test_101") == {"renewal": mock_lr}

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_lease_renewal("lr_missing") is None

    # 3. get_lease_renewal_metrics
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_metrics_resp
    )
    assert api_utils.get_lease_renewal_metrics() == mock_metrics_resp

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_lease_renewal_metrics() is None

    # 4. create_lease_renewal
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"renewal": mock_lr}
    )
    assert api_utils.create_lease_renewal(mock_lr) == {"renewal": mock_lr}

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.create_lease_renewal(mock_lr) is None

    # 5. update_lease_renewal
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"renewal": mock_lr}
    )
    assert (
        api_utils.update_lease_renewal("lr_test_101", {"status": "accepted"})
        == {"renewal": mock_lr}
    )

    fake_requests.response = FakeResponse(status_code=404)
    assert (
        api_utils.update_lease_renewal("lr_test_101", {"status": "accepted"})
        is None
    )

    # 6. delete_lease_renewal
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK)
    assert api_utils.delete_lease_renewal("lr_test_101") is True

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.delete_lease_renewal("lr_test_101") is False

    # 7. sign_lease_renewal
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"renewal": mock_lr}
    )
    assert (
        api_utils.sign_lease_renewal("lr_test_101", {"signature_name": "Test Signer"})
        == {"renewal": mock_lr}
    )

    fake_requests.response = FakeResponse(status_code=422)
    assert (
        api_utils.sign_lease_renewal("lr_test_101", {"signature_name": "Test Signer"})
        is None
    )

    # 8. publish_lease_renewal_document
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_pub_resp
    )
    assert (
        api_utils.publish_lease_renewal_document("lr_test_101", {})
        == mock_pub_resp
    )

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.publish_lease_renewal_document("lr_test_101", {}) is None

    # 9. create_session_lease_renewal
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"renewal": mock_lr}
    )
    assert (
        api_utils.create_session_lease_renewal("sess_101", mock_lr)
        == {"renewal": mock_lr}
    )

    fake_requests.response = FakeResponse(status_code=400)
    assert api_utils.create_session_lease_renewal("sess_101", mock_lr) is None

    # 10. get_tenant_lease_renewals
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_list_resp
    )
    assert api_utils.get_tenant_lease_renewals("tenant_1") == mock_list_resp

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_tenant_lease_renewals("tenant_1") is None

    # 11. Exception handling via BoomRequests
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_lease_renewals() is None
    assert api_utils.get_lease_renewal("lr_1") is None
    assert api_utils.get_lease_renewal_metrics() is None
    assert api_utils.create_lease_renewal({}) is None
    assert api_utils.update_lease_renewal("lr_1", {}) is None
    assert api_utils.delete_lease_renewal("lr_1") is False
    assert api_utils.sign_lease_renewal("lr_1", {}) is None
    assert api_utils.publish_lease_renewal_document("lr_1", {}) is None
    assert api_utils.create_session_lease_renewal("sess_1", {}) is None
    assert api_utils.get_tenant_lease_renewals("tenant_1") is None


def test_inspection_api_utils_crud(fake_requests):
    mock_insp = {
        "inspection_id": "insp_test_101",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "inspection_type": "move_out",
        "status": "scheduled",
        "total_estimated_deductions": 0.0,
    }
    mock_list_resp = {"items": [mock_insp], "total": 1, "limit": 50, "offset": 0}

    # 1. create_inspection
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"inspection": mock_insp}
    )
    assert api_utils.create_inspection(mock_insp) == {"inspection": mock_insp}
    method, url, kwargs = fake_requests.calls[-1]
    assert method == "post"
    assert url.endswith("/inspections")
    assert kwargs["json"] == mock_insp

    fake_requests.response = FakeResponse(status_code=400)
    assert api_utils.create_inspection(mock_insp) is None

    # 2. list_inspections
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_list_resp
    )
    assert api_utils.list_inspections({"status": "scheduled", "empty": ""}) == mock_list_resp
    method, url, kwargs = fake_requests.calls[-1]
    assert method == "get"
    assert url.endswith("/inspections")
    assert kwargs["params"] == {"status": "scheduled"}

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.list_inspections() is None

    # 3. get_inspection
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"inspection": mock_insp}
    )
    assert api_utils.get_inspection("insp_test_101") == {"inspection": mock_insp}
    method, url, _ = fake_requests.calls[-1]
    assert method == "get"
    assert url.endswith("/inspections/insp_test_101")

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_inspection("insp_test_101") is None

    # 4. update_inspection
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"inspection": mock_insp}
    )
    assert api_utils.update_inspection("insp_test_101", {"status": "in_progress"}) == {
        "inspection": mock_insp
    }
    method, url, kwargs = fake_requests.calls[-1]
    assert method == "patch"
    assert url.endswith("/inspections/insp_test_101")
    assert kwargs["json"] == {"status": "in_progress"}

    fake_requests.response = FakeResponse(status_code=422)
    assert api_utils.update_inspection("insp_test_101", {"status": "in_progress"}) is None

    # 5. delete_inspection
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload={"ok": True})
    assert api_utils.delete_inspection("insp_test_101") is True
    method, url, _ = fake_requests.calls[-1]
    assert method == "delete"
    assert url.endswith("/inspections/insp_test_101")

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.delete_inspection("insp_test_101") is False


def test_inspection_api_utils_actions(fake_requests):
    mock_insp = {
        "inspection_id": "insp_test_101",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "inspection_type": "move_out",
        "status": "scheduled",
    }
    mock_pub_resp = {
        "status": "indexed",
        "inspection_id": "insp_test_101",
        "chunks_indexed": 3,
        "collection": "default",
    }

    # 6. complete_inspection
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"inspection": mock_insp}
    )
    assert api_utils.complete_inspection("insp_test_101") == {"inspection": mock_insp}
    method, url, kwargs = fake_requests.calls[-1]
    assert method == "post"
    assert url.endswith("/inspections/insp_test_101/complete")
    assert kwargs["json"] == {}

    fake_requests.response = FakeResponse(status_code=400)
    assert api_utils.complete_inspection("insp_test_101", {"deposit_base": 1500.0}) is None

    # 7. convert_inspection_item_to_work_order
    mock_wo_resp = {"work_order": {"id": "wo_99", "title": "Fix lock"}, "item_id": "item_1"}
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_wo_resp
    )
    assert (
        api_utils.convert_inspection_item_to_work_order("insp_test_101", {"item_id": "item_1"})
        == mock_wo_resp
    )
    method, url, kwargs = fake_requests.calls[-1]
    assert method == "post"
    assert url.endswith("/inspections/insp_test_101/convert-to-work-order")
    assert kwargs["json"] == {"item_id": "item_1"}

    fake_requests.response = FakeResponse(status_code=404)
    assert (
        api_utils.convert_inspection_item_to_work_order("insp_test_101", {"item_id": "item_1"})
        is None
    )

    # 8. publish_inspection_document
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_pub_resp
    )
    assert api_utils.publish_inspection_document("insp_test_101") == mock_pub_resp
    method, url, kwargs = fake_requests.calls[-1]
    assert method == "post"
    assert url.endswith("/inspections/insp_test_101/publish-document")
    assert kwargs["json"]["collection"] == "default"

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.publish_inspection_document("insp_test_101") is None

    # 9. create_session_inspection
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"inspection": mock_insp}
    )
    assert api_utils.create_session_inspection("sess_101", mock_insp) == {
        "inspection": mock_insp
    }
    method, url, kwargs = fake_requests.calls[-1]
    assert method == "post"
    assert url.endswith("/sessions/sess_101/create-inspection")
    assert kwargs["json"] == mock_insp

    fake_requests.response = FakeResponse(status_code=400)
    assert api_utils.create_session_inspection("sess_101", mock_insp) is None


def test_inspection_api_utils_queries_and_errors(fake_requests, monkeypatch):
    mock_insp = {
        "inspection_id": "insp_test_101",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "inspection_type": "move_out",
        "status": "scheduled",
    }
    mock_list_resp = {"items": [mock_insp], "total": 1, "limit": 50, "offset": 0}
    mock_metrics = {
        "total_inspections": 10,
        "status_distribution": {"completed": 5, "scheduled": 3},
        "type_distribution": {"move_in": 6, "move_out": 4},
        "condition_distribution": {"good": 5},
        "deposit_accounting_summary": {
            "total_estimated_deductions": 450.0,
            "total_actual_deductions": 400.0,
            "total_refund_amounts": 1600.0,
            "average_turnover_deduction": 200.0,
        },
        "turnover_punchlist_summary": {
            "total_punchlist_items": 8,
            "total_converted_to_work_orders": 3,
            "pending_punchlist_actions": 5,
        },
    }

    # 10. get_tenant_inspections
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_list_resp
    )
    assert api_utils.get_tenant_inspections("tenant_1") == mock_list_resp
    method, url, _ = fake_requests.calls[-1]
    assert method == "get"
    assert url.endswith("/tenants/tenant_1/inspections")

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_tenant_inspections("tenant_1") is None

    # 11. get_unit_inspections
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_list_resp
    )
    assert api_utils.get_unit_inspections("unit_101") == mock_list_resp
    method, url, _ = fake_requests.calls[-1]
    assert method == "get"
    assert url.endswith("/units/unit_101/inspections")

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.get_unit_inspections("unit_101") is None

    # 12. get_inspection_metrics
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload=mock_metrics
    )
    assert api_utils.get_inspection_metrics() == mock_metrics
    method, url, _ = fake_requests.calls[-1]
    assert method == "get"
    assert url.endswith("/inspections/metrics")

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_inspection_metrics() is None

    # 13. Exception handling via BoomRequests
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.create_inspection({}) is None
    assert api_utils.list_inspections() is None
    assert api_utils.get_inspection("insp_1") is None
    assert api_utils.update_inspection("insp_1", {}) is None
    assert api_utils.delete_inspection("insp_1") is False
    assert api_utils.complete_inspection("insp_1") is None
    assert api_utils.convert_inspection_item_to_work_order("insp_1", {}) is None
    assert api_utils.publish_inspection_document("insp_1") is None
    assert api_utils.create_session_inspection("sess_1", {}) is None
    assert api_utils.get_tenant_inspections("tenant_1") is None
    assert api_utils.get_unit_inspections("unit_1") is None
    assert api_utils.get_inspection_metrics() is None















def test_vendor_read_helpers(fake_requests, fake_st):
    listing = {"items": [{"id": "vnd_1"}], "total": 1, "limit": 50, "offset": 0}
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload=listing)
    assert api_utils.list_vendors(trade=" hvac ", status="active", search="cool") == listing
    method, url, kwargs = fake_requests.calls[0]
    assert method == "get"
    assert url.endswith("/vendors")
    assert kwargs["params"] == {
        "limit": 50,
        "offset": 0,
        "trade": "hvac",
        "status": "active",
        "search": "cool",
    }
    assert "headers" in kwargs

    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload={"vendor": {}})
    assert api_utils.get_vendor("vnd_1") == {"vendor": {}}
    assert fake_requests.calls[-1][1].endswith("/vendors/vnd_1")

    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload={"total": 2})
    assert api_utils.get_vendor_metrics() == {"total": 2}
    assert fake_requests.calls[-1][1].endswith("/vendors/metrics")

    fake_requests.response = FakeResponse(status_code=500)
    assert api_utils.get_vendor("vnd_1") is None
    assert fake_st.errors


def test_vendor_helpers_handle_network_errors(monkeypatch, fake_st):
    monkeypatch.setattr(api_utils, "requests", BoomRequests())
    assert api_utils.list_vendors() is None
    assert api_utils.get_vendor_metrics() is None
    assert any("network down" in str(e) for e in fake_st.errors)


def test_vendor_write_helpers(fake_requests, fake_st):
    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_CREATED, payload={"vendor": {"id": "vnd_new"}}
    )
    assert api_utils.create_vendor({"name": "New"}) == {"vendor": {"id": "vnd_new"}}
    method, url, kwargs = fake_requests.calls[-1]
    assert (method, kwargs["json"]) == ("post", {"name": "New"})
    assert url.endswith("/vendors")

    # a 200 is not a successful create
    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload={})
    assert api_utils.create_vendor({"name": "New"}) is None

    fake_requests.response = FakeResponse(status_code=api_utils.HTTP_OK, payload={"vendor": {}})
    assert api_utils.update_vendor("vnd_1", {"status": "inactive"}) == {"vendor": {}}
    method, url, kwargs = fake_requests.calls[-1]
    assert (method, kwargs["json"]) == ("patch", {"status": "inactive"})
    assert url.endswith("/vendors/vnd_1")

    fake_requests.response = FakeResponse(
        status_code=api_utils.HTTP_OK, payload={"status": "deleted"}
    )
    assert api_utils.delete_vendor("vnd_1") is True
    assert fake_requests.calls[-1][0] == "delete"

    fake_requests.response = FakeResponse(status_code=404)
    assert api_utils.delete_vendor("vnd_1") is False
    assert api_utils.update_vendor("vnd_1", {}) is None
    assert fake_st.errors
