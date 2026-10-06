"""Unit tests for automated AI macro suggestions and query intent classification engine."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest
from api.db_utils import DEFAULT_MACROS
from api.macro_suggestions import (
    _calculate_macro_match,
    detect_query_intent,
    extract_query_entities,
    suggest_macros_for_query,
)

# Sample test macros mimicking database rows
MOCK_MACROS = [
    {
        "id": 1,
        "title": "Emergency Maintenance Dispatch",
        "shortcut": "/emerg-maint",
        "category": "Maintenance",
        "content": "Emergency dispatched for {unit_id}. Call {support_contact}.",
        "tags": "maintenance, urgent, emergency",
        "status_action": "escalated",
    },
    {
        "id": 2,
        "title": "Routine Maintenance Scheduled",
        "shortcut": "/maint-scheduled",
        "category": "Maintenance",
        "content": "Routine maintenance scheduled for {unit_id}.",
        "tags": "maintenance, routine",
        "status_action": "active",
    },
    {
        "id": 3,
        "title": "Online Rent Payment Instructions",
        "shortcut": "/rent-pay",
        "category": "Billing",
        "content": "Pay rent online at portal. Accepted methods: ACH, debit.",
        "tags": "billing, rent, payment",
        "status_action": "resolved",
    },
    {
        "id": 4,
        "title": "Lease Renewal Offer",
        "shortcut": "/lease-renewal",
        "category": "Leasing",
        "content": "Renew your lease terms with us, {customer_name}.",
        "tags": "leasing, renewal",
        "status_action": "active",
    },
    {
        "id": 5,
        "title": "Move-Out Inspection & Deposit Timeline",
        "shortcut": "/move-out",
        "category": "Leasing",
        "content": "Move-out inspection and deposit return details.",
        "tags": "move-out, deposit, inspection",
        "status_action": "resolved",
    },
    {
        "id": 6,
        "title": "General Inquiry Resolution",
        "shortcut": "/resolve",
        "category": "General",
        "content": "Glad I could assist you today! {agent_name}",
        "tags": "general, closing",
        "status_action": "resolved",
    },
]


def test_detect_query_intent_empty_and_whitespace():
    intent, conf = detect_query_intent("")
    assert intent == "unknown"
    assert conf == 0.0

    intent, conf = detect_query_intent("   ")
    assert intent == "unknown"
    assert conf == 0.0


@pytest.mark.parametrize(
    ("query", "expected_intent"),
    [
        ("Water is leaking from the pipe and flooding my kitchen!", "maintenance_emergency"),
        ("I smell gas odor near the stove", "maintenance_emergency"),
        ("I am locked out of my apartment", "maintenance_emergency"),
        ("The dishwasher is broken and won't turn on", "maintenance_routine"),
        ("My AC is not cooling properly and the filter is dirty", "maintenance_routine"),
        ("How can I pay my rent online through the portal?", "rent_payment"),
        ("When is rent due and what is the grace period?", "rent_payment"),
        ("I would like to renew my lease for another year", "lease_renewal"),
        ("When does my lease expiration occur?", "lease_renewal"),
        ("I am moving out next month, how do I get my security deposit refund?", "move_out"),
        ("What are the office hours and where is visitor parking?", "general_inquiry"),
    ],
)
def test_detect_query_intent_recognized(query: str, expected_intent: str):
    intent, conf = detect_query_intent(query)
    assert intent == expected_intent
    assert conf > 0.40


def test_extract_query_entities_empty():
    assert extract_query_entities("") == {}
    assert extract_query_entities("   ") == {}


def test_extract_query_entities_unit_variations():
    assert extract_query_entities("There is a leak in unit 402") == {"unit_id": "Unit 402"}
    assert extract_query_entities("Apt 3B has no hot water") == {"unit_id": "Unit 3B"}
    assert extract_query_entities("Apartment 12 needs repair") == {"unit_id": "Unit 12"}
    assert extract_query_entities("Problem in #501") == {"unit_id": "Unit 501"}
    assert extract_query_entities("Suite 2A heater is broken") == {"unit_id": "Unit 2A"}


def test_extract_query_entities_customer_name():
    entities = extract_query_entities("My name is John Smith and I live in Unit 10")
    assert entities.get("customer_name") == "John Smith"
    assert entities.get("unit_id") == "Unit 10"

    entities2 = extract_query_entities("This is Alice Johnson from Apt 4")
    assert entities2.get("customer_name") == "Alice Johnson"
    assert entities2.get("unit_id") == "Unit 4"


def test_calculate_macro_match_direct_shortcut():
    score, reasons = _calculate_macro_match(
        query="Please run /emerg-maint for this ticket",
        query_tokens={"please", "run", "emerg", "maint"},
        detected_intent="unknown",
        macro=MOCK_MACROS[0],
    )
    assert score == 1.0
    assert any("/emerg-maint" in r for r in reasons)


def test_calculate_macro_match_intent_and_keyword_overlap():
    query = "Water is flooding my bathroom"
    tokens = {"water", "flooding", "bathroom"}
    score, reasons = _calculate_macro_match(
        query=query,
        query_tokens=tokens,
        detected_intent="maintenance_emergency",
        macro=MOCK_MACROS[0],
    )
    assert score > 0.50
    assert any("emergency" in r.lower() for r in reasons)


def test_suggest_macros_for_query_empty_cases():
    assert suggest_macros_for_query("", MOCK_MACROS) == []
    assert suggest_macros_for_query("   ", MOCK_MACROS) == []
    assert suggest_macros_for_query("test query", []) == []


def test_suggest_macros_emergency_query():
    query = "Help! There is a major pipe burst and flooding in Apt 4B! My name is Sarah Connor"
    suggestions = suggest_macros_for_query(
        query=query,
        macros=MOCK_MACROS,
        min_score=0.4,
        limit=3,
        session_id="sess-test-123",
    )
    assert len(suggestions) > 0
    top = suggestions[0]
    assert top["title"] == "Emergency Maintenance Dispatch"
    assert top["shortcut"] == "/emerg-maint"
    assert top["category"] == "Maintenance"
    assert top["score"] >= 0.70
    assert top["detected_intent"] == "maintenance_emergency"
    assert top["suggested_variables"]["unit_id"] == "Unit 4B"
    assert top["suggested_variables"]["customer_name"] == "Sarah Connor"
    assert top["suggested_variables"]["session_id"] == "sess-test-123"
    assert "Unit 4B" in top["rendered_preview"]
    assert "Emergency dispatched" in top["rendered_preview"]


def test_suggest_macros_rent_payment():
    query = "How do I pay rent online with my bank debit card?"
    suggestions = suggest_macros_for_query(
        query=query,
        macros=MOCK_MACROS,
        min_score=0.4,
        limit=3,
    )
    assert len(suggestions) > 0
    top = suggestions[0]
    assert top["title"] == "Online Rent Payment Instructions"
    assert top["shortcut"] == "/rent-pay"
    assert top["category"] == "Billing"
    assert top["score"] >= 0.65


def test_suggest_macros_category_filter():
    query = "I need maintenance on my sink in unit 102"
    suggestions = suggest_macros_for_query(
        query=query,
        macros=MOCK_MACROS,
        category="Billing",
        min_score=0.3,
    )
    for s in suggestions:
        assert s["category"] == "Billing"


def test_suggest_macros_min_score_filtering():
    query = "Random text with no relevance whatsoever"
    suggestions = suggest_macros_for_query(
        query=query,
        macros=MOCK_MACROS,
        min_score=0.90,
    )
    assert suggestions == []


def test_suggest_macros_limit_respected():
    query = "maintenance request for repair and fix"
    suggestions = suggest_macros_for_query(
        query=query,
        macros=MOCK_MACROS,
        min_score=0.1,
        limit=2,
    )
    assert len(suggestions) <= 2


def test_suggest_macros_with_default_macros_data():
    formatted_defaults = []
    for idx, item in enumerate(DEFAULT_MACROS, start=1):
        formatted_defaults.append({
            "id": idx,
            "title": item["title"],
            "shortcut": item["shortcut"],
            "category": item["category"],
            "content": item["content"],
            "tags": item["tags"],
            "status_action": item.get("status_action"),
        })

    suggestions = suggest_macros_for_query(
        query="I want to renew my lease contract next month",
        macros=formatted_defaults,
        min_score=0.5,
    )
    assert len(suggestions) > 0
    top = suggestions[0]
    assert top["shortcut"] == "/lease-renewal"
    assert top["category"] == "Leasing"
