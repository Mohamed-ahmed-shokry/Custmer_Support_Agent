import json
from types import SimpleNamespace

import pytest
from api import main, observability, security
from api.observability import estimate_tokens
from api.settings import settings
from fastapi.testclient import TestClient

client = TestClient(main.app)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_TOO_MANY_REQUESTS = 429
HTTP_INTERNAL_ERROR = 500
HTTP_BAD_GATEWAY = 502
EXPECTED_RETRIEVER_K = 5


@pytest.fixture(autouse=True)
def _stub_document_source_storage(monkeypatch):
    """Keep source-storage wiring out of unrelated upload tests.

    Records `save_document_source` calls instead of hitting the real DB so
    whole-suite runs do not churn through real loaders or accumulate source
    rows. Dedicated tests below override the load stub to assert the exact
    source text and options stored.
    """
    saved = []

    def record_source(
        file_id, source_text, strategy="recursive", chunk_size=1000, chunk_overlap=200
    ):
        saved.append(
            {
                "file_id": file_id,
                "source_text": source_text,
                "strategy": strategy,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            }
        )

    monkeypatch.setattr(main, "load_document_source", lambda file_path: "stub source text")
    monkeypatch.setattr(main, "save_document_source", record_source)
    yield saved


def test_health_route():
    response = client.get("/health")

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "ok"


def test_get_config_route():
    response = client.get("/config")

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["app_name"] == settings.app_name
    assert data["app_version"] == settings.app_version
    assert data["default_model"] == settings.default_model
    assert data["retriever_k"] == settings.retriever_k
    assert "supported_chunking_strategies" in data


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

    monkeypatch.setattr(main, "insert_document_record", lambda filename, *args, **kwargs: 42)
    monkeypatch.setattr(main, "get_document_by_hash", lambda sha256: None)
    monkeypatch.setattr(main, "index_document_to_chroma", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        main, "delete_document_record", lambda file_id: deleted_file_ids.append(file_id) or True
    )

    response = client.post(
        "/upload-doc",
        files={"file": ("lease.pdf", b"not really a pdf", "application/pdf")},
    )

    assert response.status_code == HTTP_INTERNAL_ERROR
    assert deleted_file_ids == [42]


