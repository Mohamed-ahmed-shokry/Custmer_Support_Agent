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
            "priority": "medium",
            "tags": "",
            "summary": None,
            "resolution_notes": None,
            "assigned_agent": None,
            "escalation_tier": "tier_1",
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


def test_sla_policies_crud_routes(monkeypatch):
    fake_policy = {
        "id": 1,
        "name": "Emergency Maintenance",
        "priority": "urgent",
        "category": "maintenance",
        "response_time_minutes": 15,
        "resolution_time_minutes": 120,
        "is_active": True,
        "created_at": "2026-10-08 10:00:00",
        "updated_at": "2026-10-08 10:00:00",
    }

    monkeypatch.setattr(main, "list_sla_policies", lambda **kwargs: [fake_policy])
    monkeypatch.setattr(main, "create_sla_policy", lambda **kwargs: 1)
    monkeypatch.setattr(
        main, "get_sla_policy", lambda pid: fake_policy if pid == 1 else None
    )
    monkeypatch.setattr(main, "update_sla_policy", lambda pid, **kwargs: pid == 1)
    monkeypatch.setattr(main, "delete_sla_policy", lambda pid: pid == 1)

    # 1. List
    resp_list = client.get("/sla/policies")
    assert resp_list.status_code == HTTP_OK
    data_list = resp_list.json()
    expected_count = 1
    assert data_list["total"] == expected_count
    assert len(data_list["items"]) == expected_count
    assert data_list["items"][0]["name"] == "Emergency Maintenance"

    # 2. Create valid
    payload_create = {
        "name": "Emergency Maintenance",
        "priority": "urgent",
        "category": "maintenance",
        "response_time_minutes": 15,
        "resolution_time_minutes": 120,
        "is_active": True,
    }
    resp_create = client.post("/sla/policies", json=payload_create)
    assert resp_create.status_code == HTTP_CREATED
    data_create = resp_create.json()
    assert data_create["id"] == expected_count
    assert data_create["priority"] == "urgent"

    # 3. Create invalid (resolution < response)
    invalid_create = dict(payload_create)
    invalid_create["resolution_time_minutes"] = 5
    resp_invalid = client.post("/sla/policies", json=invalid_create)
    assert resp_invalid.status_code == HTTP_UNPROCESSABLE_ENTITY

    # 4. Get by ID
    resp_get = client.get("/sla/policies/1")
    assert resp_get.status_code == HTTP_OK
    assert resp_get.json()["id"] == expected_count

    resp_get_404 = client.get("/sla/policies/999")
    assert resp_get_404.status_code == HTTP_NOT_FOUND

    # 5. Patch by ID
    resp_patch = client.patch(
        "/sla/policies/1",
        json={"response_time_minutes": 20},
    )
    assert resp_patch.status_code == HTTP_OK

    resp_patch_404 = client.patch(
        "/sla/policies/999",
        json={"response_time_minutes": 20},
    )
    assert resp_patch_404.status_code == HTTP_NOT_FOUND

    # 6. Delete
    resp_del = client.delete("/sla/policies/1")
    assert resp_del.status_code == HTTP_OK

    resp_del_404 = client.delete("/sla/policies/999")
    assert resp_del_404.status_code == HTTP_NOT_FOUND


def test_session_priority_update_route(monkeypatch):
    session_data = {
        "session_id": "sess-prio-1",
        "label": "Water leak inquiry",
        "status": "active",
        "priority": "urgent",
        "tags": "maintenance",
        "summary": "Urgent leak",
        "resolution_notes": None,
        "created_at": "2026-10-08 10:00:00",
        "message_count": 2,
        "last_active": "2026-10-08 10:00:00",
        "preview": "Water leak inquiry",
    }

    updated_called: dict[str, object] = {}

    def fake_update(session_id, **kwargs):
        updated_called.update(kwargs)
        return True

    monkeypatch.setattr(main, "get_all_sessions", lambda: [session_data])
    monkeypatch.setattr(main, "update_session_metadata", fake_update)

    # Valid priority patch
    resp = client.patch(
        "/sessions/sess-prio-1",
        json={"priority": "urgent"},
    )
    assert resp.status_code == HTTP_OK
    assert updated_called.get("priority") == "urgent"

    # Invalid priority patch -> 422
    resp_invalid = client.patch(
        "/sessions/sess-prio-1",
        json={"priority": "invalid-prio"},
    )
    assert resp_invalid.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_session_sla_route(monkeypatch):
    session_data = {
        "session_id": "sess-sla-1",
        "label": "Tenant question",
        "status": "active",
        "priority": "high",
        "tags": ["leasing"],
        "summary": "",
        "resolution_notes": "",
        "created_at": "2026-10-08 10:00:00",
        "message_count": 1,
    }

    fake_sla_status = {
        "session_id": "sess-sla-1",
        "priority": "high",
        "category": "leasing",
        "status": "active",
        "policy_id": 2,
        "policy_name": "High Priority Leasing",
        "response_target_minutes": 60,
        "resolution_target_minutes": 480,
        "session_started_at": "2026-10-08 10:00:00",
        "first_response_at": None,
        "response_due_at": "2026-10-08 11:00:00",
        "resolution_due_at": "2026-10-08 18:00:00",
        "response_met": False,
        "resolution_met": False,
        "response_breached": False,
        "resolution_breached": False,
        "response_approaching": False,
        "resolution_approaching": False,
        "breach_status": "healthy",
        "minutes_to_response_deadline": 45.0,
        "minutes_to_resolution_deadline": 465.0,
    }

    def stub_summary(sid):
        if sid == "sess-sla-1":
            return session_data
        raise main.HTTPException(status_code=404, detail="Not found")

    monkeypatch.setattr(main, "_get_session_summary_or_404", stub_summary)
    monkeypatch.setattr(
        main.sla,
        "calculate_session_sla_status",
        lambda sid: fake_sla_status if sid == "sess-sla-1" else None,
    )

    # 1. Known session
    resp = client.get("/sessions/sess-sla-1/sla")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["session_id"] == "sess-sla-1"
    assert data["breach_status"] == "healthy"
    expected_resp_target = 60
    assert data["response_target_minutes"] == expected_resp_target

    # 2. Unknown session
    resp_404 = client.get("/sessions/unknown-sess/sla")
    assert resp_404.status_code == HTTP_NOT_FOUND


