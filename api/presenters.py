"""Pure response presenters: previews, sources, hits, transcripts (no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.pydantic_models import SearchHit, SourceInfo

PREVIEW_MAX_CHARS = 280

ROLE_HEADINGS = {"human": "User", "ai": "Assistant"}


def preview_content(page_content: str | None) -> str:
    return (page_content or "")[:PREVIEW_MAX_CHARS].strip()


def _base_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": metadata.get("file_id"),
        "filename": metadata.get("filename") or metadata.get("source"),
        "page": metadata.get("page"),
        "chunk_index": metadata.get("chunk_index"),
    }


def build_sources(documents) -> list[SourceInfo]:
    sources = []
    seen = set()
    for document in documents or []:
        metadata = document.metadata or {}
        key = (
            metadata.get("file_id"),
            metadata.get("filename") or metadata.get("source"),
            metadata.get("page"),
            metadata.get("chunk_index"),
        )
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            SourceInfo(
                **_base_metadata(metadata),
                preview=preview_content(document.page_content),
            )
        )
    return sources


def build_search_hits(documents) -> list[SearchHit]:
    hits = []
    for rank, document in enumerate(documents or [], start=1):
        metadata = document.metadata or {}
        hits.append(
            SearchHit(
                rank=rank,
                preview=preview_content(document.page_content),
                collection=metadata.get("collection"),
                **_base_metadata(metadata),
            )
        )
    return hits


def render_session_markdown(session_id: str, label: str | None, messages: list[dict]) -> str:
    """Render a conversation as a markdown transcript."""
    title = label or session_id
    lines = [
        f"# Conversation: {title}",
        "",
        f"- Session: `{session_id}`",
        f"- Exported: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
    ]
    for message in messages:
        lines.append(f"## {ROLE_HEADINGS.get(message['role'], message['role'])}")
        lines.append("")
        lines.append(message["content"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