def test_upload_stores_normalized_collection(monkeypatch):
    recorded = {}

    def fake_insert(filename, collection="default", sha256=None):
        recorded["collection"] = collection
        recorded["sha256"] = sha256
        return 7

    monkeypatch.setattr(main, "insert_document_record", fake_insert)
    monkeypatch.setattr(main, "get_document_by_hash", lambda sha256: None)
    monkeypatch.setattr(
        main, "index_document_to_chroma", lambda *args, **kwargs: recorded.update(kwargs) or True
    )

    response = client.post(
        "/upload-doc?collection=Clients-Acme",
        files={"file": ("lease.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == HTTP_OK
    assert recorded["collection"] == "clients-acme"
    assert recorded["options"] is not None
    expected_hex_length = 64
    assert recorded["sha256"] is not None and len(recorded["sha256"]) == expected_hex_length


def test_upload_stores_source_text_and_chunking_options(monkeypatch, _stub_document_source_storage):
    expected_file_id = 7
    expected_size = 400
    expected_overlap = 50
    expected_source = "extracted source: " * 10
    monkeypatch.setattr(
        main, "insert_document_record", lambda filename, *args, **kwargs: expected_file_id
    )
    monkeypatch.setattr(main, "get_document_by_hash", lambda sha256: None)
    monkeypatch.setattr(main, "index_document_to_chroma", lambda *args, **kwargs: True)
    monkeypatch.setattr(main, "load_document_source", lambda file_path: expected_source)

    response = client.post(
        "/upload-doc?chunking_strategy=semantic&chunk_size=400&chunk_overlap=50",
        files={"file": ("lease.pdf", b"%PDF fake", "application/pdf")},
    )

    assert response.status_code == HTTP_OK
    stored = _stub_document_source_storage[-1]
    assert stored["file_id"] == expected_file_id
    assert stored["source_text"] == expected_source
    assert stored["strategy"] == "semantic"
    assert stored["chunk_size"] == expected_size
    assert stored["chunk_overlap"] == expected_overlap


def test_upload_index_failure_removes_source_text(monkeypatch):
    cleanup_events = []
    monkeypatch.setattr(main, "insert_document_record", lambda filename, *args, **kwargs: 9)
    monkeypatch.setattr(main, "get_document_by_hash", lambda sha256: None)
    monkeypatch.setattr(main, "index_document_to_chroma", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        main, "delete_document_record", lambda file_id: cleanup_events.append(file_id) or True
    )
    monkeypatch.setattr(
        main,
        "delete_document_source",
        lambda file_id: cleanup_events.append(("source", file_id)) or True,
    )

    response = client.post(
        "/upload-doc",
        files={"file": ("lease.pdf", b"%PDF fake", "application/pdf")},
    )

    assert response.status_code == HTTP_INTERNAL_ERROR
    assert cleanup_events == [9, ("source", 9)]


def test_bulk_upload_indexes_each_file(monkeypatch):
    file_ids = iter([101, 102])
    monkeypatch.setattr(
        main, "insert_document_record", lambda filename, *args, **kwargs: next(file_ids)
    )
    monkeypatch.setattr(main, "get_document_by_hash", lambda sha256: None)
    monkeypatch.setattr(main, "index_document_to_chroma", lambda *args, **kwargs: True)

    response = client.post(
        "/upload-docs",
        files=[
            ("files", ("a.pdf", b"%PDF first", "application/pdf")),
            ("files", ("b.pdf", b"%PDF second", "application/pdf")),
        ],
    )

    assert response.status_code == HTTP_OK
    body = response.json()
    expected_uploads = 2
    assert body["uploaded"] == expected_uploads
    assert body["failed"] == 0
    assert [item["file_id"] for item in body["results"]] == [101, 102]


def test_bulk_upload_reports_per_file_errors(monkeypatch):
    monkeypatch.setattr(main, "insert_document_record", lambda filename, *args, **kwargs: 42)
    monkeypatch.setattr(main, "get_document_by_hash", lambda sha256: None)
    monkeypatch.setattr(main, "index_document_to_chroma", lambda *args, **kwargs: True)

    response = client.post(
        "/upload-docs",
        files=[
            ("files", ("good.pdf", b"%PDF good", "application/pdf")),
            ("files", ("notes.xyz", b"hello", "application/octet-stream")),
        ],
    )

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["uploaded"] == 1
    assert body["failed"] == 1
    assert body["results"][0]["status"] == "indexed"
    assert body["results"][1]["status"] == "error"


def test_bulk_upload_rejects_too_many_files(monkeypatch):
    monkeypatch.setattr(settings, "max_bulk_files", 1)

    response = client.post(
        "/upload-docs",
        files=[
            ("files", ("a.pdf", b"%PDF a", "application/pdf")),
            ("files", ("b.pdf", b"%PDF b", "application/pdf")),
        ],
    )

    assert response.status_code == HTTP_BAD_REQUEST


def test_upload_rejects_duplicate_content(monkeypatch):
    def fail_insert(*args, **kwargs):
        raise AssertionError("duplicate upload must not create a record")

    monkeypatch.setattr(main, "insert_document_record", fail_insert)
    monkeypatch.setattr(
        main, "get_document_by_hash", lambda sha256: {"id": 9, "filename": "orig.pdf"}
    )

    response = client.post(
        "/upload-doc",
        files={"file": ("copy.pdf", b"identical bytes", "application/pdf")},
    )

    assert response.status_code == HTTP_CONFLICT
    assert "orig.pdf" in response.json()["detail"]


def test_upload_rejects_invalid_collection():
    response = client.post(
        "/upload-doc?collection=bad%20name!",
        files={"file": ("lease.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert "Collection" in response.json()["detail"]


def test_list_docs_filters_by_collection(monkeypatch):
    seen = {}

    def fake_list(collection=None):
        seen["collection"] = collection
        return [
            {
                "id": 1,
                "filename": "a.pdf",
                "collection": collection or "default",
                "upload_timestamp": "2026-09-04T00:00:00",
            }
        ]

    monkeypatch.setattr(main, "get_all_documents", fake_list)

    response = client.get("/list-docs?collection=clients-acme")

    assert response.status_code == HTTP_OK
    assert seen["collection"] == "clients-acme"
    assert response.json()[0]["collection"] == "clients-acme"


def test_list_docs_rejects_invalid_collection():
    response = client.get("/list-docs?collection=bad%20name!")

    assert response.status_code == HTTP_BAD_REQUEST


def test_list_collections(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: ["acme", "default"])

    response = client.get("/collections")

    assert response.status_code == HTTP_OK
    assert response.json() == ["acme", "default"]


def test_get_collections_details_route(monkeypatch):
    mock_details = [
        {
            "collection": "legal",
            "document_count": 2,
            "file_formats": {"pdf": 2},
            "earliest_upload": "2026-09-01 10:00:00",
            "latest_upload": "2026-09-02 12:00:00",
        }
    ]
    monkeypatch.setattr(main, "get_collections_details", lambda: mock_details)
    monkeypatch.setattr(main, "get_collection_chunk_count", lambda col: 6)

    response = client.get("/collections/details")
    assert response.status_code == HTTP_OK
    data = response.json()
    expected_collections = 1
    expected_docs = 2
    expected_chunks = 6
    assert len(data) == expected_collections
    assert data[0]["collection"] == "legal"
    assert data[0]["document_count"] == expected_docs
    assert data[0]["chunk_count"] == expected_chunks
    assert data[0]["file_formats"] == {"pdf": 2}


def test_delete_collection_removes_chunks_and_records(monkeypatch):
    monkeypatch.setattr(main, "delete_collection_from_chroma", lambda collection: 3)
    monkeypatch.setattr(main, "delete_documents_by_collection", lambda collection: 2)

    response = client.delete("/collections/acme")

    assert response.status_code == HTTP_OK
    assert "acme" in response.json()["message"]


def test_delete_collection_rejects_default_collection():
    response = client.delete("/collections/default")

    assert response.status_code == HTTP_BAD_REQUEST


def test_delete_collection_rejects_invalid_name():
    response = client.delete("/collections/bad%20name!")

    assert response.status_code == HTTP_BAD_REQUEST


def test_delete_collection_returns_404_when_empty(monkeypatch):
    monkeypatch.setattr(main, "delete_collection_from_chroma", lambda collection: 0)
    monkeypatch.setattr(main, "delete_documents_by_collection", lambda collection: 0)

    response = client.delete("/collections/acme")

    assert response.status_code == HTTP_NOT_FOUND


def test_delete_collection_returns_500_when_chroma_fails(monkeypatch):
    monkeypatch.setattr(main, "delete_collection_from_chroma", lambda collection: -1)
    monkeypatch.setattr(main, "delete_documents_by_collection", lambda collection: 2)

    response = client.delete("/collections/acme")

    assert response.status_code == HTTP_INTERNAL_ERROR


def test_rename_collection_moves_documents_and_chunks(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: ["acme", "default"])
    monkeypatch.setattr(main, "rename_collection_in_chroma", lambda old, new: 3)
    monkeypatch.setattr(main, "rename_collection", lambda old, new: 2)

    response = client.patch("/collections/acme", json={"collection": "Globex"})

    assert response.status_code == HTTP_OK
    body = response.json()
    expected_documents = 2
    expected_chunks = 3
    assert body["collection"] == "globex"
    assert body["documents"] == expected_documents
    assert body["chunks"] == expected_chunks


def test_rename_collection_rejects_existing_target(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: ["acme", "globex"])

    response = client.patch("/collections/acme", json={"collection": "globex"})

    assert response.status_code == HTTP_CONFLICT


def test_rename_collection_returns_404_when_empty(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: [])
    monkeypatch.setattr(main, "rename_collection_in_chroma", lambda old, new: 0)
    monkeypatch.setattr(main, "rename_collection", lambda old, new: 0)

    response = client.patch("/collections/acme", json={"collection": "globex"})

    assert response.status_code == HTTP_NOT_FOUND


def test_rename_collection_rejects_invalid_names():
    assert (
        client.patch("/collections/bad%20name!", json={"collection": "globex"}).status_code
        == HTTP_BAD_REQUEST
    )
    assert (
        client.patch("/collections/acme", json={"collection": "bad name!"}).status_code
        == HTTP_UNPROCESSABLE_ENTITY
    )


def test_get_collection_analytics_success(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: ["legal", "default"])
    mock_analytics = {
        "collection": "legal",
        "total_documents": 2,
        "total_chunks": 8,
        "avg_chunk_length": 420.5,
        "min_chunk_length": 150,
        "max_chunk_length": 950,
        "median_chunk_length": 410.0,
        "strategy_distribution": {"recursive": 5, "semantic": 3},
        "length_histogram": {
            "<200": 1,
            "200-500": 4,
            "500-1000": 3,
            "1000-2000": 0,
            ">2000": 0,
        },
    }
    monkeypatch.setattr(main, "get_collection_chunk_analytics", lambda col: mock_analytics)

    response = client.get("/collections/legal/analytics")
    assert response.status_code == HTTP_OK
    data = response.json()
    expected_docs = 2
    expected_chunks = 8
    expected_avg = 420.5
    expected_semantic = 3
    assert data["collection"] == "legal"
    assert data["total_documents"] == expected_docs
    assert data["total_chunks"] == expected_chunks
    assert data["avg_chunk_length"] == expected_avg
    assert data["strategy_distribution"]["semantic"] == expected_semantic


def test_get_collection_analytics_not_found(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: ["default"])
    response = client.get("/collections/nonexistent/analytics")
    assert response.status_code == HTTP_NOT_FOUND


def test_get_collection_analytics_invalid_name():
    response = client.get("/collections/bad%20name!/analytics")
    assert response.status_code == HTTP_BAD_REQUEST


def test_rechunk_collection_success_default_and_custom(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: ["legal"])

    mock_result = {
        "collection": "legal",
        "strategy": "semantic",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "total_documents": 3,
        "rechunked_documents": 2,
        "skipped_documents": 1,
        "failed_documents": 0,
        "total_chunks_created": 12,
        "items": [
            {
                "file_id": 1,
                "filename": "doc1.txt",
                "status": "rechunked",
                "chunk_count": 6,
                "error_message": None,
            },
            {
                "file_id": 2,
                "filename": "doc2.txt",
                "status": "rechunked",
                "chunk_count": 6,
                "error_message": None,
            },
            {
                "file_id": 3,
                "filename": "doc3.txt",
                "status": "skipped",
                "chunk_count": 0,
                "error_message": "No stored source text",
            },
        ],
    }
    called_options = []

    def fake_rechunk(col, options):
        called_options.append((col, options))
        return mock_result

    monkeypatch.setattr(main, "rechunk_collection_in_chroma", fake_rechunk)

    # 1. Custom body
    response = client.post(
        "/collections/legal/rechunk",
        json={"chunking_strategy": "semantic", "chunk_size": 500, "chunk_overlap": 50},
    )
    assert response.status_code == HTTP_OK
    data = response.json()
    expected_total_docs = 3
    expected_rechunked = 2
    expected_skipped = 1
    expected_chunks = 12
    assert data["collection"] == "legal"
    assert data["strategy"] == "semantic"
    assert data["total_documents"] == expected_total_docs
    assert data["rechunked_documents"] == expected_rechunked
    assert data["skipped_documents"] == expected_skipped
    assert data["total_chunks_created"] == expected_chunks
    assert len(data["items"]) == expected_total_docs
    assert "Re-chunked collection 'legal'" in data["message"]
    assert called_options[0][1].strategy == "semantic"

    # 2. Empty body (defaults)
    called_options.clear()
    response_empty = client.post("/collections/legal/rechunk", json={})
    assert response_empty.status_code == HTTP_OK
    assert called_options[0][1].strategy == "recursive"


def test_rechunk_collection_not_found(monkeypatch):
    monkeypatch.setattr(main, "get_all_collections", lambda: ["default"])
    response = client.post("/collections/unknown/rechunk", json={})
    assert response.status_code == HTTP_NOT_FOUND


def test_rechunk_collection_invalid_name():
    response = client.post("/collections/bad%20name!/rechunk", json={})
    assert response.status_code == HTTP_BAD_REQUEST


def test_rechunk_collection_invalid_body():
    response = client.post(
        "/collections/legal/rechunk",
        json={"chunk_size": 50},  # below min 100
    )
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY

    response_overlap = client.post(
        "/collections/legal/rechunk",
        json={"chunk_size": 500, "chunk_overlap": 500},  # overlap >= size
    )
    assert response_overlap.status_code == HTTP_UNPROCESSABLE_ENTITY


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
            "collections": ["Clients-Acme"],
            "expand_query": True,
            "rerank": True,
        },
    )

    assert response.status_code == HTTP_OK
    assert captured["file_ids"] == [7]
    assert captured["source_filename"] == "tenant-handbook.pdf"
    assert captured["use_hybrid"] is True
    assert captured["collections"] == ["clients-acme"]
    assert captured["expand_query"] is True
    assert captured["rerank"] is True


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


def test_chat_rejects_missing_api_key_when_configured(monkeypatch):
    security.reset()
    monkeypatch.setattr(settings, "api_key", "secret")

    response = client.post(
        "/chat",
        json={"question": "Hello", "model": "gpt-4o-mini"},
    )

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["X-Request-ID"]
    monkeypatch.setattr(settings, "api_key", "")


def test_health_stays_public_when_api_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")

    response = client.get("/health")

    assert response.status_code == HTTP_OK
    monkeypatch.setattr(settings, "api_key", "")


def test_chat_rate_limit_blocks_after_quota(monkeypatch):
    class FakeChain:
        def invoke(self, payload):
            return {"answer": "OK", "context": []}

    security.reset()
    monkeypatch.setattr(settings, "rate_limit_per_min", 2)
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(main, "get_rag_chain_for_model", lambda model, *args, **kwargs: FakeChain())
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    try:
        for _ in range(2):
            response = client.post(
                "/chat",
                json={"question": "Hello", "model": "gpt-4o-mini"},
            )
            assert response.status_code == HTTP_OK
        limited = client.post(
            "/chat",
            json={"question": "Hello", "model": "gpt-4o-mini"},
        )
        assert limited.status_code == HTTP_TOO_MANY_REQUESTS
        assert limited.headers["Retry-After"] == "60"
    finally:
        monkeypatch.setattr(settings, "rate_limit_per_min", 0)
        security.reset()


def test_chat_enforces_daily_token_quota(monkeypatch):
    class FakeChain:
        def invoke(self, payload):
            return {"answer": "Use the tenant portal.", "context": []}

    security.reset()
    monkeypatch.setattr(settings, "token_daily_budget_est", 10)
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(main, "get_rag_chain_for_model", lambda model, *args, **kwargs: FakeChain())
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    try:
        first = client.post(
            "/chat",
            json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
        )
        assert first.status_code == HTTP_OK
        second = client.post(
            "/chat",
            json={"question": "How do I request maintenance?", "model": "gpt-4o-mini"},
        )
        assert second.status_code == HTTP_TOO_MANY_REQUESTS
    finally:
        monkeypatch.setattr(settings, "token_daily_budget_est", 0)
        security.reset()


def test_quota_reports_unlimited_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "token_daily_budget_est", 0)

    response = client.get("/quota")

    assert response.status_code == HTTP_OK
    assert response.json() == {"budget": 0, "used": 0, "remaining": None, "unlimited": True}


def test_quota_reports_usage_against_budget(monkeypatch):
    monkeypatch.setattr(settings, "token_daily_budget_est", 100)
    monkeypatch.setattr(main, "get_token_usage", lambda key, today=None: 30)

    response = client.get("/quota")

    assert response.status_code == HTTP_OK
    assert response.json() == {"budget": 100, "used": 30, "remaining": 70, "unlimited": False}


def test_stats_returns_library_totals(monkeypatch):
    totals = {
        "documents": 2,
        "collections": 1,
        "sessions": 2,
        "messages": 3,
        "feedback_up": 1,
        "feedback_down": 0,
    }
    monkeypatch.setattr(main, "get_library_stats", lambda: totals)

    response = client.get("/stats")

    assert response.status_code == HTTP_OK
    assert response.json() == totals


def test_health_probes():
    live = client.get("/health/live")
    assert live.status_code == HTTP_OK
    assert live.json() == {"status": "ok"}

    ready = client.get("/health/ready")
    assert ready.status_code == HTTP_OK
    body = ready.json()
    assert body["ready"] is True
    assert body["checks"]["sqlite"] == "ok"
    assert body["checks"]["chroma_dir"] == "ok"


def test_latency_metrics_recorded():
    observability.reset()
    client.get("/health")
    body = client.get("/metrics.json").json()
    assert body["latency_count_other"] >= 1
    assert body["latency_avg_seconds_other"] >= 0.0


def test_search_latency_recorded_under_search_group(monkeypatch):
    observability.reset()

    def fake_select(**kwargs):
        return SimpleNamespace(invoke=lambda question: [])

    monkeypatch.setattr(main, "select_retriever", fake_select)

    response = client.post("/search", json={"question": "Hello"})
    assert response.status_code == HTTP_OK
    body = client.get("/metrics.json").json()
    assert body["latency_count_search"] >= 1


def test_metrics_endpoints_return_counters():
    response = client.get("/metrics")
    assert response.status_code == HTTP_OK
    assert "rag_agent_chat_requests" in response.text

    response_json = client.get("/metrics.json")
    assert response_json.status_code == HTTP_OK
    assert "chat_requests" in response_json.json()


def test_list_sessions_returns_summaries(monkeypatch):
    sessions = [
        {
            "session_id": "session-1",
            "message_count": 2,
            "last_active": "2026-09-04T00:00:00",
            "preview": "How do I request?",
            "label": None,
            "status": "active",
            "tags": "",
            "summary": None,
            "resolution_notes": None,
        }
    ]
    monkeypatch.setattr(main, "get_all_sessions", lambda: sessions)

    response = client.get("/sessions")

    assert response.status_code == HTTP_OK
    assert response.json() == sessions


def test_list_sessions_filtering(monkeypatch):
    calls = []

    def fake_get_sessions(status=None, tag=None):
        calls.append((status, tag))
        return []

    monkeypatch.setattr(main, "get_all_sessions", fake_get_sessions)

    res1 = client.get("/sessions?status=resolved")
    assert res1.status_code == HTTP_OK
    assert calls[-1] == ("resolved", None)

    res2 = client.get("/sessions?tag=urgent")
    assert res2.status_code == HTTP_OK
    assert calls[-1] == (None, "urgent")

    res3 = client.get("/sessions?status=invalid-status")
    assert res3.status_code == HTTP_BAD_REQUEST
    assert "Invalid session status" in res3.json()["detail"]


def test_session_history_returns_messages(monkeypatch):
    history = [
        {"role": "human", "content": "Hi"},
        {"role": "ai", "content": "Hello!"},
    ]
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: history)

    response = client.get("/sessions/session-1/history")

    assert response.status_code == HTTP_OK
    assert response.json() == history


def test_session_history_rejects_blank_session_id():
    response = client.get("/sessions/%20/history")

    assert response.status_code == HTTP_BAD_REQUEST


def test_delete_session_removes_it(monkeypatch):
    monkeypatch.setattr(main, "delete_session", lambda session_id: True)

    response = client.delete("/sessions/session-1")

    assert response.status_code == HTTP_OK
    assert "session-1" in response.json()["message"]


def test_delete_session_returns_404_when_unknown(monkeypatch):
    monkeypatch.setattr(main, "delete_session", lambda session_id: False)

    response = client.delete("/sessions/missing")

    assert response.status_code == HTTP_NOT_FOUND


def test_delete_session_rejects_blank_session_id():
    response = client.delete("/sessions/%20")

    assert response.status_code == HTTP_BAD_REQUEST


def test_prune_sessions_returns_deleted_count(monkeypatch):
    monkeypatch.setattr(main, "prune_sessions_before", lambda cutoff: 2)

    response = client.delete("/sessions", params={"before": "2021-01-01T00:00:00"})

    assert response.status_code == HTTP_OK
    expected_deleted = 2
    assert response.json()["deleted_sessions"] == expected_deleted


def test_prune_sessions_rejects_invalid_date():
    response = client.delete("/sessions", params={"before": "not-a-date"})

    assert response.status_code == HTTP_BAD_REQUEST


def test_prune_sessions_requires_before_param():
    response = client.delete("/sessions")

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_submit_feedback_records_rating(monkeypatch):
    monkeypatch.setattr(
        main, "get_chat_history", lambda session_id: [{"role": "human", "content": "Hi"}]
    )
    monkeypatch.setattr(main, "insert_feedback", lambda session_id, rating, comment=None: 3)

    response = client.post("/feedback", json={"session_id": "session-1", "rating": 1})

    assert response.status_code == HTTP_OK
    assert response.json() == {"message": "Feedback recorded.", "feedback_id": 3}


def test_submit_feedback_with_comment(monkeypatch):
    recorded = {}
    monkeypatch.setattr(
        main, "get_chat_history", lambda session_id: [{"role": "human", "content": "Hi"}]
    )

    def fake_insert(session_id, rating, comment=None):
        recorded["session_id"] = session_id
        recorded["rating"] = rating
        recorded["comment"] = comment
        return 42

    monkeypatch.setattr(main, "insert_feedback", fake_insert)
    response = client.post(
        "/feedback",
        json={"session_id": "session-1", "rating": -1, "comment": "Needs more detail"},
    )
    assert response.status_code == HTTP_OK
    assert response.json() == {"message": "Feedback recorded.", "feedback_id": 42}
    assert recorded == {
        "session_id": "session-1",
        "rating": -1,
        "comment": "Needs more detail",
    }


def test_submit_feedback_returns_404_for_unknown_session(monkeypatch):
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])

    response = client.post("/feedback", json={"session_id": "missing", "rating": 1})

    assert response.status_code == HTTP_NOT_FOUND


