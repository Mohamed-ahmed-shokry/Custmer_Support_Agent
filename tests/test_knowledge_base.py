from unittest.mock import patch

import pytest
from api import db_utils, knowledge_base


@pytest.fixture(autouse=True)
def clean_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_document_store()
    db_utils.create_session_labels()
    db_utils.create_feedback()
    db_utils.create_knowledge_gaps()
    db_utils.create_knowledge_articles()
    yield


def test_is_unanswered_or_fallback_response():
    assert knowledge_base.is_unanswered_or_fallback_response("I do not know.") is True
    assert knowledge_base.is_unanswered_or_fallback_response("No documents provided.") is True
    assert (
        knowledge_base.is_unanswered_or_fallback_response(
            "I don't know the exact schedule", sources_count=0
        )
        is True
    )
    assert (
        knowledge_base.is_unanswered_or_fallback_response(
            "Pool is open from 9 AM to 10 PM.", sources_count=2
        )
        is False
    )
    assert knowledge_base.is_unanswered_or_fallback_response("", sources_count=1) is True


def test_dispatch_gap_alert_and_article_alert():
    with patch("api.webhooks.dispatch_event") as mock_dispatch:
        gap = {
            "id": 1,
            "query": "Is quiet hours enforced?",
            "frequency": 2,
            "category": "policy",
            "priority": "medium",
        }
        knowledge_base.dispatch_gap_detected_alert_if_needed(gap)
        mock_dispatch.assert_called_once()
        assert mock_dispatch.call_args[0][0] == "knowledge.gap_detected"

    with patch("api.webhooks.dispatch_event") as mock_dispatch_art:
        art = {
            "id": 10,
            "title": "Gym & Pool Rules",
            "category": "policy",
            "slug": "gym_pool_rules",
            "version": 1,
        }
        knowledge_base.dispatch_article_published_alert_if_needed(art)
        mock_dispatch_art.assert_called_once()
        assert mock_dispatch_art.call_args[0][0] == "knowledge.article_published"


def test_scan_sessions_for_knowledge_gaps():
    db_utils.insert_application_logs(
        "sess-fallback",
        "Can I have two dogs in unit 402?",
        "I do not have enough information about pet policies in unit 402.",
        "test-model",
    )
    db_utils.insert_feedback("sess-fallback", rating=-1, comment="Bot didn't know pets policy")
    db_utils.update_session_metadata("sess-fallback", status="escalated")

    db_utils.insert_application_logs(
        "sess-good",
        "What is the Wi-Fi password?",
        "Wi-Fi is ResidentWiFi2026.",
        "test-model",
    )
    db_utils.insert_feedback("sess-good", rating=1)

    res = knowledge_base.scan_sessions_for_knowledge_gaps(limit=50)
    min_scanned = 2
    assert res["scanned_sessions_count"] >= min_scanned
    assert res["total_gaps_identified"] >= 1
    assert len(res["gaps"]) >= 1

    gap = res["gaps"][0]
    assert "dog" in gap["query"].lower() or "pet" in gap["query"].lower()
    assert gap["status"] == "open"
    assert gap["frequency"] == 1


def test_synthesize_article_from_session():
    db_utils.insert_application_logs(
        "sess-synth",
        "How do I schedule a move-in freight elevator?",
        (
            "To reserve the freight elevator, submit a request via the resident portal "
            "at least 48 hours in advance. A $100 refundable security deposit is required."
        ),
        "test-model",
    )
    db_utils.update_session_metadata(
        session_id="sess-synth",
        resolution_notes="Confirmed elevator reservation portal instructions.",
    )

    article = knowledge_base.synthesize_article_from_session(
        "sess-synth",
        author="agent_sarah",
        category="general",
    )

    assert article["id"] is not None
    assert "freight elevator" in article["title"].lower()
    assert article["category"] == "general"
    assert "freight elevator" in article["content_markdown"].lower()
    assert article["status"] == "draft"
    assert article["source_session_id"] == "sess-synth"


def test_publish_knowledge_article():
    gap = db_utils.record_knowledge_gap(
        query="Where can I park my bicycle?",
        category="policy",
    )
    art = db_utils.create_knowledge_article(
        title="Bicycle Storage Policy",
        content_markdown="# Bicycle Storage\n\nBikes must be stored in bike room B1.",
        category="policy",
        tags=["bikes", "storage"],
        source_gap_id=gap["id"],
    )

    mock_resp = {"total_chunks": 1, "indexed": 1}
    with patch("api.chroma_utils.reindex_chunks_in_chroma", return_value=mock_resp):
        result = knowledge_base.publish_knowledge_article(
            art["id"],
            collection="default",
        )

    assert result["article"]["id"] == art["id"]
    assert result["file_id"] is not None
    assert result["article"]["status"] == "published"
    assert result["linked_gap_resolved"] is True

    # Check database state
    updated_art = db_utils.get_knowledge_article(art["id"])
    assert updated_art["status"] == "published"
    assert updated_art["published_file_id"] == result["file_id"]

    updated_gap = db_utils.get_knowledge_gap(gap["id"])
    assert updated_gap["status"] == "resolved"
    assert updated_gap["linked_article_id"] == art["id"]


def test_get_knowledge_base_analytics():
    db_utils.record_knowledge_gap("How to book clubhouse?", category="general", priority="high")
    art = db_utils.create_knowledge_article(
        title="Clubhouse Booking",
        content_markdown="Reserve at leasing office.",
        category="general",
    )
    db_utils.update_knowledge_article(art["id"], status="published")

    analytics = knowledge_base.get_knowledge_base_analytics()
    assert analytics["total_gaps"] >= 1
    assert analytics["open_gaps_count"] >= 1
    assert analytics["total_articles"] >= 1
    assert analytics["published_articles_count"] >= 1
    assert "gap_resolution_rate" in analytics
    assert "priority_distribution" in analytics
    assert "category_distribution" in analytics
