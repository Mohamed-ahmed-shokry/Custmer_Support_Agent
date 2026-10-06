"""Automated AI macro suggestions and query intent classification engine.

Provides tenant query intent detection, domain entity extraction (unit IDs, resident names),
and multi-factor ranking to suggest relevant property management canned responses.
"""

from __future__ import annotations

import re
from typing import Any

from api.macros import render_template

# Intent taxonomy definitions for property management support
INTENT_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "maintenance_emergency": [
        re.compile(r"\b(leak|leaking|flooding|flood|pipe\s*burst|burst\s*pipe)\b", re.IGNORECASE),
        re.compile(r"\b(gas\s*leak|gas\s*odor|smell\s*gas)\b", re.IGNORECASE),
        re.compile(r"\b(fire|smoke|sparks?|electrical\s*fire)\b", re.IGNORECASE),
        re.compile(r"\b(no\s*heat|freezing|heater\s*broken|furnace\s*out)\b", re.IGNORECASE),
        re.compile(r"\b(lockout|locked\s*out|broken\s*lock|cannot\s*enter)\b", re.IGNORECASE),
        re.compile(r"\b(ceiling\s*collapse|water\s*pouring)\b", re.IGNORECASE),
    ],
    "maintenance_routine": [
        re.compile(
            r"\b(repair|fix|maintenance|broken|not\s*working|clogged|dripping)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(dishwasher|refrigerator|fridge|stove|oven|microwave|washer|dryer)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(ac|air\s*condition(?:ing|er)?|thermostat|filter|light\s*bulb)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(faucet|sink|toilet|drain|garbage\s*disposal|pest|roach|mice)\b",
            re.IGNORECASE,
        ),
    ],
    "rent_payment": [
        re.compile(
            r"\b(pay\s*rent|rent\s*payment|payment\s*method|portal|pay\s*online)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b(rent\s*due|due\s*date|grace\s*period|late\s*fee)\b", re.IGNORECASE),
        re.compile(r"\b(ach|direct\s*debit|credit\s*card|rent\s*balance|invoice)\b", re.IGNORECASE),
    ],
    "lease_renewal": [
        re.compile(r"\b(renew|renewal|lease\s*renewal|extend\s*lease)\b", re.IGNORECASE),
        re.compile(r"\b(lease\s*term|lease\s*extension|renewing\s*my\s*lease)\b", re.IGNORECASE),
        re.compile(r"\b(lease\s*expir(?:ing|ation|es?))\b", re.IGNORECASE),
    ],
    "move_out": [
        re.compile(
            r"\b(move\s*out|moving\s*out|vacate|vacating|notice\s*to\s*vacate)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b(security\s*deposit|deposit\s*refund|deposit\s*return)\b", re.IGNORECASE),
        re.compile(r"\b(walkthrough|final\s*inspection|forwarding\s*address)\b", re.IGNORECASE),
    ],
    "general_inquiry": [
        re.compile(
            r"\b(office\s*hours|contact\s*info|phone\s*number|email\s*address)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b(parking|visitor\s*parking|permit|parking\s*space)\b", re.IGNORECASE),
        re.compile(r"\b(package|mail|gym|pool|trash|dumpster|quiet\s*hours)\b", re.IGNORECASE),
    ],
}

# Entity extraction patterns
_UNIT_PATTERNS = [
    re.compile(
        r"\b(?:unit|apt|apartment|suite|flat)\s*(?:#|no\.?|num\.?)?\s*([A-Za-z0-9\-]+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|\s|[^\w])#\s*([0-9]{1,4}[A-Za-z]?)\b"),
]

_NAME_PATTERNS = [
    re.compile(
        r"\b(?:my\s*name\s*is|this\s*is|i\s*am|i'm)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b",
        re.IGNORECASE,
    ),
]

# Stopwords for lexical token matching
_STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "it",
    "my", "our", "your", "we", "i", "me", "he", "she", "they", "this", "that", "with",
    "please", "can", "help", "need", "have", "has", "do", "does", "be", "been", "was",
}