def test_submit_feedback_rejects_invalid_rating():
    response = client.post("/feedback", json={"session_id": "session-1", "rating": 0})

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_submit_feedback_rejects_blank_session_id():
    response = client.post("/feedback", json={"session_id": "   ", "rating": -1})

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_list_feedback_route(monkeypatch):
    fake_items = [
        {
            "id": 1,
            "session_id": "s1",
            "rating": 1,
            "comment": "Nice",
            "created_at": "2026-09-21 00:00:00",
        }
    ]
    monkeypatch.setattr(
        main,
        "list_feedback",
        lambda rating=None, session_id=None, limit=50, offset=0: (fake_items, 1),
    )
    response = client.get("/feedback?rating=1&session_id=s1&limit=10&offset=0")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["comment"] == "Nice"


def test_list_feedback_route_validation():
    response = client.get("/feedback?rating=0")
    assert response.status_code == HTTP_BAD_REQUEST

    response = client.get("/feedback?limit=0")
    assert response.status_code == HTTP_BAD_REQUEST

    response = client.get("/feedback?limit=101")
    assert response.status_code == HTTP_BAD_REQUEST

    response = client.get("/feedback?offset=-1")
    assert response.status_code == HTTP_BAD_REQUEST


def test_get_session_feedback_route(monkeypatch):
    fake_items = [
        {
            "id": 1,
            "session_id": "s1",
            "rating": 1,
            "comment": "Nice",
            "created_at": "2026-09-21 00:00:00",
        }
    ]
    monkeypatch.setattr(
        main, "get_chat_history", lambda session_id: [{"role": "human", "content": "Hi"}]
    )
    monkeypatch.setattr(main, "get_session_feedback", lambda session_id: fake_items)
    response = client.get("/sessions/s1/feedback")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1


def test_get_session_feedback_route_not_found(monkeypatch):
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    response = client.get("/sessions/missing/feedback")
    assert response.status_code == HTTP_NOT_FOUND


