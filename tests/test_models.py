from datetime import datetime

import pytest
from api.pydantic_models import (
    DEFAULT_MODEL,
    ChunkingStrategy,
    CollectionAnalyticsResponse,
    CollectionRechunkRequest,
    CollectionRechunkResponse,
    DocumentDetailResponse,
    DocumentRechunkItem,
    ModelName,
    QueryInput,
    QueryResponse,
    RechunkDocumentRequest,
    SessionInfo,
    SessionSummaryRequest,
    SessionSummaryResponse,
    SourceInfo,
    SupportTriageAnalyticsResponse,
    TagCount,
    UpdateSessionRequest,
    model_from_value,
)
from pydantic import ValidationError


def test_query_input_rejects_empty_question():
    with pytest.raises(ValidationError):
        QueryInput(question="")


def test_query_input_rejects_whitespace_question():
    with pytest.raises(ValidationError):
        QueryInput(question="   ")


def test_model_from_value_accepts_supported_model():
    assert model_from_value("gpt-4o") == ModelName.GPT4_O


def test_model_from_value_falls_back_for_unknown_model():
    assert model_from_value("unknown") == DEFAULT_MODEL


def test_query_input_uses_configured_default_model(monkeypatch):
    monkeypatch.setattr("api.pydantic_models.settings.default_model", "gpt-4o")

    assert QueryInput(question="How do I request maintenance?").model == ModelName.GPT4_O


def test_query_input_normalizes_collections():
    query = QueryInput(question="Hi?", collections=["Clients-Acme", "  DEFAULT  "])

    assert query.collections == ["clients-acme", "default"]


def test_query_input_rejects_invalid_collection():
    with pytest.raises(ValidationError):
        QueryInput(question="Hi?", collections=["bad name!"])


def test_query_response_accepts_sources():
    response = QueryResponse(
        answer="Answer",
        session_id="session-1",
        model=ModelName.GPT4_O_MINI,
        sources=[SourceInfo(filename="guide.pdf", preview="Relevant text")],
    )

    assert response.sources[0].filename == "guide.pdf"
    assert response.sources[0].preview == "Relevant text"


def test_rechunk_document_request_defaults():
    req = RechunkDocumentRequest()
    expected_chunk_size = 1000
    expected_chunk_overlap = 200
    assert req.chunking_strategy == ChunkingStrategy.RECURSIVE
    assert req.chunk_size == expected_chunk_size
    assert req.chunk_overlap == expected_chunk_overlap


def test_rechunk_document_request_custom():
    expected_size = 640
    expected_overlap = 80
    req = RechunkDocumentRequest(
        chunking_strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=expected_size,
        chunk_overlap=expected_overlap,
    )
    assert req.chunking_strategy == ChunkingStrategy.SEMANTIC
    assert req.chunk_size == expected_size
    assert req.chunk_overlap == expected_overlap


def test_rechunk_document_request_validation():
    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_size=50)  # below 100

    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_size=5000)  # above 4000

    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_overlap=-1)  # negative overlap

    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_size=500, chunk_overlap=500)  # overlap >= size


def test_document_detail_response_chunking_fields():
    expected_size = 800
    expected_overlap = 150
    resp = DocumentDetailResponse(
        id=1,
        filename="test.pdf",
        chunk_count=3,
        chunking_strategy="semantic",
        chunk_size=expected_size,
        chunk_overlap=expected_overlap,
    )
    assert resp.chunking_strategy == "semantic"
    assert resp.chunk_size == expected_size
    assert resp.chunk_overlap == expected_overlap

    resp_default = DocumentDetailResponse(id=2, filename="test2.pdf", chunk_count=0)
    assert resp_default.chunking_strategy is None
    assert resp_default.chunk_size is None
    assert resp_default.chunk_overlap is None


def test_collection_rechunk_request_defaults_and_custom():
    default_req = CollectionRechunkRequest()
    expected_default_size = 1000
    expected_default_overlap = 200
    assert default_req.chunking_strategy == ChunkingStrategy.RECURSIVE
    assert default_req.chunk_size == expected_default_size
    assert default_req.chunk_overlap == expected_default_overlap

    expected_custom_size = 600
    expected_custom_overlap = 80
    custom_req = CollectionRechunkRequest(
        chunking_strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=expected_custom_size,
        chunk_overlap=expected_custom_overlap,
    )
    assert custom_req.chunking_strategy == ChunkingStrategy.SEMANTIC
    assert custom_req.chunk_size == expected_custom_size
    assert custom_req.chunk_overlap == expected_custom_overlap


def test_collection_rechunk_request_validation():
    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_size=50)

    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_size=5000)

    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_overlap=-1)

    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_size=400, chunk_overlap=400)