def test_evaluate_sla_alerts_route(monkeypatch):
    fake_result = {
        "total_sessions_checked": 5,
        "alerts_triggered": 1,
        "alerts": [
            {
                "session_id": "sess-breach-1",
                "priority": "urgent",
                "category": "maintenance",
                "event": "sla.breached",
                "breach_type": "response",
                "deadline_due_at": "2026-10-08 10:15:00",
                "minutes_remaining": -10.5,
                "webhooks_dispatched": 1,
            }
        ],
    }

    monkeypatch.setattr(
        main.sla,
        "evaluate_and_dispatch_sla_alerts",
        lambda **kwargs: fake_result,
    )

    resp = client.post(
        "/sla/evaluate-alerts",
        json={"approaching_threshold_minutes": 20},
    )
    assert resp.status_code == HTTP_OK
    data = resp.json()
    expected_checked = 5
    expected_triggered = 1
    assert data["total_sessions_checked"] == expected_checked
    assert data["alerts_triggered"] == expected_triggered
    assert len(data["alerts"]) == expected_triggered
    assert data["alerts"][0]["event"] == "sla.breached"


def test_sla_analytics_route(monkeypatch):
    fake_analytics = {
        "total_tracked_sessions": 10,
        "compliance_rate": 90.0,
        "met_sessions": 7,
        "healthy_sessions": 2,
        "approaching_breach_sessions": 0,
        "breached_sessions": 1,
        "avg_first_response_minutes": 12.4,
        "priority_breakdown": {
            "urgent": {"total": 3, "breached": 0},
            "high": {"total": 4, "breached": 1},
        },
    }

    monkeypatch.setattr(
        main.sla,
        "get_sla_compliance_analytics",
        lambda: fake_analytics,
    )

    resp = client.get("/sla/analytics")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    expected_tracked = 10
    expected_rate = 90.0
    assert data["total_tracked_sessions"] == expected_tracked
    assert data["compliance_rate"] == expected_rate
    assert "urgent" in data["priority_breakdown"]


# =====================================================================
# Tests: Support Agents, Assignment, Workload & Business Hours Routes
# =====================================================================


def test_support_agents_crud_routes(monkeypatch):
    test_agent = {
        "id": "agent_test_1",
        "name": "Test Agent One",
        "email": "test1@example.com",
        "tier": "tier_1",
        "department": "general_leasing",
        "is_active": 1,
        "created_at": "2026-10-11T12:00:00",
        "updated_at": "2026-10-11T12:00:00",
    }
    store = {"agent_test_1": test_agent}

    monkeypatch.setattr(
        main,
        "list_support_agents",
        lambda tier=None, department=None, active_only=False: list(store.values()),
    )
    monkeypatch.setattr(main, "get_support_agent", store.get)
    monkeypatch.setattr(
        main,
        "create_support_agent",
        lambda agent_id, name, email, tier="tier_1", department="general_leasing", is_active=1: (
            store.setdefault(
                agent_id,
                {
                    "id": agent_id,
                    "name": name,
                    "email": email,
                    "tier": tier,
                    "department": department,
                    "is_active": is_active,
                    "created_at": "2026-10-11T12:00:00",
                    "updated_at": "2026-10-11T12:00:00",
                },
            )
        ),
    )
    monkeypatch.setattr(
        main,
        "update_support_agent",
        lambda agent_id, **kwargs: agent_id in store,
    )
    monkeypatch.setattr(
        main,
        "delete_support_agent",
        lambda agent_id: bool(store.pop(agent_id, None)),
    )

    # 1. List agents
    resp_list = client.get("/agents")
    assert resp_list.status_code == HTTP_OK
    data_list = resp_list.json()
    assert data_list["total"] == 1
    assert data_list["items"][0]["id"] == "agent_test_1"

    # 2. Create agent
    new_agent_payload = {
        "id": "agent_test_2",
        "name": "Test Agent Two",
        "email": "test2@example.com",
        "tier": "tier_2",
        "department": "maintenance",
        "is_active": True,
    }
    resp_create = client.post("/agents", json=new_agent_payload)
    assert resp_create.status_code == HTTP_CREATED
    data_created = resp_create.json()
    assert data_created["id"] == "agent_test_2"
    assert data_created["tier"] == "tier_2"

    # 3. Conflict on duplicate agent
    resp_dup = client.post("/agents", json=new_agent_payload)
    assert resp_dup.status_code == HTTP_CONFLICT

    # 4. Get specific agent
    resp_get = client.get("/agents/agent_test_1")
    assert resp_get.status_code == HTTP_OK
    assert resp_get.json()["name"] == "Test Agent One"

    # 5. Get missing agent
    resp_miss = client.get("/agents/nonexistent")
    assert resp_miss.status_code == HTTP_NOT_FOUND

    # 6. Update agent
    resp_up = client.patch(
        "/agents/agent_test_1",
        json={"tier": "tier_3", "is_active": False},
    )
    assert resp_up.status_code == HTTP_OK

    # 7. Delete agent
    resp_del = client.delete("/agents/agent_test_1")
    assert resp_del.status_code == HTTP_OK
    assert "deleted" in resp_del.json()["message"]