def test_feedback_analytics_route_success(monkeypatch):
    sample_data = {
        "total_feedback": 10,
        "positive_feedback": 8,
        "negative_feedback": 2,
        "satisfaction_rate": 80.0,
        "total_comments": 4,
        "comment_rate": 40.0,
        "recent_comments": [
            {
                "id": 1,
                "session_id": "s1",
                "rating": 1,
                "comment": "Good job",
                "created_at": "2026-09-21 00:00:00",
            }
        ],
    }
    monkeypatch.setattr(main, "get_feedback_analytics", lambda recent_comments_limit=5: sample_data)
    response = client.get("/feedback/analytics?recent_comments_limit=3")
    assert response.status_code == HTTP_OK
    data = response.json()
    expected_rate = 80.0
    expected_total = 10
    assert data["satisfaction_rate"] == expected_rate
    assert data["total_feedback"] == expected_total
    assert len(data["recent_comments"]) == 1


def test_feedback_analytics_route_validation():
    res_neg = client.get("/feedback/analytics?recent_comments_limit=-1")
    assert res_neg.status_code == HTTP_BAD_REQUEST

    res_too_large = client.get("/feedback/analytics?recent_comments_limit=51")
    assert res_too_large.status_code == HTTP_BAD_REQUEST


def test_export_session_returns_markdown_transcript(monkeypatch):
    history = [
        {"role": "human", "content": "When is rent due?"},
        {"role": "ai", "content": "On the first."},
    ]
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: history)
    monkeypatch.setattr(
        main,
        "get_all_sessions",
        lambda: [
            {
                "session_id": "session-1",
                "message_count": 2,
                "last_active": "2026-09-04T00:00:00",
                "preview": "When is rent due?",
                "label": "Rent questions",
            }
        ],
    )

    response = client.get("/sessions/session-1/export")

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"].startswith("text/markdown")
    body = response.text
    assert "# Conversation: Rent questions" in body
    assert "## User" in body
    assert "When is rent due?" in body
    assert "## Assistant" in body


def test_export_session_returns_404_when_unknown(monkeypatch):
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])

    response = client.get("/sessions/missing/export")

    assert response.status_code == HTTP_NOT_FOUND


def test_export_session_rejects_blank_session_id():
    response = client.get("/sessions/%20/export")

    assert response.status_code == HTTP_BAD_REQUEST


def test_export_session_json_and_csv(monkeypatch):
    history = [
        {"role": "human", "content": "When is rent due?"},
        {"role": "ai", "content": "On the first."},
    ]
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: history)
    monkeypatch.setattr(
        main,
        "get_all_sessions",
        lambda: [{"session_id": "session-1", "label": "Rent questions"}],
    )

    json_res = client.get("/sessions/session-1/export?format=json")
    assert json_res.status_code == HTTP_OK
    assert "application/json" in json_res.headers["content-type"]
    assert "session-1.json" in json_res.headers["content-disposition"]
    json_data = json.loads(json_res.text)
    expected_messages = 2
    assert json_data["session_id"] == "session-1"
    assert len(json_data["messages"]) == expected_messages

    csv_res = client.get("/sessions/session-1/export?format=csv")
    assert csv_res.status_code == HTTP_OK
    assert "text/csv" in csv_res.headers["content-type"]
    assert "session-1.csv" in csv_res.headers["content-disposition"]
    assert "session_id,label,status,tags,summary,resolution_notes,turn,role,content" in csv_res.text


def test_export_session_rejects_invalid_format():
    response = client.get("/sessions/session-1/export?format=xml")
    assert response.status_code == HTTP_BAD_REQUEST
    assert "format" in response.json()["detail"].lower()


def test_rename_session_returns_updated_summary(monkeypatch):
    summary = {
        "session_id": "session-1",
        "message_count": 2,
        "last_active": "2026-09-04T00:00:00",
        "preview": "How do I request?",
        "label": "Lease questions",
    }
    monkeypatch.setattr(main, "rename_session", lambda session_id, label: True)
    monkeypatch.setattr(main, "get_all_sessions", lambda: [summary])

    response = client.patch("/sessions/session-1", json={"label": "Lease questions"})

    assert response.status_code == HTTP_OK
    assert response.json()["label"] == "Lease questions"


def test_rename_session_returns_404_when_unknown(monkeypatch):
    monkeypatch.setattr(main, "rename_session", lambda session_id, label: False)

    response = client.patch("/sessions/missing", json={"label": "Lease questions"})

    assert response.status_code == HTTP_NOT_FOUND


def test_rename_session_rejects_blank_label():
    response = client.patch("/sessions/session-1", json={"label": "   "})

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_update_session_metadata_success(monkeypatch):
    summary = {
        "session_id": "session-1",
        "message_count": 2,
        "last_active": "2026-09-04T00:00:00",
        "preview": "How do I request?",
        "label": "Lease",
        "status": "resolved",
        "tags": "lease, urgent",
    }
    recorded_args = {}

    def fake_update(session_id, label=None, status=None, tags=None, **kwargs):
        recorded_args.update(
            {"session_id": session_id, "label": label, "status": status, "tags": tags}
        )
        return True

    monkeypatch.setattr(main, "update_session_metadata", fake_update)
    monkeypatch.setattr(main, "get_all_sessions", lambda: [summary])

    payload = {"status": "resolved", "tags": "lease, urgent"}
    response = client.patch("/sessions/session-1", json=payload)

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "resolved"
    assert response.json()["tags"] == "lease, urgent"
    assert recorded_args["status"] == "resolved"


def test_update_session_rejects_invalid_status_or_empty_body():
    # Invalid status -> 422
    res_bad_status = client.patch("/sessions/session-1", json={"status": "invalid_status"})
    assert res_bad_status.status_code == HTTP_UNPROCESSABLE_ENTITY

    # Empty body -> 422
    res_empty = client.patch("/sessions/session-1", json={})
    assert res_empty.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_update_session_returns_404_when_missing(monkeypatch):
    monkeypatch.setattr(main, "update_session_metadata", lambda *args, **kwargs: False)
    response = client.patch("/sessions/missing", json={"status": "resolved"})
    assert response.status_code == HTTP_NOT_FOUND


def test_chat_records_estimated_tokens(monkeypatch):
    class FakeChain:
        def invoke(self, payload):
            return {"answer": "Use the tenant portal.", "context": []}

    observability.reset()
    monkeypatch.setattr(main, "get_chat_history", lambda session_id: [])
    monkeypatch.setattr(main, "get_rag_chain_for_model", lambda model, *args, **kwargs: FakeChain())
    monkeypatch.setattr(main, "insert_application_logs", lambda *args: None)

    question = "How do I request maintenance?"
    response = client.post(
        "/chat",
        json={"question": question, "model": "gpt-4o-mini"},
    )

    assert response.status_code == HTTP_OK
    metrics = client.get("/metrics.json").json()
    assert metrics["prompt_tokens_est"] == estimate_tokens(question)
    assert metrics["completion_tokens_est"] == estimate_tokens("Use the tenant portal.")


def test_search_returns_ranked_hits(monkeypatch):
    class FakeRetriever:
        def invoke(self, question):
            return [
                SimpleNamespace(
                    page_content="  Maintenance portal details.  ",
                    metadata={
                        "file_id": 7,
                        "filename": "tenant-handbook.pdf",
                        "page": 3,
                        "chunk_index": 2,
                        "collection": "default",
                    },
                )
            ]

    captured = {}

    def fake_select(**kwargs):
        captured.update(kwargs)
        return FakeRetriever()

    monkeypatch.setattr(main, "select_retriever", fake_select)

    response = client.post(
        "/search",
        json={
            "question": "How do I request maintenance?",
            "k": 5,
            "collections": ["Default"],
            "rerank": True,
        },
    )

    assert response.status_code == HTTP_OK
    assert captured["k"] == EXPECTED_RETRIEVER_K
    assert captured["collections"] == ["default"]
    assert captured["rerank"] is True
    body = response.json()
    assert body["hits"][0]["rank"] == 1
    assert body["hits"][0]["preview"] == "Maintenance portal details."
    assert body["hits"][0]["filename"] == "tenant-handbook.pdf"


def test_search_rejects_empty_question():
    response = client.post("/search", json={"question": "   "})

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_search_returns_502_when_retrieval_fails(monkeypatch):
    class FailingRetriever:
        def invoke(self, question):
            raise RuntimeError("vector store down")

    monkeypatch.setattr(main, "select_retriever", lambda **kwargs: FailingRetriever())

    response = client.post("/search", json={"question": "Hello"})

    assert response.status_code == HTTP_BAD_GATEWAY


def test_search_with_score_threshold_filters_hits(monkeypatch):
    class ScoredRetriever:
        def invoke(self, question):
            return [
                SimpleNamespace(
                    page_content="High confidence chunk",
                    metadata={"file_id": 1, "filename": "high.pdf", "score": 0.85},
                ),
                SimpleNamespace(
                    page_content="Low confidence chunk",
                    metadata={"file_id": 2, "filename": "low.pdf", "score": 0.25},
                ),
            ]

    monkeypatch.setattr(main, "select_retriever", lambda **kwargs: ScoredRetriever())

    response = client.post(
        "/search",
        json={"question": "Test query", "score_threshold": 0.5},
    )
    assert response.status_code == HTTP_OK
    hits = response.json()["hits"]
    expected_hits = 1
    assert len(hits) == expected_hits
    assert hits[0]["filename"] == "high.pdf"
    expected_score = 0.85
    assert hits[0]["score"] == expected_score

    # Validation: score_threshold must be between 0.0 and 1.0
    res_neg = client.post("/search", json={"question": "Test", "score_threshold": -0.1})
    assert res_neg.status_code == HTTP_UNPROCESSABLE_ENTITY

    res_large = client.post("/search", json={"question": "Test", "score_threshold": 1.1})
    assert res_large.status_code == HTTP_UNPROCESSABLE_ENTITY


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


