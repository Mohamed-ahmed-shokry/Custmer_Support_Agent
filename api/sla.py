"""Service Level Agreement (SLA) policy calculation, priority triage, and alerting engine.

Provides automated deadline calculations, breach detection, webhook dispatching,
and compliance analytics for customer support operations.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from api import db_utils, webhooks

logger = logging.getLogger(__name__)

DEFAULT_APPROACHING_THRESHOLD_MINUTES = 30


def parse_timestamp(value: Any) -> datetime | None:
    """Parse SQLite or ISO timestamp strings into UTC-aware datetime."""
    if not value or not isinstance(value, str):
        return None
    val = value.strip()
    if not val:
        return None

    # Try ISO formats
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        pass

    # Try SQLite CURRENT_TIMESTAMP format '%Y-%m-%d %H:%M:%S'
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(val, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue

    return None


def infer_session_category(
    tags: str | list[str] | None,
    query: str | None = None,
) -> str:
    """Infer support category from tags or query text."""
    haystack_parts = []
    if isinstance(tags, list):
        haystack_parts.extend(tags)
    elif isinstance(tags, str):
        haystack_parts.append(tags)

    if query:
        haystack_parts.append(query)

    text = " ".join(haystack_parts).lower()

    maint_keys = ("maintenance", "leak", "repair", "heat", "pipe", "water", "ac", "lockout")
    if any(k in text for k in maint_keys):
        return "maintenance"
    if any(k in text for k in ("lease", "renew", "tenant", "agreement", "move-out")):
        return "lease"
    if any(k in text for k in ("rent", "billing", "payment", "invoice", "fee")):
        return "billing"

    return "general"


def calculate_session_sla_status(  # noqa: PLR0912, PLR0915
    session_id: str,
    current_time: datetime | None = None,
    approaching_threshold_minutes: int = DEFAULT_APPROACHING_THRESHOLD_MINUTES,
) -> dict | None:
    """Compute detailed SLA status, deadlines, and breach conditions for a session."""
    meta = db_utils.get_session_metadata(session_id)
    if meta is None:
        return None

    timestamps = db_utils.get_session_timestamps(session_id)
    priority = meta.get("priority") or db_utils.DEFAULT_SESSION_PRIORITY
    tags = meta.get("tags") or ""
    category = infer_session_category(tags)

    policy = db_utils.get_matching_sla_policy(priority, category)
    if policy is None:
        resp_target = 60
        resol_target = 480
        pol_id = None
        pol_name = "Default Fallback SLA"
    else:
        resp_target = int(policy["response_time_minutes"])
        resol_target = int(policy["resolution_time_minutes"])
        pol_id = policy["id"]
        pol_name = policy["name"]

    now = current_time or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    session_start_raw = timestamps.get("session_start")
    start_dt = parse_timestamp(session_start_raw) or now

    first_resp_raw = timestamps.get("first_response_at")
    first_resp_dt = parse_timestamp(first_resp_raw)

    response_due_dt = start_dt + timedelta(minutes=resp_target)
    resolution_due_dt = start_dt + timedelta(minutes=resol_target)

    # 1. First Response SLA
    response_met = False
    response_breached = False
    if first_resp_dt is not None:
        if first_resp_dt <= response_due_dt:
            response_met = True
        else:
            response_breached = True
    elif now > response_due_dt:
        response_breached = True

    # 2. Resolution SLA
    session_status = (meta.get("status") or "active").lower()
    resolution_met = False
    resolution_breached = False
    if session_status in ("resolved", "closed"):
        resolution_met = not resolution_breached
    elif now > resolution_due_dt:
        resolution_breached = True

    # 3. Approaching Breach calculation
    mins_to_resp = max(0.0, (response_due_dt - now).total_seconds() / 60.0)
    mins_to_resol = max(0.0, (resolution_due_dt - now).total_seconds() / 60.0)

    response_approaching = (
        not response_met
        and not response_breached
        and mins_to_resp <= approaching_threshold_minutes
    )
    resolution_approaching = (
        not resolution_met
        and not resolution_breached
        and mins_to_resol <= approaching_threshold_minutes
    )

    # 4. Overall Breach Status
    if response_breached or resolution_breached:
        breach_status = "breached"
    elif response_approaching or resolution_approaching:
        breach_status = "approaching_breach"
    elif response_met and resolution_met:
        breach_status = "met"
    else:
        breach_status = "healthy"

    return {
        "session_id": session_id,
        "priority": priority,
        "category": category,
        "status": session_status,
        "policy_id": pol_id,
        "policy_name": pol_name,
        "response_target_minutes": resp_target,
        "resolution_target_minutes": resol_target,
        "session_started_at": start_dt.isoformat(),
        "first_response_at": first_resp_dt.isoformat() if first_resp_dt else None,
        "response_due_at": response_due_dt.isoformat(),
        "resolution_due_at": resolution_due_dt.isoformat(),
        "response_met": response_met,
        "resolution_met": resolution_met,
        "response_breached": response_breached,
        "resolution_breached": resolution_breached,
        "response_approaching": response_approaching,
        "resolution_approaching": resolution_approaching,
        "breach_status": breach_status,
        "minutes_to_response_deadline": round(mins_to_resp, 1) if not response_met else 0.0,
        "minutes_to_resolution_deadline": round(mins_to_resol, 1) if not resolution_met else 0.0,
    }


def evaluate_and_dispatch_sla_alerts(
    approaching_threshold_minutes: int = DEFAULT_APPROACHING_THRESHOLD_MINUTES,
    current_time: datetime | None = None,
) -> dict:
    """Evaluate active sessions for SLA deadlines and dispatch webhook alerts."""
    sessions = db_utils.get_all_sessions()
    now = current_time or datetime.now(UTC)
    alerts = []
    checked_count = 0

    for s in sessions:
        status_val = (s.get("status") or "active").lower()
        if status_val not in ("active", "escalated"):
            continue

        checked_count += 1
        s_id = s["session_id"]
        sla_info = calculate_session_sla_status(
            s_id,
            current_time=now,
            approaching_threshold_minutes=approaching_threshold_minutes,
        )
        if not sla_info:
            continue

        breach_status = sla_info["breach_status"]
        if breach_status in ("breached", "approaching_breach"):
            event_name = (
                "sla.breached"
                if breach_status == "breached"
                else "sla.approaching_breach"
            )
            is_resp = (
                sla_info["response_breached"] or sla_info["response_approaching"]
            )
            breach_type = "response" if is_resp else "resolution"
            due_at = (
                sla_info["response_due_at"]
                if breach_type == "response"
                else sla_info["resolution_due_at"]
            )
            rem_mins = (
                sla_info["minutes_to_response_deadline"]
                if breach_type == "response"
                else sla_info["minutes_to_resolution_deadline"]
            )

            payload_data = {
                "session_id": s_id,
                "priority": sla_info["priority"],
                "category": sla_info["category"],
                "breach_type": breach_type,
                "breach_status": breach_status,
                "response_due_at": sla_info["response_due_at"],
                "resolution_due_at": sla_info["resolution_due_at"],
                "minutes_remaining": rem_mins,
            }

            try:
                dispatch_results = webhooks.dispatch_event(event_name, payload_data)
                dispatched_count = len(dispatch_results)
            except Exception as exc:
                logger.warning("Error dispatching SLA webhook for session %s: %s", s_id, exc)
                dispatched_count = 0

            alerts.append({
                "session_id": s_id,
                "priority": sla_info["priority"],
                "category": sla_info["category"],
                "event": event_name,
                "breach_type": breach_type,
                "deadline_due_at": due_at,
                "minutes_remaining": rem_mins,
                "webhooks_dispatched": dispatched_count,
            })

    return {
        "total_sessions_checked": checked_count,
        "alerts_triggered": len(alerts),
        "alerts": alerts,
    }


def get_sla_compliance_analytics(current_time: datetime | None = None) -> dict:
    """Aggregate operational SLA compliance rate and priority triage metrics."""
    sessions = db_utils.get_all_sessions()
    now = current_time or datetime.now(UTC)

    total_tracked = len(sessions)
    if total_tracked == 0:
        return {
            "total_tracked_sessions": 0,
            "compliance_rate": 100.0,
            "met_sessions": 0,
            "healthy_sessions": 0,
            "approaching_breach_sessions": 0,
            "breached_sessions": 0,
            "avg_first_response_minutes": 0.0,
            "priority_breakdown": {
                p: {"total": 0, "breached": 0, "met": 0, "active": 0}
                for p in sorted(db_utils.VALID_SESSION_PRIORITIES)
            },
        }

    met_count = 0
    healthy_count = 0
    approaching_count = 0
    breached_count = 0
    first_resp_times: list[float] = []

    priority_breakdown: dict[str, dict[str, int]] = {
        p: {"total": 0, "breached": 0, "met": 0, "active": 0}
        for p in sorted(db_utils.VALID_SESSION_PRIORITIES)
    }

    for s in sessions:
        s_id = s["session_id"]
        sla_info = calculate_session_sla_status(s_id, current_time=now)
        if not sla_info:
            continue

        prio = sla_info["priority"]
        if prio not in priority_breakdown:
            prio = db_utils.DEFAULT_SESSION_PRIORITY

        priority_breakdown[prio]["total"] += 1

        b_status = sla_info["breach_status"]
        if b_status == "breached":
            breached_count += 1
            priority_breakdown[prio]["breached"] += 1
        elif b_status == "approaching_breach":
            approaching_count += 1
        elif b_status == "met":
            met_count += 1
            priority_breakdown[prio]["met"] += 1
        else:
            healthy_count += 1

        if sla_info["status"] in ("active", "escalated"):
            priority_breakdown[prio]["active"] += 1

        if sla_info["first_response_at"] and sla_info["session_started_at"]:
            st_dt = parse_timestamp(sla_info["session_started_at"])
            fr_dt = parse_timestamp(sla_info["first_response_at"])
            if st_dt and fr_dt and fr_dt >= st_dt:
                diff_mins = (fr_dt - st_dt).total_seconds() / 60.0
                first_resp_times.append(diff_mins)

    compliance_rate = round(((total_tracked - breached_count) / total_tracked) * 100.0, 1)
    avg_resp = (
        round(sum(first_resp_times) / len(first_resp_times), 1)
        if first_resp_times
        else 0.0
    )

    return {
        "total_tracked_sessions": total_tracked,
        "compliance_rate": compliance_rate,
        "met_sessions": met_count,
        "healthy_sessions": healthy_count,
        "approaching_breach_sessions": approaching_count,
        "breached_sessions": breached_count,
        "avg_first_response_minutes": avg_resp,
        "priority_breakdown": priority_breakdown,
    }