def test_agents_workload_route(monkeypatch):
    fake_workload = {
        "agents": [
            {
                "agent": {
                    "id": "agent_sarah",
                    "name": "Sarah Connor",
                    "email": "sarah@example.com",
                    "tier": "tier_1",
                    "department": "general_leasing",
                    "is_active": True,
                },
                "active_sessions_count": 2,
                "resolved_sessions_count": 5,
                "total_sessions_count": 7,
            }
        ],
        "total_active_sessions": 3,
        "unassigned_active_sessions": 1,
        "tier_distribution": {"tier_1": 2, "tier_2": 1, "tier_3": 0},
    }
    monkeypatch.setattr(
        main.assignment,
        "get_agent_workload_analytics",
        lambda: fake_workload,
    )

    resp = client.get("/agents/workload")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    expected_active_sessions = 3
    assert data["total_active_sessions"] == expected_active_sessions
    assert data["unassigned_active_sessions"] == 1
    assert data["agents"][0]["agent"]["id"] == "agent_sarah"


def test_session_assign_and_auto_assign_routes(monkeypatch):
    fake_session = {
        "session_id": "sess-route-assign",
        "message_count": 2,
        "last_active": "2026-10-11T12:00:00",
        "preview": "Test preview",
        "label": "Test Label",
        "status": "active",
        "tags": "leasing",
        "summary": None,
        "resolution_notes": None,
        "priority": "medium",
        "assigned_agent": "agent_sarah",
        "escalation_tier": "tier_1",
    }

    monkeypatch.setattr(main, "_get_session_summary_or_404", lambda sid: fake_session)
    monkeypatch.setattr(
        main.assignment,
        "assign_session",
        lambda **kwargs: {"session_id": kwargs["session_id"], "metadata": fake_session},
    )
    monkeypatch.setattr(
        main.assignment,
        "auto_assign_session",
        lambda **kwargs: {"session_id": kwargs["session_id"], "metadata": fake_session},
    )

    # 1. Manual assign
    resp_assign = client.post(
        "/sessions/sess-route-assign/assign",
        json={
            "agent_id": "agent_sarah",
            "tier": "tier_1",
            "assigned_by": "test_user",
            "reason": "Routing test",
        },
    )
    assert resp_assign.status_code == HTTP_OK
    assert resp_assign.json()["assigned_agent"] == "agent_sarah"

    # 2. Auto assign
    resp_auto = client.post(
        "/sessions/sess-route-assign/auto-assign",
        json={"strategy": "least_busy", "target_tier": "tier_1"},
    )
    assert resp_auto.status_code == HTTP_OK
    assert resp_auto.json()["assigned_agent"] == "agent_sarah"


def test_session_assignment_history_route(monkeypatch):
    fake_history = [
        {
            "id": 1,
            "session_id": "sess-hist",
            "assigned_by": "dispatcher",
            "previous_agent": None,
            "new_agent": "agent_sarah",
            "previous_tier": "tier_1",
            "new_tier": "tier_1",
            "reason": "Initial queue routing",
            "assigned_at": "2026-10-11T12:00:00",
        }
    ]
    monkeypatch.setattr(
        main,
        "_get_session_summary_or_404",
        lambda sid: {"session_id": sid, "status": "active"},
    )
    monkeypatch.setattr(
        main,
        "get_session_assignment_history",
        lambda session_id, limit=50: fake_history,
    )

    resp = client.get("/sessions/sess-hist/assignment-history")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["session_id"] == "sess-hist"
    assert data["total"] == 1
    assert data["items"][0]["new_agent"] == "agent_sarah"


