"""Unit tests for response presenters (pure functions, no I/O)."""

from types import SimpleNamespace

from api.presenters import (
    build_search_hits,
    build_sources,
    preview_content,
    render_session_markdown,
)


def _doc(content, **metadata):
    return SimpleNamespace(page_content=content, metadata=dict(metadata))


def test_preview_content_truncates_and_strips():
    assert preview_content("  hello  ") == "hello"
    assert preview_content(None) == ""
    assert preview_content("x" * 300) == "x" * 280


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