def detect_query_intent(query: str) -> tuple[str, float]:
    """Detect property management support intent from tenant query text.

    Args:
        query: Incoming customer message text.

    Returns:
        A tuple of ``(intent_name, confidence)`` where confidence is between 0.0 and 1.0.
    """
    if not query or not query.strip():
        return "unknown", 0.0

    text = query.strip()
    best_intent = "unknown"
    best_score = 0.0

    for intent, patterns in INTENT_PATTERNS.items():
        matched_count = 0
        for pattern in patterns:
            if pattern.search(text):
                matched_count += 1

        if matched_count > 0:
            confidence = min(0.50 + (matched_count * 0.25), 0.95)
            if intent == "maintenance_emergency":
                confidence = min(confidence + 0.05, 0.99)
            if confidence > best_score:
                best_score = confidence
                best_intent = intent

    return best_intent, round(best_score, 2)


def extract_query_entities(query: str) -> dict[str, str]:
    """Extract domain entities such as unit numbers and customer names from query text.

    Args:
        query: Incoming customer message text.

    Returns:
        Dictionary mapping entity keys (e.g. ``unit_id``, ``customer_name``) to extracted values.
    """
    if not query or not query.strip():
        return {}

    entities: dict[str, str] = {}

    for pattern in _UNIT_PATTERNS:
        match = pattern.search(query)
        if match:
            unit_val = match.group(1).strip()
            if unit_val:
                entities["unit_id"] = f"Unit {unit_val}"
                break

    for pattern in _NAME_PATTERNS:
        match = pattern.search(query)
        if match:
            name_val = match.group(1).strip()
            if name_val:
                entities["customer_name"] = name_val
                break

    return entities


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alpha tokens, removing common stopwords."""
    tokens = re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


_INTENT_ALIGNMENT_SPECS: dict[str, dict[str, Any]] = {
    "maintenance_emergency": {
        "tags": {"emergency", "urgent"},
        "categories": {"maintenance"},
        "score": 0.90,
        "reason": "Matches emergency maintenance intent",
    },
    "maintenance_routine": {
        "tags": {"routine", "maintenance"},
        "categories": {"maintenance"},
        "score": 0.85,
        "reason": "Matches routine maintenance intent",
    },
    "rent_payment": {
        "tags": {"rent", "payment", "billing"},
        "categories": {"billing"},
        "score": 0.90,
        "reason": "Matches rent & billing payment intent",
    },
    "lease_renewal": {
        "tags": {"renewal", "leasing", "lease"},
        "categories": {"leasing"},
        "score": 0.90,
        "reason": "Matches lease renewal intent",
    },
    "move_out": {
        "tags": {"move-out", "deposit"},
        "categories": set(),
        "score": 0.90,
        "reason": "Matches move-out & deposit return intent",
    },
    "general_inquiry": {
        "tags": set(),
        "categories": {"general"},
        "score": 0.75,
        "reason": "Matches general inquiry intent",
    },
}


def _score_intent_alignment(
    detected_intent: str, category: str, tags: list[str]
) -> tuple[float, str | None]:
    """Score alignment between detected query intent and macro attributes."""
    spec = _INTENT_ALIGNMENT_SPECS.get(detected_intent)
    if not spec:
        return 0.0, None

    tags_set = set(tags)
    matches_tags = bool(tags_set.intersection(spec["tags"]))
    matches_cat = category in spec["categories"]

    if matches_tags or matches_cat:
        return float(spec["score"]), str(spec["reason"])

    return 0.0, None


def _calculate_macro_match(
    query: str,
    query_tokens: set[str],
    detected_intent: str,
    macro: dict[str, Any],
) -> tuple[float, list[str]]:
    """Calculate multi-factor match score and explanation for a macro template.

    Args:
        query: Raw query text.
        query_tokens: Tokenized set of words from query.
        detected_intent: Detected domain intent.
        macro: Macro dictionary from database.

    Returns:
        Tuple of ``(score, match_reasons)`` with score between 0.0 and 1.0.
    """
    reasons: list[str] = []
    shortcut = str(macro.get("shortcut", "")).lower()

    if shortcut and shortcut in query.lower():
        return 1.0, [f"Direct shortcut trigger match: {shortcut}"]

    category = str(macro.get("category", "")).lower()
    raw_tags = macro.get("tags", [])
    if isinstance(raw_tags, str):
        macro_tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        macro_tags = [str(t).strip().lower() for t in raw_tags if str(t).strip()]
    else:
        macro_tags = []

    intent_score, intent_reason = _score_intent_alignment(detected_intent, category, macro_tags)
    if intent_reason:
        reasons.append(intent_reason)

    title = str(macro.get("title", ""))
    content = str(macro.get("content", ""))
    macro_text = f"{title} {' '.join(macro_tags)} {content}"
    macro_tokens = _tokenize(macro_text)

    overlap_tokens = query_tokens.intersection(macro_tokens)
    if query_tokens:
        keyword_overlap = min(len(overlap_tokens) / max(len(query_tokens), 1), 1.0)
    else:
        keyword_overlap = 0.0

    if overlap_tokens:
        sample_words = sorted(overlap_tokens)[:4]
        reasons.append(f"Matched keywords: {', '.join(sample_words)}")

    cat_bonus = 0.0
    if category and category in query.lower():
        cat_bonus = 0.20
        reasons.append(f"Category alignment: {macro.get('category')}")

    if intent_score > 0:
        composite = (0.80 * intent_score) + (0.15 * keyword_overlap) + (0.05 * cat_bonus)
    else:
        composite = (0.75 * keyword_overlap) + (0.25 * cat_bonus)

    final_score = round(min(max(composite, 0.0), 0.98), 2)
    return final_score, reasons


def suggest_macros_for_query(  # noqa: PLR0913, PLR0917
    query: str,
    macros: list[dict[str, Any]],
    min_score: float = 0.3,
    limit: int = 3,
    category: str | None = None,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Rank candidate macros against customer query and return top suggestions.

    Args:
        query: Incoming customer query text.
        macros: Candidate macro records from database.
        min_score: Minimum match score threshold (0.0 to 1.0).
        limit: Maximum number of suggestions to return.
        category: Optional category filter.
        session_id: Optional active session ID to inject into suggested variables.

    Returns:
        List of ranked macro suggestion dictionaries sorted by descending score.
    """
    if not query or not query.strip() or not macros:
        return []

    detected_intent, _ = detect_query_intent(query)
    query_tokens = _tokenize(query)
    extracted_entities = extract_query_entities(query)

    if session_id:
        extracted_entities["session_id"] = session_id

    candidates: list[dict[str, Any]] = []

    for macro in macros:
        macro_cat = str(macro.get("category", ""))
        if category and macro_cat.lower() != category.strip().lower():
            continue

        score, reasons = _calculate_macro_match(
            query=query,
            query_tokens=query_tokens,
            detected_intent=detected_intent,
            macro=macro,
        )

        if score >= min_score:
            suggested_vars = dict(extracted_entities)
            content = str(macro.get("content", ""))
            rendered_preview, _ = render_template(content, suggested_vars, fallback_defaults=True)

            raw_tags = macro.get("tags", [])
            if isinstance(raw_tags, str):
                tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif isinstance(raw_tags, list):
                tags_list = [str(t) for t in raw_tags]
            else:
                tags_list = []

            candidates.append({
                "macro_id": macro["id"],
                "title": macro["title"],
                "shortcut": macro["shortcut"],
                "category": macro["category"],
                "content": content,
                "score": score,
                "match_reasons": reasons,
                "detected_intent": detected_intent,
                "status_action": macro.get("status_action"),
                "tags": tags_list,
                "suggested_variables": suggested_vars,
                "rendered_preview": rendered_preview,
            })

    candidates.sort(key=lambda x: (x["score"], -x["macro_id"]), reverse=True)
    return candidates[:limit]
