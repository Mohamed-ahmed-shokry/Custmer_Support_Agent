"""Core Knowledge Base Gap Detection, FAQ Article Drafting, and Self-Service Deflection Engine.

Provides automated detection of unanswered or low-coverage tenant inquiries,
scanning across escalated and low-CSAT sessions, structured Markdown KB article
synthesis from resolved support dialogues, and 1-click publishing directly into
the RAG document corpus with automated gap resolution and webhook alerts.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from api import db_utils, webhooks
from api.chroma_utils import ChunkingOptions, ChunkingStrategy, reindex_chunks_in_chroma
from api.sla import infer_session_category
from api.summarization import summarize_dialogue

logger = logging.getLogger(__name__)

# Phrases commonly indicating a RAG retriever fallback or refusal
FALLBACK_PHRASES = (
    "i don't have enough information",
    "i do not have enough information",
    "i don't know",
    "i do not know",
    "not mentioned in the provided documents",
    "not found in the provided context",
    "no documents provided",
    "cannot find any information",
    "unable to find information",
    "please contact management directly",
    "please contact our leasing office",
    "i couldn't find any details",
    "i could not find any details",
)


def is_unanswered_or_fallback_response(answer: str, sources_count: int = 0) -> bool:
    """Determine whether an assistant response indicates an unanswered query or knowledge gap."""
    clean_ans = (answer or "").strip().lower()
    if not clean_ans:
        return True
    if sources_count == 0 and any(p in clean_ans for p in FALLBACK_PHRASES):
        return True
    return any(p in clean_ans for p in FALLBACK_PHRASES[:6])


def dispatch_gap_detected_alert_if_needed(
    gap: dict[str, Any],
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    """Dispatch 'knowledge.gap_detected' webhook notification when a knowledge gap is logged."""
    event_data = {
        "gap_id": gap.get("id"),
        "query": gap.get("query"),
        "normalized_query": gap.get("normalized_query"),
        "category": gap.get("category"),
        "source_type": gap.get("source_type"),
        "session_id": gap.get("session_id"),
        "frequency": gap.get("frequency", 1),
        "priority": gap.get("priority", "medium"),
        "status": gap.get("status", "open"),
        "notes": gap.get("notes", ""),
        "created_at": gap.get("created_at"),
    }
    try:
        return webhooks.dispatch_event("knowledge.gap_detected", event_data, timeout=timeout)
    except Exception as exc:
        logger.warning("Failed dispatching knowledge.gap_detected webhook: %s", exc)
        return []


def dispatch_article_published_alert_if_needed(
    article: dict[str, Any],
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    """Dispatch 'knowledge.article_published' webhook when an article is published to RAG."""
    event_data = {
        "article_id": article.get("id"),
        "title": article.get("title"),
        "category": article.get("category"),
        "published_file_id": article.get("published_file_id"),
        "published_collection": article.get("published_collection"),
        "source_session_id": article.get("source_session_id"),
        "source_gap_id": article.get("source_gap_id"),
        "tags": article.get("tags", []),
        "status": article.get("status", "published"),
        "author": article.get("author", "support_agent"),
        "created_at": article.get("created_at"),
    }
    try:
        return webhooks.dispatch_event("knowledge.article_published", event_data, timeout=timeout)
    except Exception as exc:
        logger.warning("Failed dispatching knowledge.article_published webhook: %s", exc)
        return []


def scan_sessions_for_knowledge_gaps(limit: int = 100) -> dict[str, Any]:
    """Scan recent support sessions and low-CSAT feedback to automatically identify knowledge gaps.

    Evaluates:
      1. Sessions marked with status 'escalated'.
      2. Feedback items with score <= 2 or rating == -1.
      3. Sessions whose last response matches unanswered / fallback heuristics.
    """
    sessions = db_utils.get_all_sessions()[:limit]
    feedback_items, _ = db_utils.list_feedback(limit=limit, offset=0)

    gaps_created = 0
    gaps_incremented = 0
    scanned_count = len(sessions)
    new_gap_records: list[dict[str, Any]] = []

    # Map session_id to low CSAT feedback comments or ratings
    low_csat_sessions: dict[str, dict[str, Any]] = {}
    for fb in feedback_items:
        score = fb.get("score")
        rating = fb.get("rating")
        is_low = (score is not None and int(score) <= 2) or (rating == -1)  # noqa: PLR2004
        if is_low and fb.get("session_id"):
            low_csat_sessions[fb["session_id"]] = fb

    for sess in sessions:
        sid = sess["session_id"]
        status_val = (sess.get("status") or "active").lower()
        query_text = sess.get("preview") or db_utils.get_session_latest_user_query(sid)
        if not query_text or len(query_text.strip()) < 3:  # noqa: PLR2004
            continue

        cat = infer_session_category(sess.get("tags"), query=query_text)
        detected_reason: str | None = None
        source_type = "unanswered_query"
        gap_priority = "medium"

        if status_val == "escalated":
            detected_reason = "Escalated session tenant inquiry requires knowledge documentation."
            source_type = "escalated_session"
            gap_priority = "high"
        elif sid in low_csat_sessions:
            fb = low_csat_sessions[sid]
            comment = fb.get("comment") or ""
            detected_reason = f"Low CSAT feedback recorded for session. {comment}".strip()
            source_type = "low_csat"
            gap_priority = "high"
        else:
            # Check latest interaction for fallback response
            history = db_utils.get_chat_history(sid)
            if history:
                ai_messages = [
                    m["content"] for m in reversed(history)
                    if m.get("role") == "ai" and m.get("content")
                ]
                last_ai_ans = ai_messages[0] if ai_messages else ""
                if is_unanswered_or_fallback_response(last_ai_ans):
                    detected_reason = "Assistant gave fallback answer without sufficient context."
                    source_type = "unanswered_query"
                    gap_priority = "medium"

        if detected_reason:
            gap_res = db_utils.record_knowledge_gap(
                query=query_text.strip(),
                category=cat,
                source_type=source_type,
                session_id=sid,
                priority=gap_priority,
                notes=detected_reason,
            )
            if gap_res.get("deduplicated"):
                gaps_incremented += 1
            else:
                gaps_created += 1
                dispatch_gap_detected_alert_if_needed(gap_res)
            new_gap_records.append(gap_res)

    return {
        "scanned_sessions_count": scanned_count,
        "gaps_created": gaps_created,
        "gaps_incremented": gaps_incremented,
        "total_gaps_identified": gaps_created + gaps_incremented,
        "gaps": new_gap_records,
    }


def synthesize_article_from_session(
    session_id: str,
    author: str = "support_agent",
    category: str | None = None,
    link_gap_id: int | None = None,
) -> dict[str, Any]:
    """Synthesize a structured Markdown FAQ / Knowledge Article draft from a resolved session."""
    clean_sid = (session_id or "").strip()
    if not clean_sid:
        raise ValueError("session_id must not be blank.")

    meta = db_utils.get_session_metadata(clean_sid)
    if meta is None:
        raise ValueError(f"Session '{clean_sid}' not found.")

    history = db_utils.get_chat_history(clean_sid)
    if not history:
        raise ValueError(f"Session '{clean_sid}' has no recorded chat messages.")

    human_msgs = [
        m.get("content", "").strip() for m in history
        if m.get("role") == "human" and m.get("content")
    ]
    first_query = human_msgs[0] if human_msgs else "General inquiry"
    summary_data = summarize_dialogue(history)
    summary_text = summary_data.get("summary", "")
    key_points = summary_data.get("key_points", [])
    suggested_tags = summary_data.get("suggested_tags", [])

    existing_notes = (meta.get("resolution_notes") or "").strip()
    ai_msgs = [
        m.get("content", "").strip() for m in reversed(history)
        if m.get("role") == "ai" and m.get("content")
    ]
    last_response = ai_msgs[0] if ai_msgs else "Contact management office for guidance."
    resolution_body = (
        f"{existing_notes}\n\n{last_response}" if existing_notes else last_response
    )

    inferred_cat = category or infer_session_category(meta.get("tags"), query=first_query)
    clean_cat = db_utils.normalize_knowledge_category(inferred_cat)

    # Derive human-friendly title
    title_snippet = re.sub(r"^[^\w]+", "", first_query).strip()
    if len(title_snippet) > 60:  # noqa: PLR2004
        title_snippet = title_snippet[:57].rstrip() + "…"
    title = f"FAQ: {title_snippet}"

    # Build structured Markdown article content
    points_md = (
        "\n".join(f"- {p}" for p in key_points)
        if key_points
        else "- Refer to the property handbook for additional procedures."
    )
    content_md = (
        f"# {title}\n\n"
        f"**Category:** {clean_cat.title()}  \n"
        "**Status:** Verified Support Knowledge  \n\n"
        "## Summary\n"
        f"{summary_text}\n\n"
        "## Frequently Asked Question\n"
        f"**Q:** {first_query}\n\n"
        "## Resolution Guidance\n"
        f"{resolution_body}\n\n"
        "## Key Points & Steps\n"
        f"{points_md}\n\n"
        "---\n"
        f"*Compiled from support session `{clean_sid}` by `{author}`.*"
    )

    article = db_utils.create_knowledge_article(
        title=title,
        content_markdown=content_md,
        category=clean_cat,
        question_pattern=first_query,
        tags=suggested_tags,
        source_session_id=clean_sid,
        source_gap_id=link_gap_id,
        status="draft",
        author=author,
    )

    if link_gap_id is not None:
        db_utils.update_knowledge_gap(
            gap_id=link_gap_id,
            status="drafting",
            linked_article_id=article["id"],
            notes=f"Drafting article #{article['id']}: {title}",
        )

    return article


def publish_knowledge_article(  # noqa: PLR0912, PLR0913, PLR0917
    article_id: int,
    collection: str = "default",
    chunking_strategy: str = "markdown",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict[str, Any]:
    """Publish a knowledge article directly into the RAG document store and resolve linked gaps."""
    article = db_utils.get_knowledge_article(article_id)
    if article is None:
        raise ValueError(f"Knowledge article #{article_id} not found.")

    target_col = db_utils.normalize_collection(collection)
    slug = re.sub(r"[^a-z0-9]+", "_", article["title"].lower()).strip("_")[:40]
    filename = f"kb_{article_id}_{slug}.md"
    content_bytes = article["content_markdown"].encode("utf-8")
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    existing_doc = db_utils.get_document_by_hash(content_hash)
    if existing_doc is not None:
        file_id = existing_doc["id"]
    else:
        file_id = db_utils.insert_document_record(filename, target_col, content_hash)

    strat_enum = ChunkingStrategy(chunking_strategy)
    options = ChunkingOptions(
        strategy=strat_enum,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    db_utils.save_document_source(
        file_id=file_id,
        source_text=article["content_markdown"],
        strategy=strat_enum.value,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    indexed_in_chroma = False
    try:
        indexed_in_chroma = bool(
            reindex_chunks_in_chroma(
                file_id=file_id,
                source_text=article["content_markdown"],
                filename=filename,
                collection=target_col,
                options=options,
            )
        )
    except Exception as exc:
        logger.warning(
            "Vectorstore indexing skipped/failed for published article #%s: %s",
            article_id,
            exc,
        )

    updated_art = db_utils.update_knowledge_article(
        article_id=article_id,
        status="published",
        published_file_id=file_id,
        published_collection=target_col,
    )

    linked_gap_resolved = False
    source_gap_id = article.get("source_gap_id")
    if source_gap_id:
        db_utils.update_knowledge_gap(
            gap_id=source_gap_id,
            status="resolved",
            linked_article_id=article_id,
            notes=f"Resolved by published article #{article_id}: {article['title']}",
        )
        linked_gap_resolved = True

    if updated_art:
        dispatch_article_published_alert_if_needed(updated_art)

    return {
        "article": updated_art,
        "file_id": file_id,
        "collection": target_col,
        "indexed_in_vectorstore": indexed_in_chroma,
        "linked_gap_resolved": linked_gap_resolved,
    }


def get_knowledge_base_analytics() -> dict[str, Any]:
    """Calculate aggregated knowledge gap resolution metrics and self-service deflection KPIs."""
    gaps, total_gaps = db_utils.list_knowledge_gaps(limit=5000, offset=0)
    articles, total_articles = db_utils.list_knowledge_articles(limit=5000, offset=0)

    open_count = sum(1 for g in gaps if g.get("status") == "open")
    drafting_count = sum(1 for g in gaps if g.get("status") == "drafting")
    resolved_count = sum(1 for g in gaps if g.get("status") == "resolved")
    dismissed_count = sum(1 for g in gaps if g.get("status") == "dismissed")

    tot_freq = sum(int(g.get("frequency", 1)) for g in gaps)
    recurring_hits = sum(max(0, int(g.get("frequency", 1)) - 1) for g in gaps)

    category_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    for g in gaps:
        if g.get("status") in ("open", "drafting"):
            cat = str(g.get("category") or "general")
            prio = str(g.get("priority") or "medium")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            priority_counts[prio] = priority_counts.get(prio, 0) + 1

    draft_arts = sum(1 for a in articles if a.get("status") == "draft")
    published_arts = sum(1 for a in articles if a.get("status") == "published")
    archived_arts = sum(1 for a in articles if a.get("status") == "archived")

    resolution_rate = (
        round((resolved_count / total_gaps) * 100.0, 1) if total_gaps > 0 else 100.0
    )
    estimated_deflected = (published_arts * 5) + recurring_hits

    return {
        "total_gaps": total_gaps,
        "open_gaps_count": open_count,
        "drafting_gaps_count": drafting_count,
        "resolved_gaps_count": resolved_count,
        "dismissed_gaps_count": dismissed_count,
        "gap_resolution_rate": resolution_rate,
        "total_gap_queries_logged": tot_freq,
        "recurring_queries_count": recurring_hits,
        "category_distribution": category_counts,
        "priority_distribution": priority_counts,
        "total_articles": total_articles,
        "draft_articles_count": draft_arts,
        "published_articles_count": published_arts,
        "archived_articles_count": archived_arts,
        "estimated_deflected_queries": estimated_deflected,
    }

