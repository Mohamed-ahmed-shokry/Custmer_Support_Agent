import pytest
from pydantic import ValidationError

from api.pydantic_models import QueryInput, QueryResponse, SourceInfo


def test_query_input_rejects_empty_question():
    with pytest.raises(ValidationError):
        QueryInput(question="")


def test_query_response_accepts_sources():
    response = QueryResponse(
        answer="Answer",
        session_id="session-1",
        model="gpt-4o-mini",
        sources=[SourceInfo(filename="guide.pdf", preview="Relevant text")],
    )

    assert response.sources[0].filename == "guide.pdf"
    assert response.sources[0].preview == "Relevant text"