def test_business_hours_status_route(monkeypatch):
    fake_status = {
        "is_open": True,
        "current_time": "2026-10-12T10:00:00",
        "next_open_at": None,
        "timezone": "UTC",
        "schedule": {"monday": "09:00 - 18:00"},
        "day_name": "Monday",
    }
    monkeypatch.setattr(
        main.business_hours,
        "get_business_hours_status",
        lambda: fake_status,
    )

    resp = client.get("/business-hours/status")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["is_open"] is True
    assert data["day_name"] == "Monday"


def test_submit_csat_feedback_route(monkeypatch):
    # Session not found
    monkeypatch.setattr(main, "get_chat_history", lambda sid: [])
    resp = client.post(
        "/feedback/csat",
        json={"session_id": "missing-s", "score": 5},
    )
    assert resp.status_code == HTTP_NOT_FOUND

    # Valid submission
    monkeypatch.setattr(
        main,
        "get_chat_history",
        lambda sid: [{"role": "user", "content": "hi"}],
    )
    fake_item = {
        "id": 101,
        "session_id": "valid-s",
        "score": 5,
        "rating": 1,
        "resolution_satisfaction": 5,
        "agent_helpfulness": 5,
        "response_speed": 4,
        "comment": "Super helpful",
        "review_status": "pending_review",
        "assigned_agent": "agent_alice",
        "escalation_tier": "tier_1",
    }
    monkeypatch.setattr(main, "submit_csat_feedback", lambda **kwargs: fake_item)

    resp2 = client.post(
        "/feedback/csat",
        json={
            "session_id": "valid-s",
            "score": 5,
            "resolution_satisfaction": 5,
            "agent_helpfulness": 5,
            "response_speed": 4,
            "comment": "Super helpful",
        },
    )
    assert resp2.status_code == HTTP_CREATED
    data2 = resp2.json()
    assert data2["message"] == "CSAT feedback recorded."
    expected_fbid = 101
    assert data2["feedback_id"] == expected_fbid


def test_list_feedback_review_queue_route(monkeypatch):
    fake_item = {
        "id": 1,
        "session_id": "s-1",
        "score": 2,
        "rating": -1,
        "resolution_satisfaction": 2,
        "agent_helpfulness": 2,
        "response_speed": 1,
        "comment": "Slow response",
        "review_status": "pending_review",
        "assigned_agent": "agent_bob",
        "escalation_tier": "tier_1",
        "reviewer_notes": None,
        "reviewed_at": None,
        "reviewed_by": None,
        "created_at": "2026-10-12 12:00:00",
    }
    monkeypatch.setattr(
        main,
        "list_feedback_review_queue",
        lambda **kwargs: ([fake_item], 1),
    )

    resp = client.get("/feedback/queue?review_status=pending_review&max_score=2")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["score"] == 2  # noqa: PLR2004

    # Invalid query parameters
    bad_resp = client.get("/feedback/queue?min_score=0")
    assert bad_resp.status_code == HTTP_BAD_REQUEST


def test_update_feedback_review_route(monkeypatch):
    # Missing feedback
    monkeypatch.setattr(main, "get_feedback_by_id", lambda fbid: None)
    resp = client.patch(
        "/feedback/999/review",
        json={"review_status": "reviewed"},
    )
    assert resp.status_code == HTTP_NOT_FOUND

    # Valid update
    fake_item = {
        "id": 42,
        "session_id": "s-42",
        "score": 1,
        "rating": -1,
        "resolution_satisfaction": 1,
        "agent_helpfulness": 1,
        "response_speed": 1,
        "comment": "Bad",
        "review_status": "reviewed",
        "assigned_agent": "agent_bob",
        "escalation_tier": "tier_1",
        "reviewer_notes": "Handled with customer",
        "reviewed_at": "2026-10-12 14:00:00",
        "reviewed_by": "lead_qa",
        "created_at": "2026-10-12 12:00:00",
    }
    monkeypatch.setattr(main, "get_feedback_by_id", lambda fbid: {"id": fbid})
    monkeypatch.setattr(main, "update_feedback_review", lambda **kwargs: fake_item)

    resp2 = client.patch(
        "/feedback/42/review",
        json={
            "review_status": "reviewed",
            "reviewer_notes": "Handled with customer",
            "reviewed_by": "lead_qa",
        },
    )
    assert resp2.status_code == HTTP_OK
    data2 = resp2.json()
    assert data2["review_status"] == "reviewed"
    assert data2["reviewed_by"] == "lead_qa"


def test_get_csat_summary_route(monkeypatch):
    fake_summary = {
        "total_responses": 15,
        "avg_csat_score": 4.5,
        "avg_resolution_score": 4.6,
        "avg_helpfulness_score": 4.7,
        "avg_speed_score": 4.3,
        "satisfaction_rate": 86.7,
        "dissatisfaction_rate": 6.7,
        "star_distribution": {1: 1, 2: 0, 3: 1, 4: 3, 5: 10},
        "pending_review_count": 3,
        "followup_required_count": 1,
    }
    monkeypatch.setattr(main.csat, "calculate_csat_summary", lambda limit=1000: fake_summary)

    resp = client.get("/feedback/csat-summary")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    expected_tot = 15
    assert data["total_responses"] == expected_tot
    expected_avg = 4.5
    assert data["avg_csat_score"] == expected_avg


