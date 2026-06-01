from types import SimpleNamespace

from fastapi.testclient import TestClient

from api import main


client = TestClient(main.app)


def test_health_route():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sanitize_filename_removes_path_segments():
    assert main.sanitize_filename("../unsafe.pdf") == "unsafe.pdf"
    assert main.sanitize_filename(r"C:\temp\unsafe.pdf") == "unsafe.pdf"


def test_upload_rejects_unsupported_extension():
    response = client.post(
        "/upload-doc",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_empty_supported_file():
    response = client.post(
        "/upload-doc",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file cannot be empty."


def test_upload_removes_document_record_when_indexing_fails(monkeypatch):
    deleted_file_ids = []

    monkeypatch.setattr(main, "insert_document_record", lambda filename: 42)
    monkeypatch.setattr(main, "index_document_to_chroma", lambda *args: False)
    monkeypatch.setattr(main, "delete_document_record", lambda file_id: deleted_file_ids.append(file_id) or True)

    response = client.post(
        "/upload-doc",
        files={"file": ("lease.pdf", b"not really a pdf", "application/pdf")},
    )

    assert response.status_code == 500
    assert deleted_file_ids == [42]


def test_chat_returns_sources(monkeypatch):
    class FakeChain:
        def invoke(self, payload):
            return {
                "answer": "Use the tenant portal for maintenance requests.",
                "context": [
                    SimpleNamespace(
                        page_content="Maintenance requests should be submitted through the tenant portal.",
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
    monkeypatch.setattr(main, "get_rag_chain_for_model", lambda model: FakeChain())
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat",
        json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Use the tenant portal")
    assert body["sources"][0]["filename"] == "tenant-handbook.pdf"


def test_chat_returns_502_when_rag_chain_fails(monkeypatch):
    class FailingChain:
        def invoke(self, payload):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(main, "get_rag_chain_for_model", lambda model: FailingChain())
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat",
        json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to generate a response from the retrieval pipeline."


def test_chat_returns_502_when_rag_response_is_invalid(monkeypatch):
    class InvalidChain:
        def invoke(self, payload):
            return {"context": []}

    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(main, "get_rag_chain_for_model", lambda model: InvalidChain())
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    response = client.post(
        "/chat",
        json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "The retrieval pipeline returned an invalid response."


def test_delete_document_returns_404_for_unknown_document(monkeypatch):
    monkeypatch.setattr(main, "get_document_record", lambda file_id: None)

    response = client.post("/delete-doc", json={"file_id": 999})

    assert response.status_code == 404
    assert response.json()["detail"] == "Document with file_id 999 was not found."


def test_delete_document_rejects_non_positive_file_id():
    response = client.post("/delete-doc", json={"file_id": 0})

    assert response.status_code == 422


def test_delete_document_deletes_chroma_and_record(monkeypatch):
    calls = []

    monkeypatch.setattr(main, "get_document_record", lambda file_id: {"id": file_id, "filename": "lease.pdf"})
    monkeypatch.setattr(main, "delete_doc_from_chroma", lambda file_id: calls.append(("chroma", file_id)) or True)
    monkeypatch.setattr(main, "delete_document_record", lambda file_id: calls.append(("db", file_id)) or True)

    response = client.post("/delete-doc", json={"file_id": 42})

    assert response.status_code == 200
    assert calls == [("chroma", 42), ("db", 42)]
