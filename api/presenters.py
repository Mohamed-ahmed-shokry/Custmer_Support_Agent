"""Pure response presenters: previews, sources, hits, transcripts (no I/O)."""

from __future__ import annotations

import csv
import io
import json
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


def extract_document_score(document: Any) -> float | None:
    """Extract and round similarity/relevance score from a document or its metadata."""
    score = getattr(document, "score", None)
    if score is None and hasattr(document, "metadata") and isinstance(document.metadata, dict):
        score = document.metadata.get("score")
        if score is None:
            score = document.metadata.get("relevance_score")
    if score is not None:
        try:
            return round(float(score), 4)
        except (TypeError, ValueError):
            return None
    return None


def build_sources(documents) -> list[SourceInfo]:
    sources = []
    seen = set()
    for document in documents or []:
        metadata = getattr(document, "metadata", {}) or {}
        key = (
            metadata.get("file_id"),
            metadata.get("filename") or metadata.get("source"),
            metadata.get("page"),
            metadata.get("chunk_index"),
        )
        if key in seen:
            continue
        seen.add(key)
        score = extract_document_score(document)
        sources.append(
            SourceInfo(
                **_base_metadata(metadata),
                preview=preview_content(getattr(document, "page_content", "")),
                score=score,
            )
        )
    return sources


def build_search_hits(
    documents, score_threshold: float | None = None
) -> list[SearchHit]:
    hits = []
    rank = 1
    for document in documents or []:
        metadata = getattr(document, "metadata", {}) or {}
        score = extract_document_score(document)
        if score_threshold is not None and score is not None and score < score_threshold:
            continue
        hits.append(
            SearchHit(
                rank=rank,
                preview=preview_content(getattr(document, "page_content", "")),
                collection=metadata.get("collection"),
                score=score,
                **_base_metadata(metadata),
            )
        )
        rank += 1
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


def render_session_json(session_id: str, label: str | None, messages: list[dict]) -> str:
    """Render a conversation as structured JSON."""
    data = {
        "session_id": session_id,
        "label": label,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "messages": [
            {
                "role": message.get("role", ""),
                "content": message.get("content", ""),
            }
            for message in messages
        ],
    }
    return json.dumps(data, indent=2) + "\n"


def render_session_csv(session_id: str, label: str | None, messages: list[dict]) -> str:
    """Render a conversation as CSV rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["session_id", "label", "turn", "role", "content"])
    for idx, message in enumerate(messages, start=1):
        writer.writerow(
            [
                session_id,
                label or "",
                idx,
                message.get("role", ""),
                message.get("content", ""),
            ]
        )
    return output.getvalue()