def test_get_agent_scorecards_route(monkeypatch):
    fake_cards = [
        {
            "agent_id": "agent_sarah",
            "tier": "tier_1",
            "total_ratings": 8,
            "avg_csat_score": 4.9,
            "avg_resolution_score": 4.8,
            "avg_helpfulness_score": 5.0,
            "avg_speed_score": 4.9,
            "positive_count": 8,
            "negative_count": 0,
            "satisfaction_rate": 100.0,
        }
    ]
    monkeypatch.setattr(main, "get_agent_performance_analytics", lambda: fake_cards)

    resp = client.get("/feedback/agent-scorecards")
    assert resp.status_code == HTTP_OK
    data = resp.json()
    assert data["total_agents"] == 1
    assert data["scorecards"][0]["agent_id"] == "agent_sarah"


def test_knowledge_gap_routes(monkeypatch):
    fake_gap = {
        "id": 1,
        "query": "How to reserve freight elevator?",
        "normalized_query": "how to reserve freight elevator",
        "category": "policy",
        "source_type": "manual",
        "session_id": "sess-1",
        "frequency": 1,
        "priority": "high",
        "status": "open",
        "linked_article_id": None,
        "notes": "urgent",
        "created_at": "2026-10-13 10:00:00",
        "updated_at": "2026-10-13 10:00:00",
    }
    monkeypatch.setattr(main.db_utils, "record_knowledge_gap", lambda **kwargs: fake_gap)
    monkeypatch.setattr(main.db_utils, "list_knowledge_gaps", lambda **kwargs: ([fake_gap], 1))
    monkeypatch.setattr(
        main.db_utils,
        "get_knowledge_gap",
        lambda gid: fake_gap if gid == 1 else None,
    )
    monkeypatch.setattr(
        main.db_utils,
        "update_knowledge_gap",
        lambda gap_id, **kw: {**fake_gap, **{k: v for k, v in kw.items() if v is not None}}
        if gap_id == 1
        else None,
    )
    monkeypatch.setattr(main.db_utils, "delete_knowledge_gap", lambda gid: gid == 1)

    # 1. Create gap
    payload = {"query": "How to reserve freight elevator?", "category": "policy"}
    res = client.post("/knowledge/gaps", json=payload)
    assert res.status_code == HTTP_CREATED
    assert res.json()["id"] == 1

    # 2. List gaps
    res = client.get("/knowledge/gaps?status=open")
    assert res.status_code == HTTP_OK
    assert res.json()["total"] == 1

    # 3. Get gap
    res = client.get("/knowledge/gaps/1")
    assert res.status_code == HTTP_OK
    assert res.json()["query"] == "How to reserve freight elevator?"

    # 4. Get 404
    res = client.get("/knowledge/gaps/999")
    assert res.status_code == HTTP_NOT_FOUND

    # 5. Patch gap
    res = client.patch("/knowledge/gaps/1", json={"status": "resolved"})
    assert res.status_code == HTTP_OK
    assert res.json()["status"] == "resolved"

    # 6. Delete gap
    res = client.delete("/knowledge/gaps/1")
    assert res.status_code == HTTP_OK
    assert res.json()["status"] == "deleted"


def test_scan_knowledge_gaps_route(monkeypatch):
    fake_scan = {
        "scanned_sessions_count": 25,
        "gaps_created": 3,
        "gaps_incremented": 1,
        "total_gaps_identified": 4,
        "gaps": [
            {
                "id": 2,
                "query": "Where is the pet wash station?",
                "normalized_query": "where is the pet wash station",
                "category": "general",
                "source_type": "low_csat",
                "session_id": "sess-2",
                "frequency": 1,
                "priority": "medium",
                "status": "open",
                "linked_article_id": None,
                "notes": "Low CSAT",
                "created_at": "2026-10-13 11:00:00",
                "updated_at": "2026-10-13 11:00:00",
            }
        ],
    }
    monkeypatch.setattr(
        main.knowledge_base,
        "scan_sessions_for_knowledge_gaps",
        lambda limit=100: fake_scan,
    )

    res = client.post("/knowledge/gaps/scan?limit=50")
    assert res.status_code == HTTP_OK
    expected_scanned = 25
    assert res.json()["scanned_sessions_count"] == expected_scanned
    expected_total_identified = 4
    assert res.json()["total_gaps_identified"] == expected_total_identified