def test_collection_rechunk_response():
    expected_docs = 5
    expected_rechunked = 4
    expected_skipped = 1
    expected_failed = 0
    expected_chunks = 28
    item1 = DocumentRechunkItem(
        file_id=1,
        filename="doc1.txt",
        status="rechunked",
        chunk_count=10,
    )
    item2 = DocumentRechunkItem(
        file_id=2,
        filename="doc2.txt",
        status="skipped",
        chunk_count=0,
        error_message="No stored source text",
    )
    resp = CollectionRechunkResponse(
        message="Re-chunked collection legal",
        collection="legal",
        strategy="semantic",
        chunk_size=500,
        chunk_overlap=50,
        total_documents=expected_docs,
        rechunked_documents=expected_rechunked,
        skipped_documents=expected_skipped,
        failed_documents=expected_failed,
        total_chunks_created=expected_chunks,
        items=[item1, item2],
    )
    assert resp.collection == "legal"
    expected_items_count = 2
    assert resp.total_documents == expected_docs
    assert resp.rechunked_documents == expected_rechunked
    assert len(resp.items) == expected_items_count
    assert resp.items[0].status == "rechunked"
    assert resp.items[1].error_message == "No stored source text"


def test_collection_analytics_response():
    expected_docs = 3
    expected_chunks = 15
    expected_avg = 450.5
    expected_min = 120
    expected_max = 980
    expected_median = 430.0
    expected_semantic_count = 5
    resp = CollectionAnalyticsResponse(
        collection="kb",
        total_documents=expected_docs,
        total_chunks=expected_chunks,
        avg_chunk_length=expected_avg,
        min_chunk_length=expected_min,
        max_chunk_length=expected_max,
        median_chunk_length=expected_median,
        strategy_distribution={"recursive": 10, "semantic": expected_semantic_count},
        length_histogram={"<200": 1, "200-500": 8, "500-1000": 6},
    )
    assert resp.collection == "kb"
    assert resp.total_documents == expected_docs
    assert resp.total_chunks == expected_chunks
    assert resp.avg_chunk_length == expected_avg
    assert resp.strategy_distribution["semantic"] == expected_semantic_count


def test_session_info_summary_and_resolution_notes():
    now = datetime.now()
    default_info = SessionInfo(session_id="s1", message_count=2, last_active=now)
    assert default_info.summary is None
    assert default_info.resolution_notes is None
    assert default_info.status == "active"

    custom_info = SessionInfo(
        session_id="s2",
        message_count=4,
        last_active=now,
        status="resolved",
        summary="Customer resolved fee discrepancy.",
        resolution_notes="Refund processed successfully.",
    )
    assert custom_info.summary == "Customer resolved fee discrepancy."
    assert custom_info.resolution_notes == "Refund processed successfully."


def test_update_session_request_summary_and_notes():
    # At least one field required
    with pytest.raises(ValidationError):
        UpdateSessionRequest()

    # Valid with only summary
    req1 = UpdateSessionRequest(summary="  New summary  ")
    assert req1.summary == "New summary"

    # Valid with only resolution_notes
    req2 = UpdateSessionRequest(resolution_notes="  New notes  ")
    assert req2.resolution_notes == "New notes"

    # Reject overly long summary or notes
    with pytest.raises(ValidationError):
        UpdateSessionRequest(summary="x" * 2001)

    with pytest.raises(ValidationError):
        UpdateSessionRequest(resolution_notes="y" * 2001)


def test_session_summary_request_and_response():
    req_def = SessionSummaryRequest()
    assert req_def.model is None
    assert req_def.save_summary is True

    req_custom = SessionSummaryRequest(model="gpt-4o", save_summary=False)
    assert req_custom.model == "gpt-4o"
    assert req_custom.save_summary is False

    resp = SessionSummaryResponse(
        session_id="s1",
        summary="User asked about lease.",
        key_points=["Customer inquiry: lease terms"],
        sentiment="positive",
        suggested_tags=["lease"],
        saved=True,
    )
    assert resp.session_id == "s1"
    assert resp.sentiment == "positive"
    assert resp.saved is True


def test_support_triage_analytics_response():

    expected_total = 10
    expected_active = 4
    expected_resolved = 4
    expected_escalated = 1
    expected_closed = 1
    expected_res_rate = 50.0
    expected_esc_rate = 10.0
    expected_turns = 2.5
    expected_tag_count = 5

    resp = SupportTriageAnalyticsResponse(
        total_sessions=expected_total,
        active_count=expected_active,
        resolved_count=expected_resolved,
        escalated_count=expected_escalated,
        closed_count=expected_closed,
        resolution_rate=expected_res_rate,
        escalation_rate=expected_esc_rate,
        avg_turns_per_session=expected_turns,
        top_tags=[TagCount(tag="lease", count=expected_tag_count)],
    )
    assert resp.total_sessions == expected_total
    assert resp.resolution_rate == expected_res_rate
    assert resp.top_tags[0].tag == "lease"
    assert resp.top_tags[0].count == expected_tag_count
