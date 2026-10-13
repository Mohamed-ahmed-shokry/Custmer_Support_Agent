"""Core CSAT feedback analytics, agent scorecards, and alert engine."""

from typing import Any

from api import db_utils, webhooks

LOW_CSAT_THRESHOLD = 2
HIGH_CSAT_THRESHOLD = 4


def _extract_effective_score(item: dict[str, Any]) -> int:
    score = item.get("score")
    rating = item.get("rating")
    if score is not None:
        return int(score)
    if rating == 1:
        return 5
    if rating == -1:
        return 1
    return 3


def calculate_csat_summary(limit: int = 1000) -> dict[str, Any]:
    """Aggregate overall CSAT score distribution, average criteria scores, and trends.

    Returns structured summary including:
      - total_responses: int
      - avg_csat_score: float (1.0 to 5.0 scale)
      - avg_resolution_score: float | None
      - avg_helpfulness_score: float | None
      - avg_speed_score: float | None
      - satisfaction_rate: float (percentage of responses with score >= 4 or rating = 1)
      - dissatisfaction_rate: float (percentage of responses with score <= 2 or rating = -1)
      - star_distribution: dict[int, int] (counts for 1 to 5 stars)
      - pending_review_count: int
      - followup_required_count: int
    """
    items, total = db_utils.list_feedback(limit=limit, offset=0)
    if not items:
        return {
            "total_responses": 0,
            "avg_csat_score": 0.0,
            "avg_resolution_score": None,
            "avg_helpfulness_score": None,
            "avg_speed_score": None,
            "satisfaction_rate": 0.0,
            "dissatisfaction_rate": 0.0,
            "star_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "pending_review_count": 0,
            "followup_required_count": 0,
        }

    star_distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    csat_scores: list[int] = []
    res_scores: list[int] = []
    help_scores: list[int] = []
    speed_scores: list[int] = []
    positive_count = 0
    negative_count = 0
    pending_review = 0
    followup_required = 0

    for item in items:
        effective_score = _extract_effective_score(item)
        if effective_score in star_distribution:
            star_distribution[effective_score] += 1
        csat_scores.append(effective_score)

        if effective_score >= HIGH_CSAT_THRESHOLD:
            positive_count += 1
        elif effective_score <= LOW_CSAT_THRESHOLD:
            negative_count += 1

        if item.get("resolution_satisfaction") is not None:
            res_scores.append(int(item["resolution_satisfaction"]))
        if item.get("agent_helpfulness") is not None:
            help_scores.append(int(item["agent_helpfulness"]))
        if item.get("response_speed") is not None:
            speed_scores.append(int(item["response_speed"]))

        status = item.get("review_status")
        if status == "pending_review":
            pending_review += 1
        elif status == "followup_required":
            followup_required += 1

    tot = len(csat_scores)
    avg_csat = round(sum(csat_scores) / tot, 2) if tot > 0 else 0.0
    avg_res = round(sum(res_scores) / len(res_scores), 2) if res_scores else None
    avg_help = round(sum(help_scores) / len(help_scores), 2) if help_scores else None
    avg_speed = round(sum(speed_scores) / len(speed_scores), 2) if speed_scores else None
    sat_rate = round(positive_count / tot * 100, 1) if tot > 0 else 0.0
    dissat_rate = round(negative_count / tot * 100, 1) if tot > 0 else 0.0

    return {
        "total_responses": total,
        "avg_csat_score": avg_csat,
        "avg_resolution_score": avg_res,
        "avg_helpfulness_score": avg_help,
        "avg_speed_score": avg_speed,
        "satisfaction_rate": sat_rate,
        "dissatisfaction_rate": dissat_rate,
        "star_distribution": star_distribution,
        "pending_review_count": pending_review,
        "followup_required_count": followup_required,
    }


def is_low_csat(feedback: dict[str, Any]) -> bool:
    """Determine whether feedback qualifies as low CSAT requiring alerts/reviews."""
    score = feedback.get("score")
    if score is not None:
        return int(score) <= LOW_CSAT_THRESHOLD
    rating = feedback.get("rating")
    return rating == -1


def dispatch_low_csat_alert_if_needed(
    feedback: dict[str, Any],
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    """Trigger 'feedback.low_csat' webhook dispatch when feedback meets low CSAT criteria."""
    if not is_low_csat(feedback):
        return []

    event_data = {
        "feedback_id": feedback.get("id"),
        "session_id": feedback.get("session_id"),
        "score": feedback.get("score"),
        "rating": feedback.get("rating"),
        "resolution_satisfaction": feedback.get("resolution_satisfaction"),
        "agent_helpfulness": feedback.get("agent_helpfulness"),
        "response_speed": feedback.get("response_speed"),
        "comment": feedback.get("comment"),
        "assigned_agent": feedback.get("assigned_agent"),
        "escalation_tier": feedback.get("escalation_tier"),
        "review_status": feedback.get("review_status"),
        "created_at": feedback.get("created_at"),
    }
    return webhooks.dispatch_event("feedback.low_csat", event_data, timeout=timeout)