def test_knowledge_article_routes(monkeypatch):
    target_aid = 10
    fake_art = {
        "id": target_aid,
        "title": "Freight Elevator Booking Policy",
        "category": "policy",
        "question_pattern": "How to reserve elevator",
        "content_markdown": "# Freight Elevator\n\nReserve 48h prior.",
        "tags": ["elevator", "logistics"],
        "source_session_id": "sess-1",
        "source_gap_id": 1,
        "status": "draft",
        "author": "agent_dan",
        "published_file_id": None,
        "published_collection": None,
        "created_at": "2026-10-13 10:00:00",
        "updated_at": "2026-10-13 10:00:00",
    }
    monkeypatch.setattr(main.db_utils, "create_knowledge_article", lambda **kwargs: fake_art)
    monkeypatch.setattr(main.db_utils, "list_knowledge_articles", lambda **kwargs: ([fake_art], 1))
    monkeypatch.setattr(
        main.db_utils,
        "get_knowledge_article",
        lambda aid: fake_art if aid == target_aid else None,
    )
    monkeypatch.setattr(
        main.db_utils,
        "update_knowledge_article",
        lambda article_id, **kw: {**fake_art, **{k: v for k, v in kw.items() if v is not None}}
        if article_id == target_aid
        else None,
    )
    monkeypatch.setattr(
        main.db_utils,
        "delete_knowledge_article",
        lambda aid: aid == target_aid,
    )

    # 1. Create article
    art_payload = {
        "title": "Freight Elevator Booking Policy",
        "content_markdown": "# Freight Elevator",
        "category": "policy",
    }
    res = client.post("/knowledge/articles", json=art_payload)
    assert res.status_code == HTTP_CREATED
    expected_art_id = target_aid
    assert res.json()["id"] == expected_art_id

    # 2. List articles
    res = client.get("/knowledge/articles?category=policy")
    assert res.status_code == HTTP_OK
    assert res.json()["total"] == 1

    # 3. Get article
    res = client.get("/knowledge/articles/10")
    assert res.status_code == HTTP_OK
    assert res.json()["title"] == "Freight Elevator Booking Policy"

    # 4. Patch article
    res = client.patch("/knowledge/articles/10", json={"status": "published"})
    assert res.status_code == HTTP_OK
    assert res.json()["status"] == "published"

    # 5. Delete article
    res = client.delete("/knowledge/articles/10")
    assert res.status_code == HTTP_OK
    assert res.json()["status"] == "deleted"


def test_session_draft_article_route(monkeypatch):
    fake_art = {
        "id": 11,
        "title": "FAQ: Move-in procedures",
        "category": "lease",
        "question_pattern": "What are move in procedures?",
        "content_markdown": "# Move In FAQ",
        "tags": ["move_in"],
        "source_session_id": "sess-3",
        "source_gap_id": None,
        "status": "draft",
        "author": "agent_alice",
        "published_file_id": None,
        "published_collection": None,
        "created_at": "2026-10-13 12:00:00",
        "updated_at": "2026-10-13 12:00:00",
    }
    monkeypatch.setattr(main, "_get_session_summary_or_404", lambda sid: {"session_id": sid})
    monkeypatch.setattr(
        main.knowledge_base,
        "synthesize_article_from_session",
        lambda **kwargs: fake_art,
    )

    res = client.post("/sessions/sess-3/draft-article", json={"author": "agent_alice"})
    assert res.status_code == HTTP_CREATED
    expected_synth_id = 11
    assert res.json()["id"] == expected_synth_id
    assert res.json()["source_session_id"] == "sess-3"


def test_publish_article_and_analytics_routes(monkeypatch):
    fake_art = {
        "id": 10,
        "title": "Freight Elevator Booking Policy",
        "category": "policy",
        "question_pattern": "How to reserve elevator",
        "content_markdown": "# Freight Elevator",
        "tags": ["elevator"],
        "source_session_id": "sess-1",
        "source_gap_id": 1,
        "status": "published",
        "author": "agent_dan",
        "published_file_id": 50,
        "published_collection": "default",
        "created_at": "2026-10-13 10:00:00",
        "updated_at": "2026-10-13 10:00:00",
    }
    fake_pub_res = {
        "article": fake_art,
        "file_id": 50,
        "collection": "default",
        "indexed_in_vectorstore": True,
        "linked_gap_resolved": True,
    }
    monkeypatch.setattr(
        main.knowledge_base,
        "publish_knowledge_article",
        lambda **kwargs: fake_pub_res,
    )

    res = client.post("/knowledge/articles/10/publish", json={"collection": "default"})
    assert res.status_code == HTTP_OK
    expected_doc_id = 50
    assert res.json()["file_id"] == expected_doc_id
    assert res.json()["linked_gap_resolved"] is True

    fake_analytics = {
        "total_gaps": 8,
        "open_gaps_count": 3,
        "drafting_gaps_count": 1,
        "resolved_gaps_count": 4,
        "dismissed_gaps_count": 0,
        "gap_resolution_rate": 50.0,
        "total_gap_queries_logged": 12,
        "recurring_queries_count": 4,
        "category_distribution": {"policy": 2, "maintenance": 1},
        "priority_distribution": {"high": 2, "medium": 1},
        "total_articles": 5,
        "draft_articles_count": 1,
        "published_articles_count": 4,
        "archived_articles_count": 0,
        "estimated_deflected_queries": 24,
    }
    monkeypatch.setattr(
        main.knowledge_base,
        "get_knowledge_base_analytics",
        lambda: fake_analytics,
    )

    res_an = client.get("/knowledge/analytics")
    assert res_an.status_code == HTTP_OK
    expected_tot_gaps = 8
    assert res_an.json()["total_gaps"] == expected_tot_gaps
    expected_deflected = 24
    assert res_an.json()["estimated_deflected_queries"] == expected_deflected


