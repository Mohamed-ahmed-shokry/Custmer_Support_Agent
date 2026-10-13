"""Customer Support Agent Assignment, Workload Balancing, and Tiered Escalation Engine.

Provides automated and manual agent assignment, tiered escalation routing
(tier_1 -> tier_2 -> tier_3), workload analytics aggregation, and audit trail tracking
with webhook notifications.
"""

from __future__ import annotations

import logging
from typing import Any

from api import db_utils, webhooks

logger = logging.getLogger(__name__)


def assign_session(  # noqa: PLR0912, PLR0913, PLR0917
    session_id: str,
    agent_id: str | None = None,
    tier: str | None = None,
    assigned_by: str = "system",
    reason: str = "",
) -> dict[str, Any]:
    """Assign agent or escalation tier to a session, record audit log, and notify webhooks.

    Returns a dict containing the updated session metadata and assignment history record.
    Raises ValueError if session is not found or agent/tier validation fails.
    """
    clean_session_id = (session_id or "").strip()
    if not clean_session_id:
        raise ValueError("session_id must not be blank.")

    meta = db_utils.get_session_metadata(clean_session_id)
    if meta is None:
        raise ValueError(f"Session '{clean_session_id}' not found.")

    prev_agent = meta.get("assigned_agent")
    prev_tier = meta.get("escalation_tier") or db_utils.DEFAULT_AGENT_TIER

    target_agent = prev_agent
    if agent_id is not None:
        clean_agent_id = agent_id.strip().lower()
        if clean_agent_id:
            # Validate agent exists and is active
            agent_record = db_utils.get_support_agent(clean_agent_id)
            if agent_record is None:
                raise ValueError(f"Support agent '{clean_agent_id}' does not exist.")
            target_agent = clean_agent_id
        else:
            target_agent = None

    target_tier = prev_tier
    if tier is not None:
        target_tier = db_utils.normalize_agent_tier(tier)

    # If assigning an agent without specifying tier, adopt agent's tier if agent exists
    if agent_id is not None and target_agent and tier is None:
        agent_record = db_utils.get_support_agent(target_agent)
        if agent_record:
            target_tier = agent_record["tier"]

    # Update session labels
    db_utils.update_session_metadata(
        clean_session_id,
        assigned_agent=target_agent,
        escalation_tier=target_tier,
    )

    # Record assignment history audit entry
    history_record = db_utils.record_session_assignment(
        session_id=clean_session_id,
        assigned_by=assigned_by,
        previous_agent=prev_agent,
        new_agent=target_agent,
        previous_tier=prev_tier,
        new_tier=target_tier,
        reason=reason,
    )

    updated_meta = db_utils.get_session_metadata(clean_session_id) or {}

    # Fire webhooks
    agent_changed = prev_agent != target_agent
    tier_changed = prev_tier != target_tier

    if agent_changed:
        try:
            webhooks.dispatch_event(
                "session.assigned",
                {
                    "session_id": clean_session_id,
                    "previous_agent": prev_agent,
                    "assigned_agent": target_agent,
                    "escalation_tier": target_tier,
                    "assigned_by": assigned_by,
                    "reason": reason,
                },
            )
        except Exception as exc:
            logger.warning("Failed dispatching session.assigned webhook: %s", exc)

    if tier_changed:
        try:
            webhooks.dispatch_event(
                "session.tier_escalated",
                {
                    "session_id": clean_session_id,
                    "previous_tier": prev_tier,
                    "new_tier": target_tier,
                    "assigned_agent": target_agent,
                    "assigned_by": assigned_by,
                    "reason": reason,
                },
            )
        except Exception as exc:
            logger.warning("Failed dispatching session.tier_escalated webhook: %s", exc)

    return {
        "session_id": clean_session_id,
        "metadata": updated_meta,
        "assignment_record": history_record,
        "agent_changed": agent_changed,
        "tier_changed": tier_changed,
    }


