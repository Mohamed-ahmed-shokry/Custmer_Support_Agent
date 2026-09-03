import pytest
from api.pydantic_models import (
    DEFAULT_MODEL,
    ModelName,
    QueryInput,
    QueryResponse,
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


def test_query_response_accepts_sources():
    response = QueryResponse(
        answer="Answer",
        session_id="session-1",
        model="gpt-4o-mini",
        sources=[SourceInfo(filename="guide.pdf", preview="Relevant text")],
    )

    assert response.sources[0].filename == "guide.pdf"
    assert response.sources[0].preview == "Relevant text"
