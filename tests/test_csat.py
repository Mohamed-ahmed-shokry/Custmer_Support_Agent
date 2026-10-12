"""Unit tests for CSAT summary calculation and low-CSAT alert engine."""

from unittest.mock import patch

from api import csat, db_utils


def test_calculate_csat_summary_empty(monkeypatch, tmp_path):
    db_path = tmp_path / "empty_test.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_feedback()

    summary = csat.calculate_csat_summary()
    assert summary["total_responses"] == 0
    assert summary["avg_csat_score"] == 0.0
    assert summary["avg_resolution_score"] is None
    assert summary["avg_helpfulness_score"] is None
    assert summary["avg_speed_score"] is None
    assert summary["satisfaction_rate"] == 0.0
    assert summary["dissatisfaction_rate"] == 0.0
    assert summary["star_distribution"] == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    assert summary["pending_review_count"] == 0
    assert summary["followup_required_count"] == 0


def test_calculate_csat_summary_populated(monkeypatch, tmp_path):
    db_path = tmp_path / "populated_test.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_session_labels()
    db_utils.create_feedback()

    # 1st: 5 stars (positive)
    f1 = db_utils.submit_csat_feedback(
        "s-1",
        score=5,
        resolution_satisfaction=5,
        agent_helpfulness=4,
        response_speed=5,
    )
    # 2nd: 4 stars (positive)
    db_utils.submit_csat_feedback(
        "s-2",
        score=4,
        resolution_satisfaction=4,
        agent_helpfulness=4,
        response_speed=4,
    )
    # 3rd: 1 star (negative)
    f3 = db_utils.submit_csat_feedback(
        "s-3",
        score=1,
        resolution_satisfaction=1,
        agent_helpfulness=2,
        response_speed=1,
    )
    # 4th: legacy binary rating -1 (maps to 1 star, negative)
    db_utils.insert_feedback("s-4", -1)

    # Update review statuses
    db_utils.update_feedback_review(f1["id"], review_status="reviewed")
    db_utils.update_feedback_review(f3["id"], review_status="followup_required")

    summary = csat.calculate_csat_summary()
    expected_responses = 4
    assert summary["total_responses"] == expected_responses
    # Scores: 5, 4, 1, 1 -> avg = 11/4 = 2.75
    expected_avg_csat = 2.75
    assert summary["avg_csat_score"] == expected_avg_csat
    # Resolution: 5, 4, 1 -> avg = 10/3 = 3.33
    expected_avg_res = 3.33
    assert summary["avg_resolution_score"] == expected_avg_res
    # Helpfulness: 4, 4, 2 -> avg = 10/3 = 3.33
    expected_avg_help = 3.33
    assert summary["avg_helpfulness_score"] == expected_avg_help
    # Speed: 5, 4, 1 -> avg = 10/3 = 3.33
    expected_avg_speed = 3.33
    assert summary["avg_speed_score"] == expected_avg_speed

    # 2 positive (5, 4), 2 negative (1, 1) -> 50% each
    expected_sat = 50.0
    assert summary["satisfaction_rate"] == expected_sat
    assert summary["dissatisfaction_rate"] == expected_sat

    assert summary["star_distribution"][1] == 2  # noqa: PLR2004
    assert summary["star_distribution"][4] == 1
    assert summary["star_distribution"][5] == 1

    # s-2 and s-4 remain pending_review, s-3 is followup_required, s-1 is reviewed
    assert summary["pending_review_count"] == 2  # noqa: PLR2004
    assert summary["followup_required_count"] == 1


def test_is_low_csat_and_alert_dispatch():
    # 1 star or 2 stars is low CSAT
    assert csat.is_low_csat({"score": 1, "rating": -1})
    assert csat.is_low_csat({"score": 2, "rating": -1})
    assert not csat.is_low_csat({"score": 3, "rating": 0})
    assert not csat.is_low_csat({"score": 4, "rating": 1})
    assert not csat.is_low_csat({"score": 5, "rating": 1})

    # Legacy feedback with score=None
    assert csat.is_low_csat({"score": None, "rating": -1})
    assert not csat.is_low_csat({"score": None, "rating": 1})

    # Test alert dispatch on non-low csat
    high_feedback = {"id": 1, "score": 5, "session_id": "s-high"}
    assert csat.dispatch_low_csat_alert_if_needed(high_feedback) == []

    # Test alert dispatch on low csat
    low_feedback = {
        "id": 42,
        "session_id": "s-alert-1",
        "score": 1,
        "rating": -1,
        "resolution_satisfaction": 1,
        "agent_helpfulness": 1,
        "response_speed": 1,
        "comment": "Unacceptable delay",
        "assigned_agent": "agent_charlie",
        "escalation_tier": "tier_1",
        "review_status": "pending_review",
        "created_at": "2026-10-12 12:00:00",
    }
    with patch("api.webhooks.dispatch_event") as mock_dispatch:
        mock_dispatch.return_value = [{"webhook_id": 10, "success": True}]
        results = csat.dispatch_low_csat_alert_if_needed(low_feedback, timeout=2.5)
        assert results == [{"webhook_id": 10, "success": True}]
        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert call_args[0][0] == "feedback.low_csat"
        data = call_args[0][1]
        assert data["feedback_id"] == 42  # noqa: PLR2004
        assert data["score"] == 1
        assert data["assigned_agent"] == "agent_charlie"
        expected_timeout = 2.5
        assert call_args[1]["timeout"] == expected_timeout
