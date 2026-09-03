from types import SimpleNamespace

from api import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_INTERNAL_ERROR = 500
HTTP_BAD_GATEWAY = 502
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_ENTITY = 422


def test_health_route():
    response = client.get("/health")

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "ok"


def test_sanitize_filename_removes_path_segments():
    assert main.sanitize_filename("../unsafe.pdf") == "unsafe.pdf"
    assert main.sanitize_filename(r"C:\temp\unsafe.pdf") == "unsafe.pdf"


def test_upload_rejects_unsupported_extension():
    response = client.post(
        "/upload-doc",
        files={"file": ("notes.xyz", b"hello", "application/octet-stream")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_empty_supported_file():
    response = client.post(
        "/upload-doc",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["detail"] == "Uploaded file cannot be empty."


def test_upload_removes_document_record_when_indexing_fails(monkeypatch):
    deleted_file_ids = []

    monkeypatch.setattr(main, "insert_document_record", lambda filename: 42)
    monkeypatch.setattr(
        main, "index_document_to_chroma", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(
        main, "delete_document_record", lambda file_id: deleted_file_ids.append(file_id) or True
    )

    response = client.post(
        "/upload-doc",
        files={"file": ("lease.pdf", b"not really a pdf", "application/pdf")},
    )

    assert response.status_code == HTTP_INTERNAL_ERROR
    assert deleted_file_ids == [42]


def test_chat_returns_sources(monkeypatch):
    class FakeChain:
        def invoke(self, payload):
            return {
                "answer": "Use the tenant portal for maintenance requests.",
                "context": [
                    SimpleNamespace(
                        page_content=(
                            "Maintenance requests should be submitted through the tenant portal."
                        ),
                        metadata={
                            "file_id": 7,
                            "filename": "tenant-handbook.pdf",
                            "page": 3,
                            "chunk_index": 2,
                        },
                    )
                ],
            }

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(main, "get_rag_chain_for_model", lambda model, *args, **kwargs: FakeChain())
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat",
        json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
    )

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["answer"].startswith("Use the tenant portal")
    assert body["sources"][0]["filename"] == "tenant-handbook.pdf"


def test_chat_returns_502_when_rag_chain_fails(monkeypatch):
    class FailingChain:
        def invoke(self, payload):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(
        main, "get_rag_chain_for_model", lambda model, *args, **kwargs: FailingChain()
    )
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat",
        json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
    )

    assert response.status_code == HTTP_BAD_GATEWAY
    assert response.json()["detail"] == (
        "Failed to generate a response from the retrieval pipeline."
    )


def test_chat_returns_502_when_rag_response_is_invalid(monkeypatch):
    class InvalidChain:
        def invoke(self, payload):
            return {"context": []}

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(
        main, "get_rag_chain_for_model", lambda model, *args, **kwargs: InvalidChain()
    )
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat",
        json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
    )

    assert response.status_code == HTTP_BAD_GATEWAY
    assert response.json()["detail"] == "The retrieval pipeline returned an invalid response."


def test_chat_forwards_retrieval_filters(monkeypatch):
    captured = {}

    class FakeChain:
        def invoke(self, payload):
            return {"answer": "Filtered answer.", "context": []}

    def fake_get_chain(model, *args, **kwargs):
        captured.update(kwargs)
        captured["model"] = model
        return FakeChain()

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(main, "get_rag_chain_for_model", fake_get_chain)
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat",
        json={
            "question": "Filter test?",
            "model": "gpt-4o-mini",
            "file_ids": [7],
            "source_filename": "tenant-handbook.pdf",
            "use_hybrid": True,
        },
    )

    assert response.status_code == HTTP_OK
    assert captured["file_ids"] == [7]
    assert captured["source_filename"] == "tenant-handbook.pdf"
    assert captured["use_hybrid"] is True


def test_upload_rejects_invalid_chunk_params():
    response = client.post(
        "/upload-doc?chunk_size=10&chunk_overlap=5",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert "chunk_size" in response.json()["detail"]


def test_upload_rejects_chunk_overlap_not_smaller_than_size():
    response = client.post(
        "/upload-doc?chunk_size=500&chunk_overlap=500",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert "chunk_overlap" in response.json()["detail"]


def test_delete_document_returns_404_for_unknown_document(monkeypatch):
    monkeypatch.setattr(main, "get_document_record", lambda file_id: None)

    response = client.post("/delete-doc", json={"file_id": 999})

    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["detail"] == "Document with file_id 999 was not found."


def test_delete_document_rejects_non_positive_file_id():
    response = client.post("/delete-doc", json={"file_id": 0})

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_delete_document_deletes_chroma_and_record(monkeypatch):
    calls = []

    monkeypatch.setattr(
        main,
        "get_document_record",
        lambda file_id: {"id": file_id, "filename": "lease.pdf"},
    )
    monkeypatch.setattr(
        main,
        "delete_doc_from_chroma",
        lambda file_id: calls.append(("chroma", file_id)) or True,
    )
    monkeypatch.setattr(
        main,
        "delete_document_record",
        lambda file_id: calls.append(("db", file_id)) or True,
    )

    response = client.post("/delete-doc", json={"file_id": 42})

    assert response.status_code == HTTP_OK
    assert calls == [("chroma", 42), ("db", 42)]


def test_chat_stream_returns_sse_events(monkeypatch):
    class FakeStreamChain:
        async def astream(self, payload):
            yield {"answer": "Hello"}
            yield {"answer": " world"}
            yield {"context": []}

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(
        main, "get_rag_chain_for_model", lambda model, *args, **kwargs: FakeStreamChain()
    )
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat/stream",
        json={"question": "Hello", "model": "gpt-4o-mini"},
    )

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    content = response.text
    assert "data: Hello" in content
    assert "data:  world" in content


def test_chat_stream_handles_chain_error(monkeypatch):
    class FailingStreamChain:
        async def astream(self, payload):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(
        main, "get_rag_chain_for_model", lambda model, *args, **kwargs: FailingStreamChain()
    )
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat/stream",
        json={"question": "Hello", "model": "gpt-4o-mini"},
    )

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    content = response.text
    assert "event: error" in content