def test_create_unit_route_success_and_validations(monkeypatch, tmp_path):
    """Test POST /units creation and error responses."""
    db_file = tmp_path / "test_api_units.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()

    # 1. Successful creation
    unit_rent = 1600.0
    payload = {
        "id": "unit_401",
        "property_name": "Highland Park",
        "unit_number": "401",
        "building_name": "Building B",
        "floor": 4,
        "address": "401 Highland Ave",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62704",
        "monthly_rent": unit_rent,
        "parking_spot": "P-401",
        "gate_code": "#4011",
    }
    res = client.post("/units", json=payload)
    assert res.status_code == HTTP_CREATED
    data = res.json()["unit"]
    assert data["id"] == "unit_401"
    assert data["property_name"] == "Highland Park"
    assert data["monthly_rent"] == unit_rent

    # 2. Duplicate unit ID -> 409 Conflict
    dup_res = client.post("/units", json=payload)
    assert dup_res.status_code == HTTP_CONFLICT
    assert "already exists" in dup_res.json()["detail"].lower()

    # 3. Invalid unit ID (spaces) -> 422 Unprocessable Entity
    bad_payload = {**payload, "id": "invalid unit id with spaces"}
    bad_res = client.post("/units", json=bad_payload)
    assert bad_res.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_list_and_get_unit_routes(monkeypatch, tmp_path):
    """Test GET /units listing and GET /units/{id} lookup."""
    db_file = tmp_path / "test_api_units_list.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()

    # Pre-seeded units are present
    res = client.get("/units")
    assert res.status_code == HTTP_OK
    data = res.json()
    expected_seeded_units = 3
    assert data["total"] == expected_seeded_units
    assert len(data["items"]) == expected_seeded_units

    # Filter by property_name
    filter_res = client.get("/units?property_name=Sunset%20Heights%20Apartments")
    assert filter_res.status_code == HTTP_OK
    expected_filtered_units = 2
    assert filter_res.json()["total"] == expected_filtered_units

    # Get single unit
    unit_res = client.get("/units/unit_101")
    assert unit_res.status_code == HTTP_OK
    assert unit_res.json()["unit"]["unit_number"] == "101"

    # Not found unit
    missing_res = client.get("/units/non_existent_unit")
    assert missing_res.status_code == HTTP_NOT_FOUND


def test_update_and_delete_unit_routes(monkeypatch, tmp_path):
    """Test PATCH /units/{id} update and DELETE /units/{id} deletion."""
    db_file = tmp_path / "test_api_units_crud.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()

    # Update unit_204
    updated_rent = 1999.0
    patch_res = client.patch(
        "/units/unit_204",
        json={"monthly_rent": updated_rent, "parking_spot": "P-999"},
    )
    assert patch_res.status_code == HTTP_OK
    assert patch_res.json()["unit"]["monthly_rent"] == updated_rent
    assert patch_res.json()["unit"]["parking_spot"] == "P-999"

    # Update non-existent unit
    patch_missing = client.patch("/units/non_existent_unit", json={"monthly_rent": 1200.0})
    assert patch_missing.status_code == HTTP_NOT_FOUND

    # Delete unit_PH1
    del_res = client.delete("/units/unit_PH1")
    assert del_res.status_code == HTTP_OK
    assert del_res.json()["status"] == "deleted"

    # Verify unit is gone
    get_res = client.get("/units/unit_PH1")
    assert get_res.status_code == HTTP_NOT_FOUND

    # Delete non-existent unit -> 404
    del_missing = client.delete("/units/unit_PH1")
    assert del_missing.status_code == HTTP_NOT_FOUND


def test_create_tenant_route_success_and_validations(monkeypatch, tmp_path):
    """Test POST /tenants creation, conflict, and validation."""
    db_file = tmp_path / "test_api_tenants.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()
    main.db_utils.create_tenants()

    rent_val = 2150.0
    payload = {
        "id": "tenant_999",
        "first_name": "Diana",
        "last_name": "Prince",
        "email": "diana.prince@themyscira.com",
        "phone": "+1 555-444-3322",
        "unit_id": "unit_101",
        "lease_start": "2025-01-01",
        "lease_end": "2025-12-31",
        "monthly_rent": rent_val,
        "balance_due": 0.0,
        "status": "active",
        "emergency_contact_name": "Hippolyta",
        "emergency_contact_phone": "+1 555-999-8877",
        "notes": "VIP tenant",
    }
    res = client.post("/tenants", json=payload)
    assert res.status_code == HTTP_CREATED
    data = res.json()["tenant"]
    assert data["id"] == "tenant_999"
    assert data["first_name"] == "Diana"
    assert data["monthly_rent"] == rent_val

    # Duplicate ID -> 409 Conflict
    dup_res = client.post("/tenants", json=payload)
    assert dup_res.status_code == HTTP_CONFLICT

    # Invalid email -> 422
    bad_payload = {**payload, "id": "tenant_998", "email": "invalid-email"}
    bad_res = client.post("/tenants", json=bad_payload)
    assert bad_res.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_list_and_get_tenant_routes(monkeypatch, tmp_path):
    """Test GET /tenants list and GET /tenants/{id} lookup."""
    db_file = tmp_path / "test_api_tenants_list.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()
    main.db_utils.create_tenants()

    # Pre-seeded tenants exist
    res = client.get("/tenants")
    assert res.status_code == HTTP_OK
    data = res.json()
    expected_seeded = 3
    assert data["total"] == expected_seeded
    assert len(data["items"]) == expected_seeded

    # Filter by unit_id
    filter_res = client.get("/tenants?unit_id=unit_101")
    assert filter_res.status_code == HTTP_OK
    expected_filtered = 1
    assert filter_res.json()["total"] == expected_filtered

    # Lookup existing tenant
    tenant_res = client.get("/tenants/tenant_1")
    assert tenant_res.status_code == HTTP_OK
    assert tenant_res.json()["tenant"]["first_name"] == "Sarah"

    # Lookup missing tenant -> 404
    missing_res = client.get("/tenants/non_existent_tenant")
    assert missing_res.status_code == HTTP_NOT_FOUND