def test_delete_document_removes_source_text(monkeypatch):
    removed_sources = []
    monkeypatch.setattr(main, "get_document_record", lambda file_id: {"id": file_id})
    monkeypatch.setattr(main, "delete_doc_from_chroma", lambda file_id: True)
    monkeypatch.setattr(main, "delete_document_record", lambda file_id: True)
    monkeypatch.setattr(
        main, "delete_document_source", lambda file_id: removed_sources.append(file_id) or True
    )

    response = client.post("/delete-doc", json={"file_id": 55})

    assert response.status_code == HTTP_OK
    assert removed_sources == [55]


def test_delete_collection_removes_source_text(monkeypatch):
    removed = []
    monkeypatch.setattr(main, "delete_collection_from_chroma", lambda collection: 3)
    monkeypatch.setattr(main, "delete_documents_by_collection", lambda collection: 2)
    monkeypatch.setattr(
        main,
        "delete_document_sources_by_collection",
        lambda collection: removed.append(collection) or True,
    )

    response = client.delete("/collections/acme")

    assert response.status_code == HTTP_OK
    assert removed == ["acme"]


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
            # Unreachable yield keeps this a true async generator so the
            # failure surfaces mid-iteration like a real chain error.
            yield {}  # pragma: no cover

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


def test_get_document_details_success(monkeypatch):
    file_id = 42
    expected_chunk_count = 2
    fake_record = {
        "id": file_id,
        "filename": "lease.pdf",
        "collection": "clients-acme",
        "sha256": "abcdef123456",
        "upload_timestamp": "2026-09-18 12:00:00",
    }
    fake_chunks = [
        {
            "chunk_id": "42:0",
            "chunk_index": 0,
            "page": 1,
            "content": "Paragraph one content",
            "preview": "Paragraph one content",
        },
        {
            "chunk_id": "42:1",
            "chunk_index": 1,
            "page": 2,
            "content": "Paragraph two content",
            "preview": "Paragraph two content",
        },
    ]
    monkeypatch.setattr(
        main, "get_document_record", lambda fid: fake_record if fid == file_id else None
    )
    monkeypatch.setattr(
        main, "get_doc_chunks_from_chroma", lambda fid: fake_chunks if fid == file_id else []
    )

    response = client.get(f"/docs/{file_id}")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["id"] == file_id
    assert data["filename"] == "lease.pdf"
    assert data["collection"] == "clients-acme"
    assert data["sha256"] == "abcdef123456"
    assert data["chunk_count"] == expected_chunk_count
    assert len(data["chunks"]) == expected_chunk_count
    assert data["chunks"][0]["chunk_id"] == "42:0"
    assert data["chunks"][0]["page"] == 1


def test_get_document_details_not_found(monkeypatch):
    monkeypatch.setattr(main, "get_document_record", lambda fid: None)
    response = client.get("/docs/999")
    assert response.status_code == HTTP_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_get_document_details_includes_chunking_options(monkeypatch):
    file_id = 42
    expected_chunk_size = 500
    expected_chunk_overlap = 50
    fake_record = {
        "id": file_id,
        "filename": "lease.pdf",
        "collection": "default",
        "sha256": "abcdef",
        "upload_timestamp": "2026-09-28T00:00:00Z",
    }
    fake_source = {
        "file_id": file_id,
        "source_text": "Sample text",
        "strategy": "semantic",
        "chunk_size": expected_chunk_size,
        "chunk_overlap": expected_chunk_overlap,
    }
    monkeypatch.setattr(
        main, "get_document_record", lambda fid: fake_record if fid == file_id else None
    )
    monkeypatch.setattr(main, "get_doc_chunks_from_chroma", lambda fid: [])
    monkeypatch.setattr(
        main, "get_document_source", lambda fid: fake_source if fid == file_id else None
    )

    response = client.get(f"/docs/{file_id}")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["chunking_strategy"] == "semantic"
    assert data["chunk_size"] == expected_chunk_size
    assert data["chunk_overlap"] == expected_chunk_overlap


def test_rechunk_document_route_success(monkeypatch):
    file_id = 42
    target_size = 600
    target_overlap = 60
    fake_record = {
        "id": file_id,
        "filename": "lease.pdf",
        "collection": "clients-acme",
        "sha256": "hash123",
        "upload_timestamp": "2026-09-28T00:00:00Z",
    }
    fake_source = {
        "file_id": file_id,
        "source_text": "First page text. Second page text.",
        "strategy": "recursive",
        "chunk_size": 1000,
        "chunk_overlap": 200,
    }
    reindexed_calls = []
    saved_sources = []

    monkeypatch.setattr(
        main, "get_document_record", lambda fid: fake_record if fid == file_id else None
    )
    monkeypatch.setattr(
        main, "get_document_source", lambda fid: fake_source if fid == file_id else None
    )
    monkeypatch.setattr(
        main,
        "reindex_chunks_in_chroma",
        lambda file_id, source_text, filename, collection, options: reindexed_calls.append(
            (file_id, filename, collection, options)
        )
        or True,
    )
    monkeypatch.setattr(
        main,
        "save_document_source",
        lambda *args, **kwargs: saved_sources.append((args, kwargs)),
    )
    fake_doc_chunks = [
        {"chunk_id": f"{file_id}:0", "chunk_index": 0, "preview": "P1", "content": "Text 1"},
        {"chunk_id": f"{file_id}:1", "chunk_index": 1, "preview": "P2", "content": "Text 2"},
    ]
    monkeypatch.setattr(
        main,
        "get_doc_chunks_from_chroma",
        lambda fid: fake_doc_chunks if fid == file_id else [],
    )

    response = client.post(
        f"/docs/{file_id}/rechunk",
        json={
            "chunking_strategy": "semantic",
            "chunk_size": target_size,
            "chunk_overlap": target_overlap,
        },
    )
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["id"] == file_id
    assert data["filename"] == "lease.pdf"
    assert data["collection"] == "clients-acme"
    expected_chunks = 2
    assert data["chunk_count"] == expected_chunks
    assert data["chunking_strategy"] == "semantic"
    assert data["chunk_size"] == target_size
    assert data["chunk_overlap"] == target_overlap

    assert len(reindexed_calls) == 1
    assert reindexed_calls[0][0] == file_id
    assert reindexed_calls[0][1] == "lease.pdf"
    assert reindexed_calls[0][2] == "clients-acme"
    assert reindexed_calls[0][3].strategy.value == "semantic"

    assert len(saved_sources) == 1
    assert saved_sources[0][1]["file_id"] == file_id
    assert saved_sources[0][1]["strategy"] == "semantic"
    assert saved_sources[0][1]["chunk_size"] == target_size
    assert saved_sources[0][1]["chunk_overlap"] == target_overlap


def test_rechunk_document_route_not_found(monkeypatch):
    monkeypatch.setattr(main, "get_document_record", lambda fid: None)
    response = client.post("/docs/999/rechunk", json={})
    assert response.status_code == HTTP_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_rechunk_document_route_no_source_text(monkeypatch):
    file_id = 42
    monkeypatch.setattr(
        main, "get_document_record", lambda fid: {"id": fid, "filename": "doc.pdf"}
    )
    monkeypatch.setattr(main, "get_document_source", lambda fid: None)

    response = client.post(f"/docs/{file_id}/rechunk", json={})
    assert response.status_code == HTTP_BAD_REQUEST
    assert "not available" in response.json()["detail"].lower()


def test_rechunk_document_route_invalid_chunk_params():
    # Test invalid overlap >= chunk_size
    response = client.post("/docs/42/rechunk", json={"chunk_size": 200, "chunk_overlap": 200})
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY

    # Test chunk_size below minimum (100)
    response_small = client.post("/docs/42/rechunk", json={"chunk_size": 50})
    assert response_small.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_rechunk_document_route_reindex_failure(monkeypatch):
    file_id = 42
    fake_record = {"id": file_id, "filename": "lease.pdf", "collection": "default"}
    fake_source = {"file_id": file_id, "source_text": "Text"}

    monkeypatch.setattr(main, "get_document_record", lambda fid: fake_record)
    monkeypatch.setattr(main, "get_document_source", lambda fid: fake_source)
    monkeypatch.setattr(main, "reindex_chunks_in_chroma", lambda *args, **kwargs: False)

    response = client.post(f"/docs/{file_id}/rechunk", json={})
    assert response.status_code == HTTP_INTERNAL_ERROR
    assert "failed to re-chunk" in response.json()["detail"].lower()



def test_delete_many_documents_success(monkeypatch):
    first_id = 42
    second_id = 43
    expected_deleted = 2

    monkeypatch.setattr(main, "get_document_record", lambda fid: {"id": fid, "filename": "doc.pdf"})
    monkeypatch.setattr(main, "delete_doc_from_chroma", lambda fid: True)
    monkeypatch.setattr(main, "delete_document_record", lambda fid: True)

    response = client.post("/delete-docs", json={"file_ids": [first_id, second_id]})
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["deleted"] == expected_deleted
    assert data["failed"] == 0
    assert len(data["results"]) == expected_deleted
    assert all(r["status"] == "deleted" for r in data["results"])


