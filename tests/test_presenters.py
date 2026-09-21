"""Unit tests for response presenters (pure functions, no I/O)."""

import csv
import io
import json
from types import SimpleNamespace

from api.presenters import (
    build_search_hits,
    build_sources,
    extract_document_score,
    preview_content,
    render_session_csv,
    render_session_json,
    render_session_markdown,
)


def _doc(content, **metadata):

    return SimpleNamespace(page_content=content, metadata=dict(metadata))


def test_preview_content_truncates_and_strips():
    assert preview_content("  hello  ") == "hello"
    assert preview_content(None) == ""
    assert preview_content("x" * 300) == "x" * 280


def test_extract_document_score_sources():
    doc1 = SimpleNamespace(page_content="c", metadata={"score": 0.87654})
    expected_score_1 = 0.8765
    assert extract_document_score(doc1) == expected_score_1

    doc2 = SimpleNamespace(page_content="c", metadata={"relevance_score": 0.95})
    expected_score_2 = 0.95
    assert extract_document_score(doc2) == expected_score_2

    doc3 = SimpleNamespace(page_content="c", score=0.72, metadata={})
    expected_score_3 = 0.72
    assert extract_document_score(doc3) == expected_score_3

    doc4 = SimpleNamespace(page_content="c", metadata={"score": "invalid"})
    assert extract_document_score(doc4) is None

    doc5 = SimpleNamespace(page_content="c", metadata={})
    assert extract_document_score(doc5) is None


def test_build_search_hits_with_score_and_threshold():
    score_high = 0.92
    score_low = 0.35
    doc1 = SimpleNamespace(
        page_content="High match",
        metadata={"file_id": 1, "score": score_high, "collection": "docs"},
    )
    doc2 = SimpleNamespace(
        page_content="Low match",
        metadata={"file_id": 2, "score": score_low, "collection": "docs"},
    )
    doc3 = SimpleNamespace(
        page_content="Unscored match", metadata={"file_id": 3, "collection": "docs"}
    )

    # Without threshold: all 3 returned
    hits = build_search_hits([doc1, doc2, doc3])
    expected_all_hits = 3
    assert len(hits) == expected_all_hits
    assert hits[0].score == score_high
    assert hits[1].score == score_low
    assert hits[2].score is None

    # With threshold 0.5: doc2 (0.35) filtered out, doc1 kept, unscored doc3 kept
    threshold = 0.5
    filtered_hits = build_search_hits([doc1, doc2, doc3], score_threshold=threshold)
    expected_filtered = 2
    expected_second_rank = 2
    assert len(filtered_hits) == expected_filtered
    assert filtered_hits[0].preview == "High match"
    assert filtered_hits[0].rank == 1
    assert filtered_hits[1].preview == "Unscored match"
    assert filtered_hits[1].rank == expected_second_rank


def test_build_sources_includes_score():
    expected_source_score = 0.88
    doc = SimpleNamespace(
        page_content="Sample",
        metadata={"file_id": 1, "filename": "doc.pdf", "score": expected_source_score},
    )
    sources = build_sources([doc])
    assert len(sources) == 1
    assert sources[0].score == expected_source_score


def test_build_sources_dedupes_chunks():
    metadata = {"file_id": 7, "filename": "guide.pdf", "page": 1, "chunk_index": 0}
    documents = [
        _doc("First chunk", **metadata),
        _doc("First chunk", **metadata),
        _doc("Other chunk", file_id=8, filename="other.pdf"),
    ]

    sources = build_sources(documents)

    assert [(s.filename, s.preview) for s in sources] == [
        ("guide.pdf", "First chunk"),
        ("other.pdf", "Other chunk"),
    ]
    assert build_sources(None) == []
    assert build_sources([]) == []


def test_build_search_hits_ranks_from_one():
    documents = [
        _doc("  Padded content.  ", file_id=7, filename="g.pdf", collection="acme"),
        _doc("Second", file_id=7, filename="g.pdf", page=2, chunk_index=1),
    ]

    hits = build_search_hits(documents)

    assert [hit.rank for hit in hits] == [1, 2]
    assert hits[0].preview == "Padded content."
    assert hits[0].collection == "acme"
    assert hits[1].collection is None
    assert build_search_hits(None) == []


def test_render_session_markdown_uses_label_and_roles():
    markdown = render_session_markdown(
        "session-1",
        "Lease questions",
        [
            {"role": "human", "content": "When is rent due?"},
            {"role": "ai", "content": "On the first."},
            {"role": "system", "content": "Note."},
        ],
    )

    assert markdown.startswith("# Conversation: Lease questions\n")
    assert "- Session: `session-1`" in markdown
    assert "## User" in markdown
    assert "## Assistant" in markdown
    assert "## system" in markdown
    assert markdown.endswith("Note.\n")


def test_render_session_markdown_falls_back_to_session_id():
    markdown = render_session_markdown("session-9", None, [])

    assert markdown.startswith("# Conversation: session-9\n")


def test_render_session_json():
    messages = [
        {"role": "human", "content": "When is rent due?"},
        {"role": "ai", "content": "On the first."},
    ]
    raw_json = render_session_json("session-1", "Lease questions", messages)
    data = json.loads(raw_json)

    expected_count = 2
    assert data["session_id"] == "session-1"
    assert data["label"] == "Lease questions"
    assert "exported_at" in data
    assert len(data["messages"]) == expected_count
    assert data["messages"][0] == {"role": "human", "content": "When is rent due?"}
    assert data["messages"][1] == {"role": "ai", "content": "On the first."}



def test_render_session_csv():
    messages = [
        {"role": "human", "content": "Line 1\nLine 2"},
        {"role": "ai", "content": "Comma, here."},
    ]
    raw_csv = render_session_csv("session-2", "Label", messages)
    reader = list(csv.reader(io.StringIO(raw_csv)))

    assert reader[0] == ["session_id", "label", "turn", "role", "content"]
    assert reader[1] == ["session-2", "Label", "1", "human", "Line 1\nLine 2"]
    assert reader[2] == ["session-2", "Label", "2", "ai", "Comma, here."]