def test_update_and_delete_tenant_routes(monkeypatch, tmp_path):
    """Test PATCH /tenants/{id} and DELETE /tenants/{id}."""
    db_file = tmp_path / "test_api_tenants_crud.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()
    main.db_utils.create_tenants()

    # Patch balance
    updated_balance = 350.0
    patch_res = client.patch(
        "/tenants/tenant_1",
        json={"balance_due": updated_balance, "notes": "Late fee assessed"},
    )
    assert patch_res.status_code == HTTP_OK
    assert patch_res.json()["tenant"]["balance_due"] == updated_balance

    # Patch non-existent tenant -> 404
    patch_missing = client.patch("/tenants/non_existent", json={"balance_due": 0.0})
    assert patch_missing.status_code == HTTP_NOT_FOUND

    # Delete tenant_3
    del_res = client.delete("/tenants/tenant_3")
    assert del_res.status_code == HTTP_OK
    assert del_res.json()["status"] == "deleted"

    # Delete non-existent tenant -> 404
    del_missing = client.delete("/tenants/tenant_3")
    assert del_missing.status_code == HTTP_NOT_FOUND


def test_session_tenant_linking_and_context_routes(monkeypatch, tmp_path):
    """Test session tenant linking and context retrieval."""
    db_file = tmp_path / "test_api_tenant_ctx.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()
    main.db_utils.create_tenants()
    main.db_utils.create_session_labels()
    main.db_utils.create_application_logs()

    test_sid = "session_ctx_test_42"

    # 1. Unlinked session context
    res_ctx = client.get(f"/sessions/{test_sid}/tenant-context")
    assert res_ctx.status_code == HTTP_OK
    assert res_ctx.json()["tenant_id"] is None
    assert res_ctx.json()["tenant"] is None

    # 2. Link tenant to session
    link_payload = {"tenant_id": "tenant_1", "unit_id": None}
    link_res = client.post(f"/sessions/{test_sid}/link-tenant", json=link_payload)
    assert link_res.status_code == HTTP_OK
    data = link_res.json()
    assert data["session_id"] == test_sid
    assert data["tenant_id"] == "tenant_1"
    assert data["unit_id"] == "unit_101"
    assert data["tenant"]["first_name"] == "Sarah"
    assert data["unit"]["property_name"] == "Sunset Heights Apartments"

    # 3. Fetch context now that session is linked
    res_ctx_linked = client.get(f"/sessions/{test_sid}/tenant-context")
    assert res_ctx_linked.status_code == HTTP_OK
    assert res_ctx_linked.json()["tenant_id"] == "tenant_1"
    assert res_ctx_linked.json()["unit_id"] == "unit_101"

    # 4. Link invalid tenant -> 422
    bad_link = client.post(
        f"/sessions/{test_sid}/link-tenant",
        json={"tenant_id": "non_existent_tenant"},
    )
    assert bad_link.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_tenant_support_history_route(monkeypatch, tmp_path):
    """Test GET /tenants/{tenant_id}/support-history."""
    db_file = tmp_path / "test_api_tenant_history.db"
    monkeypatch.setattr(main.db_utils, "DB_NAME", str(db_file))
    main.db_utils.create_units()
    main.db_utils.create_tenants()
    main.db_utils.create_session_labels()
    main.db_utils.create_application_logs()
    main.db_utils.create_feedback()

    # Link session to tenant_2
    test_sid = "session_hist_002"
    main.db_utils.link_session_tenant(test_sid, tenant_id="tenant_2")
    main.db_utils.insert_application_logs(
        test_sid, "My sink is leaking", "We will send a plumber.", "gpt-4o"
    )

    # Fetch history
    res = client.get("/tenants/tenant_2/support-history")
    assert res.status_code == HTTP_OK
    hist = res.json()
    assert hist["tenant"]["id"] == "tenant_2"
    expected_total_sessions = 1
    assert hist["total_sessions"] == expected_total_sessions
    assert hist["sessions"][0]["session_id"] == test_sid

    # Non-existent tenant -> 404
    missing_res = client.get("/tenants/missing_tenant_id/support-history")
    assert missing_res.status_code == HTTP_NOT_FOUND