def auto_assign_session(
    session_id: str,
    strategy: str = "least_busy",
    target_tier: str | None = None,
    department: str | None = None,
    assigned_by: str = "auto_dispatcher",
) -> dict[str, Any]:
    """Automatically assign an appropriate available agent to a session.

    Selects an active agent in the target tier/department matching workload rules.
    """
    clean_session_id = (session_id or "").strip()
    if not clean_session_id:
        raise ValueError("session_id must not be blank.")

    meta = db_utils.get_session_metadata(clean_session_id)
    if meta is None:
        raise ValueError(f"Session '{clean_session_id}' not found.")

    tier_to_match = (
        db_utils.normalize_agent_tier(target_tier)
        if target_tier
        else (meta.get("escalation_tier") or db_utils.DEFAULT_AGENT_TIER)
    )

    # Query active candidate agents
    candidate_agents = db_utils.list_support_agents(
        tier=tier_to_match,
        department=department,
        active_only=True,
    )

    # Fallback to any active agent in this tier if department had no active agents
    if not candidate_agents and department:
        candidate_agents = db_utils.list_support_agents(
            tier=tier_to_match,
            active_only=True,
        )

    # Fallback to any active agent in system if tier has no agents
    if not candidate_agents:
        candidate_agents = db_utils.list_support_agents(active_only=True)

    if not candidate_agents:
        raise RuntimeError("No active support agents available for assignment.")

    # Calculate current open workloads
    all_sessions = db_utils.get_all_sessions()
    agent_workload: dict[str, int] = {a["id"]: 0 for a in candidate_agents}

    for s in all_sessions:
        if (s.get("status") or "active").lower() in ("active", "escalated"):
            assigned = s.get("assigned_agent")
            if assigned and assigned in agent_workload:
                agent_workload[assigned] += 1

    # Pick candidate with least active workload
    chosen_agent = min(candidate_agents, key=lambda a: (agent_workload.get(a["id"], 0), a["id"]))

    reason_str = (
        f"Auto-assigned using {strategy} strategy (tier={tier_to_match}, "
        f"current_workload={agent_workload.get(chosen_agent['id'], 0)})"
    )

    return assign_session(
        session_id=clean_session_id,
        agent_id=chosen_agent["id"],
        tier=tier_to_match,
        assigned_by=assigned_by,
        reason=reason_str,
    )


def get_agent_workload_analytics() -> dict[str, Any]:
    """Aggregate active, resolved, and unassigned workload distribution across all agents."""
    agents = db_utils.list_support_agents()
    all_sessions = db_utils.get_all_sessions()

    workload_map: dict[str, dict[str, int]] = {
        a["id"]: {"active": 0, "resolved": 0, "total": 0} for a in agents
    }

    unassigned_active = 0
    total_active = 0
    tier_distribution: dict[str, int] = dict.fromkeys(sorted(db_utils.VALID_AGENT_TIERS), 0)

    for s in all_sessions:
        status = (s.get("status") or "active").lower()
        assigned = s.get("assigned_agent")
        tier = s.get("escalation_tier") or db_utils.DEFAULT_AGENT_TIER
        if tier not in tier_distribution:
            tier_distribution[tier] = 0

        is_active = status in ("active", "escalated")
        is_resolved = status in ("resolved", "closed")

        if is_active:
            total_active += 1
            tier_distribution[tier] += 1

        if assigned and assigned in workload_map:
            workload_map[assigned]["total"] += 1
            if is_active:
                workload_map[assigned]["active"] += 1
            elif is_resolved:
                workload_map[assigned]["resolved"] += 1
        elif is_active and not assigned:
            unassigned_active += 1

    agent_items = []
    for a in agents:
        aid = a["id"]
        stats = workload_map.get(aid, {"active": 0, "resolved": 0, "total": 0})
        agent_items.append({
            "agent": {
                "id": a["id"],
                "name": a["name"],
                "email": a["email"],
                "tier": a["tier"],
                "department": a["department"],
                "is_active": bool(a["is_active"]),
                "created_at": a.get("created_at"),
                "updated_at": a.get("updated_at"),
            },
            "active_sessions_count": stats["active"],
            "resolved_sessions_count": stats["resolved"],
            "total_sessions_count": stats["total"],
        })

    return {
        "agents": agent_items,
        "total_active_sessions": total_active,
        "unassigned_active_sessions": unassigned_active,
        "tier_distribution": tier_distribution,
    }
