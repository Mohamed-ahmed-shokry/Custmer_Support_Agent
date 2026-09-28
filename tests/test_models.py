import pytest
from api.pydantic_models import (
    DEFAULT_MODEL,
    ChunkingStrategy,
    DocumentDetailResponse,
    ModelName,
    QueryInput,
    QueryResponse,
    RechunkDocumentRequest,
    SourceInfo,
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
        model="gpt-4o-mini",
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