def test_delete_many_documents_mixed(monkeypatch):
    first_id = 42
    second_id = 43
    third_id = 44
    expected_failed = 2

    def fake_get(fid):
        if fid == second_id:
            return None
        return {"id": fid, "filename": f"{fid}.pdf"}

    def fake_chroma(fid):
        return fid != third_id

    monkeypatch.setattr(main, "get_document_record", fake_get)
    monkeypatch.setattr(main, "delete_doc_from_chroma", fake_chroma)
    monkeypatch.setattr(main, "delete_document_record", lambda fid: True)

    response = client.post("/delete-docs", json={"file_ids": [first_id, second_id, third_id]})
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["deleted"] == 1
    assert data["failed"] == expected_failed
    status_map = {r["file_id"]: r["status"] for r in data["results"]}
    assert status_map[first_id] == "deleted"
    assert status_map[second_id] == "not_found"
    assert status_map[third_id] == "error"


def test_delete_many_documents_validation():
    response = client.post("/delete-docs", json={"file_ids": []})
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY

    response = client.post("/delete-docs", json={"file_ids": [0]})
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_search_sessions_route_success(monkeypatch):
    fake_results = [
        {
            "session_id": "session-1",
            "label": "Maintenance",
            "match_count": 2,
            "preview": "How do I fix the plumbing?",
            "last_active": "2026-09-18 12:00:00",
            "matched_queries": ["How do I fix the plumbing?"],
        }
    ]
    monkeypatch.setattr(main, "search_sessions", lambda query, limit=20: fake_results)

    response = client.get("/sessions/search?q=plumbing")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["query"] == "plumbing"
    assert len(data["results"]) == 1
    assert data["results"][0]["session_id"] == "session-1"
    expected_matches = 2
    assert data["results"][0]["match_count"] == expected_matches
    assert data["results"][0]["matched_queries"] == ["How do I fix the plumbing?"]


def test_search_sessions_route_rejects_empty_query():
    response = client.get("/sessions/search?q=   ")
    assert response.status_code == HTTP_BAD_REQUEST
    assert "must not be empty" in response.json()["detail"].lower()


def test_search_sessions_route_validates_limit():
    response = client.get("/sessions/search?q=plumbing&limit=0")
    assert response.status_code == HTTP_BAD_REQUEST

    response = client.get("/sessions/search?q=plumbing&limit=101")
    assert response.status_code == HTTP_BAD_REQUEST


def test_delete_many_sessions_success(monkeypatch):
    expected_count = 2
    monkeypatch.setattr(main, "delete_sessions", lambda sids: dict.fromkeys(sids, "deleted"))
    response = client.post("/delete-sessions", json={"session_ids": ["s1", "s2"]})
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["deleted"] == expected_count
    assert data["failed"] == 0
    assert len(data["results"]) == expected_count
    assert all(r["status"] == "deleted" for r in data["results"])


def test_delete_many_sessions_mixed(monkeypatch):
    expected_deleted = 1
    expected_failed = 2
    monkeypatch.setattr(
        main,
        "delete_sessions",
        lambda sids: {"s1": "deleted", "s2": "not_found", "s3": "error"},
    )
    response = client.post("/delete-sessions", json={"session_ids": ["s1", "s2", "s3"]})
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["deleted"] == expected_deleted
    assert data["failed"] == expected_failed
    status_map = {r["session_id"]: r["status"] for r in data["results"]}
    assert status_map == {"s1": "deleted", "s2": "not_found", "s3": "error"}


def test_delete_many_sessions_validation():
    response = client.post("/delete-sessions", json={"session_ids": []})
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY

    response = client.post("/delete-sessions", json={"session_ids": ["   "]})
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_delete_many_sessions_server_error(monkeypatch):
    def boom(sids):
        raise RuntimeError("database locked")

    monkeypatch.setattr(main, "delete_sessions", boom)
    response = client.post("/delete-sessions", json={"session_ids": ["s1"]})
    assert response.status_code == HTTP_INTERNAL_ERROR
    assert "Failed to delete sessions" in response.json()["detail"]


def test_get_support_triage_analytics_route(monkeypatch):
    expected_data = {
        "total_sessions": 5,
        "active_count": 2,
        "resolved_count": 2,
        "escalated_count": 1,
        "closed_count": 0,
        "resolution_rate": 40.0,
        "escalation_rate": 20.0,
        "avg_turns_per_session": 3.2,
        "top_tags": [{"tag": "lease", "count": 3}, {"tag": "urgent", "count": 2}],
    }
    monkeypatch.setattr(main, "get_support_triage_analytics", lambda: expected_data)

    response = client.get("/sessions/triage-analytics")
    assert response.status_code == HTTP_OK
    data = response.json()
    expected_total = 5
    expected_rate = 40.0
    expected_tag_count = 3
    assert data["total_sessions"] == expected_total
    assert data["resolution_rate"] == expected_rate
    assert data["top_tags"][0]["tag"] == "lease"
    assert data["top_tags"][0]["count"] == expected_tag_count


def test_summarize_session_route_not_found(monkeypatch):
    monkeypatch.setattr(main, "get_chat_history", lambda sid: [])
    response = client.post("/sessions/nonexistent/summarize")
    assert response.status_code == HTTP_NOT_FOUND


def test_summarize_session_route_success(monkeypatch):
    fake_history = [
        {"role": "human", "content": "How do I cancel my lease agreement?"},
        {"role": "ai", "content": "You must provide 30-day notice."},
    ]
    monkeypatch.setattr(main, "get_chat_history", lambda sid: fake_history)

    saved_metadata = {}

    def fake_update(session_id, **kwargs):
        saved_metadata.update(kwargs)
        return True

    monkeypatch.setattr(main, "update_session_metadata", fake_update)
    monkeypatch.setattr(main, "get_session_metadata", lambda sid: {"tags": "tenant"})

    response = client.post("/sessions/s1/summarize", json={"save_summary": True})
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["session_id"] == "s1"
    assert "cancel my lease agreement" in data["summary"]
    assert "lease" in data["suggested_tags"]
    assert data["saved"] is True
    assert saved_metadata.get("summary") == data["summary"]
    tags_str = str(saved_metadata.get("tags", ""))
    assert "lease" in tags_str
    assert "tenant" in tags_str


