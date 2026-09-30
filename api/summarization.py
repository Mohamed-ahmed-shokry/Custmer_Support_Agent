"""Conversation summarization and dialogue intelligence for customer support sessions.

Provides extractive and LLM-assisted conversation summarization, key points extraction,
customer sentiment classification, and domain tag suggestions.
Runs 100% offline without external API dependencies or cost, with graceful LLM fallback.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

TAG_KEYWORDS: dict[str, list[str]] = {
    "lease": ["lease", "tenant", "landlord", "rent", "sublease", "deposit", "eviction"],
    "agreement": ["agreement", "contract", "terms", "clause", "signing", "amendment"],
    "maintenance": [
        "maintenance",
        "repair",
        "leak",
        "broken",
        "plumbing",
        "hvac",
        "pest",
        "heat",
        "ac",
    ],
    "billing": [
        "bill",
        "billing",
        "invoice",
        "charge",
        "fee",
        "payment",
        "refund",
        "credit",
        "autopay",
    ],
    "policy": ["policy", "rules", "guidelines", "pets", "smoking", "parking", "noise", "hoa"],
    "escalation": [
        "escalate",
        "escalation",
        "manager",
        "supervisor",
        "lawyer",
        "dispute",
        "urgent",
    ],
    "techwave": ["techwave"],
    "greengrow": ["greengrow", "ecoharvest"],
    "quantumnext": ["quantumnext"],
}

POSITIVE_WORDS = {
    "thank",
    "thanks",
    "great",
    "awesome",
    "excellent",
    "resolved",
    "perfect",
    "helpful",
    "good",
    "appreciate",
    "happy",
    "pleased",
    "wonderful",
    "amazing",
}

NEGATIVE_WORDS = {
    "unhappy",
    "terrible",
    "broken",
    "frustrated",
    "bad",
    "issue",
    "problem",
    "fail",
    "error",
    "complaint",
    "cancel",
    "worst",
    "disappointed",
    "urgent",
    "immediately",
    "refund",
    "horrible",
    "angry",
    "unacceptable",
}


def _tokenize(text: str) -> list[str]:
    return [word.lower() for word in re.findall(r"\b[A-Za-z]{2,}\b", text or "")]


def detect_sentiment(text: str) -> str:
    """Classify sentiment into 'positive', 'negative', or 'neutral'."""
    tokens = _tokenize(text)
    if not tokens:
        return "neutral"

    pos_count = sum(1 for t in tokens if t in POSITIVE_WORDS)
    neg_count = sum(1 for t in tokens if t in NEGATIVE_WORDS)

    if pos_count > neg_count:
        return "positive"
    if neg_count > pos_count:
        return "negative"
    return "neutral"


def suggest_tags(text: str) -> list[str]:
    """Suggest domain category tags based on keyword occurrences."""
    lower_text = (text or "").lower()
    matched_tags: set[str] = set()

    for tag, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, lower_text):
                matched_tags.add(tag)
                break

    return sorted(matched_tags)


def _truncate_snippet(text: str, max_chars: int = 150) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _build_extractive_summary(
    human_messages: list[str],
    ai_messages: list[str],
    sentiment: str,
    suggested_tags: list[str],
) -> dict[str, Any]:
    """Build a deterministic extractive summary from conversation dialogue turns."""
    if not human_messages and not ai_messages:
        return {
            "summary": "No conversation messages recorded.",
            "key_points": [],
            "sentiment": "neutral",
            "suggested_tags": [],
        }

    key_points: list[str] = []

    if human_messages:
        primary_inquiry = human_messages[0].strip()
        key_points.append(f"Customer inquiry: {_truncate_snippet(primary_inquiry, 140)}")
        if len(human_messages) > 1:
            follow_up = human_messages[-1].strip()
            key_points.append(f"Follow-up query: {_truncate_snippet(follow_up, 140)}")
    else:
        primary_inquiry = "General discussion"

    if ai_messages:
        primary_response = ai_messages[0].strip()
        key_points.append(f"Support response: {_truncate_snippet(primary_response, 140)}")
        if len(ai_messages) > 1:
            latest_resolution = ai_messages[-1].strip()
            key_points.append(
                f"Resolution details: {_truncate_snippet(latest_resolution, 140)}"
            )
    else:
        primary_response = "Awaiting response"

    inquiry_preview = _truncate_snippet(primary_inquiry, 180)
    response_preview = _truncate_snippet(primary_response, 180)

    if human_messages and ai_messages:
        summary_text = f"Customer asked: {inquiry_preview}. Support provided: {response_preview}."
    elif human_messages:
        summary_text = f"Customer asked: {inquiry_preview}. (Awaiting response from support)."
    else:
        summary_text = f"Support message: {response_preview}."

    return {
        "summary": summary_text,
        "key_points": key_points,
        "sentiment": sentiment,
        "suggested_tags": suggested_tags,
    }


def _default_llm(model: str = "gpt-4o-mini"):
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 - lazy, see ADR-001

    return ChatOpenAI(model=model, temperature=0.0)


def summarize_dialogue(
    messages: list[dict[str, str]],
    model: str | None = None,
    llm: Any = None,
) -> dict[str, Any]:
    """Summarize a conversation dialogue, extracting key points, sentiment, and tags.

    Attempts LLM summarization if an LLM is provided or OpenAI API key is set,
    falling back seamlessly to extractive analysis.
    """
    human_messages = [
        m["content"] for m in messages if m.get("role") == "human" and m.get("content")
    ]
    ai_messages = [
        m["content"] for m in messages if m.get("role") == "ai" and m.get("content")
    ]

    all_human_text = " ".join(human_messages)
    full_text = " ".join(m.get("content", "") for m in messages)

    detected_sentiment = detect_sentiment(all_human_text or full_text)
    tags = suggest_tags(full_text)

    # If no LLM requested or explicitly provided, or no API key in environment, use extractive
    has_api_key = bool(os.getenv("OPENAI_API_KEY"))
    if not llm and (not model or not has_api_key):
        return _build_extractive_summary(
            human_messages, ai_messages, detected_sentiment, tags
        )

    # Attempt LLM-assisted summarization with robust fallback
    try:
        active_llm = llm or _default_llm(model=model or "gpt-4o-mini")
        dialogue_transcript = "\n".join(
            f"{m.get('role', 'speaker').upper()}: {m.get('content', '')}" for m in messages
        )
        prompt = (
            "You are a customer support triage assistant. Summarize the following dialogue.\n"
            "Provide a concise summary paragraph (2-3 sentences) capturing the customer's problem "
            "and the resolution or guidance provided.\n\n"
            f"DIALOGUE:\n{dialogue_transcript}\n\n"
            "Summary:"
        )
        response = active_llm.invoke(prompt)
        content = getattr(response, "content", "")
        summary_str = str(content).strip()
        if summary_str:
            extractive_res = _build_extractive_summary(
                human_messages, ai_messages, detected_sentiment, tags
            )
            extractive_res["summary"] = summary_str
            return extractive_res
    except Exception:
        logger.exception("LLM dialogue summarization failed, using extractive summary")

    return _build_extractive_summary(human_messages, ai_messages, detected_sentiment, tags)