def test_summarize_session_route_unsaved(monkeypatch):
    fake_history = [{"role": "human", "content": "Hello"}]
    monkeypatch.setattr(main, "get_chat_history", lambda sid: fake_history)

    called = False

    def fake_update(*args, **kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(main, "update_session_metadata", fake_update)

    response = client.post("/sessions/s2/summarize", json={"save_summary": False})
    assert response.status_code == HTTP_OK
    assert response.json()["saved"] is False
    assert called is False


def test_patch_session_summary_and_resolution_notes(monkeypatch):
    session_id = "s-42"
    fake_summary = {
        "session_id": session_id,
        "message_count": 2,
        "last_active": "2026-09-30T10:00:00",
        "preview": "Test question",
        "label": "Ticket 42",
        "status": "resolved",
        "tags": "lease, refund",
        "summary": "Resolved billing discrepancy.",
        "resolution_notes": "Issued $50 refund.",
    }
    monkeypatch.setattr(main, "update_session_metadata", lambda sid, **kwargs: True)
    monkeypatch.setattr(main, "_get_session_summary_or_404", lambda sid: fake_summary)

    response = client.patch(
        f"/sessions/{session_id}",
        json={
            "status": "resolved",
            "summary": "Resolved billing discrepancy.",
            "resolution_notes": "Issued $50 refund.",
        },
    )
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["status"] == "resolved"
    assert data["summary"] == "Resolved billing discrepancy."
    assert data["resolution_notes"] == "Issued $50 refund."


def test_export_session_includes_resolution_details(monkeypatch):
    session_id = "s-export"
    fake_summary = {
        "session_id": session_id,
        "label": "Move-out request",
        "status": "resolved",
        "tags": "lease, moveout",
        "summary": "Tenant requested early move-out date.",
        "resolution_notes": "Inspection scheduled for Friday.",
    }
    fake_history = [
        {"role": "human", "content": "Can I move out early?"},
        {"role": "ai", "content": "Yes, following inspection."},
    ]
    monkeypatch.setattr(main, "_get_session_summary_or_404", lambda sid: fake_summary)
    monkeypatch.setattr(main, "get_chat_history", lambda sid: fake_history)

    # Markdown export includes details
    resp_md = client.get(f"/sessions/{session_id}/export?format=markdown")
    assert resp_md.status_code == HTTP_OK
    assert "- Status: resolved" in resp_md.text
    assert "- Summary: Tenant requested early move-out date." in resp_md.text
    assert "- Resolution Notes: Inspection scheduled for Friday." in resp_md.text

    # JSON export includes details
    resp_json = client.get(f"/sessions/{session_id}/export?format=json")
    assert resp_json.status_code == HTTP_OK
    json_data = resp_json.json()
    assert json_data["status"] == "resolved"
    assert json_data["summary"] == "Tenant requested early move-out date."
    assert json_data["resolution_notes"] == "Inspection scheduled for Friday."

    # CSV export includes details
    resp_csv = client.get(f"/sessions/{session_id}/export?format=csv")
    assert resp_csv.status_code == HTTP_OK
    assert "Move-out request" in resp_csv.text
    assert "Inspection scheduled for Friday." in resp_csv.text


def test_register_webhook_route(monkeypatch):
    fake_hook = {
        "id": 1,
        "url": "https://example.com/alerts",
        "events": "*",
        "secret": "whsec_123",
        "is_active": True,
        "failure_count": 0,
        "created_at": "2026-10-01T00:00:00Z",
    }
    monkeypatch.setattr(main, "create_webhook", lambda **kwargs: fake_hook)

    response = client.post(
        "/webhooks",
        json={"url": "https://example.com/alerts", "secret": "whsec_123"},
    )
    assert response.status_code == HTTP_CREATED
    data = response.json()
    assert data["id"] == 1
    assert data["url"] == "https://example.com/alerts"
    assert data["is_active"] is True

    # Bad URL fails validation
    bad_resp = client.post("/webhooks", json={"url": "invalid-url"})
    assert bad_resp.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_list_webhooks_route(monkeypatch):
    fake_hooks = [
        {
            "id": 1,
            "url": "https://example.com/h1",
            "events": "*",
            "secret": "",
            "is_active": True,
            "failure_count": 0,
            "created_at": "2026-10-01T00:00:00Z",
        }
    ]
    monkeypatch.setattr(main, "list_webhooks", lambda **kwargs: fake_hooks)

    response = client.get("/webhooks")
    assert response.status_code == HTTP_OK
    assert len(response.json()) == 1


def test_get_and_delete_webhook_routes(monkeypatch):
    fake_hook = {
        "id": 1,
        "url": "https://example.com/h1",
        "events": "*",
        "secret": "",
        "is_active": True,
        "failure_count": 0,
        "created_at": "2026-10-01T00:00:00Z",
    }
    monkeypatch.setattr(main, "get_webhook", lambda wid: fake_hook if wid == 1 else None)
    monkeypatch.setattr(main, "delete_webhook", lambda wid: wid == 1)

    # Get found
    resp = client.get("/webhooks/1")
    assert resp.status_code == HTTP_OK
    assert resp.json()["id"] == 1

    # Get not found
    resp_404 = client.get("/webhooks/999")
    assert resp_404.status_code == HTTP_NOT_FOUND

    # Delete found
    del_resp = client.delete("/webhooks/1")
    assert del_resp.status_code == HTTP_OK

    # Delete not found
    del_404 = client.delete("/webhooks/999")
    assert del_404.status_code == HTTP_NOT_FOUND


def test_update_webhook_route(monkeypatch):
    fake_updated = {
        "id": 1,
        "url": "https://example.com/new",
        "events": "session.escalated",
        "secret": "new-sec",
        "is_active": False,
        "failure_count": 0,
        "created_at": "2026-10-01T00:00:00Z",
    }
    monkeypatch.setattr(
        main,
        "update_webhook",
        lambda webhook_id, **kwargs: fake_updated if webhook_id == 1 else None,
    )

    resp = client.patch(
        "/webhooks/1",
        json={
            "url": "https://example.com/new",
            "events": "session.escalated",
            "reset_failures": True,
        },
    )
    assert resp.status_code == HTTP_OK
    assert resp.json()["url"] == "https://example.com/new"

    # Not found
    resp_404 = client.patch("/webhooks/999", json={"url": "https://example.com/new"})
    assert resp_404.status_code == HTTP_NOT_FOUND


def test_ping_webhook_route(monkeypatch):
    fake_ping = {
        "webhook_id": 1,
        "url": "https://example.com/ping",
        "event": "ping",
        "status_code": 200,
        "success": True,
        "error": None,
    }

    def stub_ping(wid):
        if wid == 1:
            return fake_ping
        raise ValueError("Webhook not found.")

    monkeypatch.setattr(main.webhooks, "ping_webhook", stub_ping)

    resp = client.post("/webhooks/1/ping")
    assert resp.status_code == HTTP_OK
    assert resp.json()["success"] is True

    resp_404 = client.post("/webhooks/999/ping")
    assert resp_404.status_code == HTTP_NOT_FOUND


def test_list_webhook_deliveries_route(monkeypatch):
    fake_logs = [
        {
            "id": 1,
            "webhook_id": 1,
            "event": "session.escalated",
            "url": "https://example.com/hook",
            "status_code": 200,
            "success": True,
            "payload_preview": "preview",
            "error_message": None,
            "delivered_at": "2026-10-01T00:00:00Z",
        }
    ]
    monkeypatch.setattr(main, "get_webhook_delivery_logs", lambda **kwargs: (fake_logs, 1))

    resp = client.get("/webhooks/deliveries?limit=10&offset=0")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1

    # Bad limit
    assert client.get("/webhooks/deliveries?limit=0").status_code == HTTP_BAD_REQUEST
    assert client.get("/webhooks/deliveries?limit=101").status_code == HTTP_BAD_REQUEST
    assert client.get("/webhooks/deliveries?offset=-1").status_code == HTTP_BAD_REQUEST


def test_feedback_negative_triggers_webhook(monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        main.webhooks,
        "dispatch_event",
        lambda ev, data: dispatched.append((ev, data)),
    )
    monkeypatch.setattr(
        main, "get_chat_history", lambda sid: [{"role": "human", "content": "Hi"}]
    )
    monkeypatch.setattr(main, "insert_feedback", lambda sid, rating, comment: 42)

    # Positive feedback does not dispatch
    resp_pos = client.post("/feedback", json={"session_id": "s-1", "rating": 1})
    assert resp_pos.status_code == HTTP_OK
    assert len(dispatched) == 0

    # Negative feedback dispatches feedback.negative
    resp_neg = client.post(
        "/feedback",
        json={"session_id": "s-1", "rating": -1, "comment": "Unhelpful"},
    )
    assert resp_neg.status_code == HTTP_OK
    assert len(dispatched) == 1
    assert dispatched[0][0] == "feedback.negative"
    assert dispatched[0][1]["session_id"] == "s-1"
    assert dispatched[0][1]["rating"] == -1


def test_session_status_update_triggers_webhooks(monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        main.webhooks,
        "dispatch_event",
        lambda ev, data: dispatched.append((ev, data)),
    )
    monkeypatch.setattr(
        main, "get_chat_history", lambda sid: [{"role": "human", "content": "Hi"}]
    )

    state = {"status": "active", "label": "Session 1", "session_id": "s-1"}

    def fake_get_summary(sid):
        return {
            "session_id": sid,
            "label": state.get("label"),
            "status": state.get("status", "active"),
            "tags": "",
            "summary": "",
            "resolution_notes": "",
            "message_count": 1,
            "last_active": "2026-10-01",
            "preview": "Hi",
        }

    def fake_update(sid, **kwargs):
        if kwargs.get("status"):
            state["status"] = kwargs["status"]
        if kwargs.get("label"):
            state["label"] = kwargs["label"]
        return True

    monkeypatch.setattr(main, "_get_session_summary_or_404", fake_get_summary)
    monkeypatch.setattr(main, "update_session_metadata", fake_update)

    # Escalating triggers session.escalated
    resp_esc = client.patch("/sessions/s-1", json={"status": "escalated"})
    assert resp_esc.status_code == HTTP_OK
    assert len(dispatched) == 1
    assert dispatched[0][0] == "session.escalated"
    assert dispatched[0][1]["status"] == "escalated"
    assert dispatched[0][1]["previous_status"] == "active"

    # Resolving triggers session.resolved
    resp_res = client.patch("/sessions/s-1", json={"status": "resolved"})
    assert resp_res.status_code == HTTP_OK
    expected_dispatched_count = 2
    assert len(dispatched) == expected_dispatched_count
    assert dispatched[1][0] == "session.resolved"
    assert dispatched[1][1]["status"] == "resolved"
    assert dispatched[1][1]["previous_status"] == "escalated"


def test_create_macro_route(monkeypatch):
    fake_macro = {
        "id": 1,
        "title": "Lease Renewal",
        "shortcut": "/lease-renewal",
        "category": "Leasing",
        "content": "Hello {customer_name}, renewal info.",
        "tags": ["leasing"],
        "status_action": "active",
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
    }
    monkeypatch.setattr(main, "create_macro", lambda **kwargs: fake_macro)

    response = client.post(
        "/macros",
        json={
            "title": "Lease Renewal",
            "shortcut": "/lease-renewal",
            "category": "Leasing",
            "content": "Hello {customer_name}, renewal info.",
            "tags": ["leasing"],
            "status_action": "active",
        },
    )
    assert response.status_code == HTTP_CREATED
    data = response.json()
    assert data["id"] == 1
    assert data["shortcut"] == "/lease-renewal"
    assert data["variables"] == ["customer_name"]

    def fail_create(**kwargs):
        raise ValueError("Macro shortcut '/lease-renewal' already exists.")

    monkeypatch.setattr(main, "create_macro", fail_create)
    fail_resp = client.post(
        "/macros",
        json={
            "title": "Lease Renewal",
            "shortcut": "/lease-renewal",
            "content": "Hello {customer_name}",
        },
    )
    assert fail_resp.status_code == HTTP_BAD_REQUEST


def test_list_and_get_macros_routes(monkeypatch):
    target_id = 10
    fake_macro = {
        "id": target_id,
        "title": "Emergency Maintenance",
        "shortcut": "/emerg-maint",
        "category": "Maintenance",
        "content": "Hello {customer_name}, unit {unit_id}.",
        "tags": ["maintenance", "emergency"],
        "status_action": "escalated",
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
    }
    monkeypatch.setattr(main, "list_macros", lambda **kwargs: [fake_macro])
    monkeypatch.setattr(main, "list_macro_categories", lambda: ["Maintenance", "Leasing"])
    monkeypatch.setattr(
        main, "get_macro", lambda mid: fake_macro if mid == target_id else None
    )

    resp_list = client.get("/macros?category=Maintenance")
    assert resp_list.status_code == HTTP_OK
    assert len(resp_list.json()) == 1

    resp_cats = client.get("/macros/categories")
    assert resp_cats.status_code == HTTP_OK
    assert "Maintenance" in resp_cats.json()["categories"]

    resp_get = client.get(f"/macros/{target_id}")
    assert resp_get.status_code == HTTP_OK
    assert resp_get.json()["id"] == target_id
    assert resp_get.json()["shortcut"] == "/emerg-maint"

    resp_404 = client.get("/macros/999")
    assert resp_404.status_code == HTTP_NOT_FOUND


def test_update_and_delete_macro_routes(monkeypatch):
    target_id = 10
    fake_macro = {
        "id": target_id,
        "title": "Updated Title",
        "shortcut": "/new-sc",
        "category": "General",
        "content": "Updated content.",
        "tags": ["tag1"],
        "status_action": "resolved",
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
    }

    def fake_update(macro_id, **kwargs):
        if macro_id == target_id:
            if kwargs.get("shortcut") == "/taken":
                raise ValueError("Macro shortcut is already taken.")
            return fake_macro
        return None

    monkeypatch.setattr(main, "update_macro", fake_update)
    monkeypatch.setattr(main, "delete_macro", lambda mid: mid == target_id)

    resp_up = client.patch(f"/macros/{target_id}", json={"title": "Updated Title"})
    assert resp_up.status_code == HTTP_OK
    assert resp_up.json()["title"] == "Updated Title"

    resp_collision = client.patch(f"/macros/{target_id}", json={"shortcut": "/taken"})
    assert resp_collision.status_code == HTTP_BAD_REQUEST

    resp_up_404 = client.patch("/macros/999", json={"title": "No"})
    assert resp_up_404.status_code == HTTP_NOT_FOUND

    resp_del = client.delete(f"/macros/{target_id}")
    assert resp_del.status_code == HTTP_OK

    resp_del_404 = client.delete("/macros/999")
    assert resp_del_404.status_code == HTTP_NOT_FOUND


def test_render_macro_route(monkeypatch):
    fake_macro = {
        "id": 1,
        "title": "Notice",
        "shortcut": "/notice",
        "category": "General",
        "content": "Hello {customer_name}, unit {unit_id}.",
        "tags": [],
        "status_action": "active",
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
    }
    monkeypatch.setattr(main, "get_macro", lambda mid: fake_macro if mid == 1 else None)

    resp = client.post(
        "/macros/1/render",
        json={"variables": {"customer_name": "Dave", "unit_id": "3A"}},
    )
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["macro_id"] == 1
    assert data["rendered_content"] == "Hello Dave, unit 3A."
    assert data["unresolved_variables"] == []

    resp_404 = client.post("/macros/999/render", json={})
    assert resp_404.status_code == HTTP_NOT_FOUND


def test_apply_macro_to_session_route(monkeypatch):
    target_macro_id = 5
    dispatched = []
    logged_messages = []
    updated_metadata = []

    fake_macro = {
        "id": target_macro_id,
        "title": "Resolve Ticket",
        "shortcut": "/resolve",
        "category": "General",
        "content": "Hello {customer_name}, ticket resolved for {session_id}.",
        "tags": ["resolved", "macro-tag"],
        "status_action": "resolved",
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
    }

    session_summary = {
        "session_id": "sess-42",
        "label": "Help request",
        "status": "active",
        "tags": ["initial"],
        "summary": "Tenant asked about payment.",
        "resolution_notes": "",
    }

    monkeypatch.setattr(
        main,
        "_get_session_summary_or_404",
        lambda sid: session_summary if sid == "sess-42" else None,
    )
    monkeypatch.setattr(
        main, "get_macro", lambda mid: fake_macro if mid == target_macro_id else None
    )
    monkeypatch.setattr(
        main, "get_macro_by_shortcut", lambda sc: fake_macro if sc == "/resolve" else None
    )
    monkeypatch.setattr(
        main,
        "insert_application_logs",
        lambda session_id, user_query, gpt_response, model: logged_messages.append(
            (session_id, user_query, gpt_response)
        ),
    )
    monkeypatch.setattr(
        main,
        "update_session_metadata",
        lambda session_id, status=None, tags=None: updated_metadata.append(
            (session_id, status, tags)
        ),
    )
    monkeypatch.setattr(
        main.webhooks,
        "dispatch_event",
        lambda ev, data: dispatched.append((ev, data)),
    )

    resp = client.post(
        "/sessions/sess-42/apply-macro",
        json={
            "macro_id": target_macro_id,
            "variables": {"customer_name": "Alice"},
            "update_status": True,
            "append_tags": True,
        },
    )
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["macro_id"] == target_macro_id
    assert data["session_id"] == "sess-42"
    assert "Hello Alice, ticket resolved for sess-42." in data["rendered_content"]
    assert data["applied_status"] == "resolved"
    assert "resolved" in data["applied_tags"]

    assert len(logged_messages) == 1
    assert "[Applied Macro: Resolve Ticket]" in logged_messages[0][1]

    assert len(updated_metadata) == 1
    assert updated_metadata[0][1] == "resolved"
    assert "initial" in updated_metadata[0][2]
    assert "macro-tag" in updated_metadata[0][2]

    assert len(dispatched) == 1
    assert dispatched[0][0] == "session.resolved"
    assert dispatched[0][1]["session_id"] == "sess-42"

    resp_macro_404 = client.post(
        "/sessions/sess-42/apply-macro",
        json={"macro_id": 999},
    )
    assert resp_macro_404.status_code == HTTP_NOT_FOUND


def test_suggest_macros_route(monkeypatch):
    fake_macros = [
        {
            "id": 1,
            "title": "Emergency Maintenance Dispatch",
            "shortcut": "/emerg-maint",
            "category": "Maintenance",
            "content": "Emergency dispatch for {unit_id}. Call {support_contact}.",
            "tags": ["maintenance", "urgent", "emergency"],
            "status_action": "escalated",
        },
        {
            "id": 2,
            "title": "Online Rent Payment",
            "shortcut": "/rent-pay",
            "category": "Billing",
            "content": "Pay rent online via resident portal.",
            "tags": ["billing", "rent"],
            "status_action": "resolved",
        },
    ]

    monkeypatch.setattr(main, "list_macros", lambda **kwargs: fake_macros)

    # Valid suggest request
    resp = client.post(
        "/macros/suggest",
        json={
            "query": "Help, there is flooding in unit 402!",
            "session_id": "sess-leak-1",
            "top_k": 3,
            "min_score": 0.3,
        },
    )
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["detected_intent"] == "maintenance_emergency"
    assert data["extracted_variables"]["unit_id"] == "Unit 402"
    assert data["extracted_variables"]["session_id"] == "sess-leak-1"
    assert data["total_matches"] >= 1
    assert data["suggestions"][0]["shortcut"] == "/emerg-maint"
    assert "Unit 402" in data["suggestions"][0]["rendered_preview"]

    # Category filter
    resp_cat = client.post(
        "/macros/suggest",
        json={
            "query": "Pay rent online",
            "category": "Billing",
        },
    )
    assert resp_cat.status_code == HTTP_OK

    # Empty query validation failure
    resp_bad = client.post("/macros/suggest", json={"query": "   "})
    assert resp_bad.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_get_session_macro_suggestions_route(monkeypatch):
    fake_macros = [
        {
            "id": 1,
            "title": "Emergency Maintenance Dispatch",
            "shortcut": "/emerg-maint",
            "category": "Maintenance",
            "content": "Dispatched for {unit_id}. Ref {session_id}.",
            "tags": ["urgent"],
            "status_action": "escalated",
        }
    ]

    session_summary = {
        "session_id": "sess-active-99",
        "label": "Tenant question",
        "status": "active",
        "tags": [],
        "summary": "",
        "resolution_notes": "",
    }

    def stub_get_summary(sid):
        if sid == "sess-active-99":
            return session_summary
        raise main.HTTPException(status_code=404, detail=f"Session {sid} was not found.")

    monkeypatch.setattr(main, "_get_session_summary_or_404", stub_get_summary)
    monkeypatch.setattr(main, "list_macros", lambda **kwargs: fake_macros)

    # 1. Nonexistent session -> 404
    resp_404 = client.get("/sessions/sess-missing/macro-suggestions")
    assert resp_404.status_code == HTTP_NOT_FOUND

    # 2. Session with no user queries
    monkeypatch.setattr(main, "get_session_latest_user_query", lambda sid: None)
    resp_empty = client.get("/sessions/sess-active-99/macro-suggestions")
    assert resp_empty.status_code == HTTP_OK
    data_empty = resp_empty.json()
    assert data_empty["latest_query"] is None
    assert data_empty["total_matches"] == 0
    assert data_empty["suggestions"] == []

    # 3. Session with user query
    monkeypatch.setattr(
        main,
        "get_session_latest_user_query",
        lambda sid: "Pipe broke in Apt 5B, water leaking",
    )
    resp_query = client.get("/sessions/sess-active-99/macro-suggestions?top_k=2&min_score=0.2")
    assert resp_query.status_code == HTTP_OK
    data_query = resp_query.json()
    assert data_query["latest_query"] == "Pipe broke in Apt 5B, water leaking"
    assert data_query["detected_intent"] == "maintenance_emergency"
    assert data_query["extracted_variables"]["unit_id"] == "Unit 5B"
    assert data_query["extracted_variables"]["session_id"] == "sess-active-99"
    assert data_query["total_matches"] >= 1
    assert data_query["suggestions"][0]["shortcut"] == "/emerg-maint"



