"""Unit tests for agent assignment, tiered escalation, and workload balancing engine."""

from api import assignment, db_utils


def setup_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_assignment.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_document_store()
    db_utils.create_session_labels()
    db_utils.migrate_session_labels()
    db_utils.create_feedback()
    db_utils.create_webhooks()
    db_utils.create_support_macros()
    db_utils.create_sla_policies()
    db_utils.create_support_agents()
    db_utils.create_session_assignment_history()
    return db_path


def test_assign_session_manual_and_history(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)

    # Insert a test session
    session_id = "sess-assign-1"
    db_utils.insert_application_logs(session_id, "Inquiry about parking", "Response", "gpt-4o")
    db_utils.update_session_metadata(session_id, label="Parking Question", priority="medium")

    # Verify initial state: unassigned, tier_1
    meta = db_utils.get_session_metadata(session_id)
    assert meta is not None
    assert meta.get("assigned_agent") is None
    assert meta.get("escalation_tier") == "tier_1"

    # Assign to agent_sarah (tier 1 general_leasing)
    result = assignment.assign_session(
        session_id=session_id,
        agent_id="agent_sarah",
        tier="tier_1",
        assigned_by="dispatcher_test",
        reason="Assigned for initial triage",
    )
    assert result["session_id"] == session_id
    assert result["agent_changed"] is True
    assert result["metadata"]["assigned_agent"] == "agent_sarah"
    assert result["metadata"]["escalation_tier"] == "tier_1"

    # Escalate to Tier 2 (agent_marcus)
    res_esc = assignment.assign_session(
        session_id=session_id,
        agent_id="agent_marcus",
        tier="tier_2",
        assigned_by="agent_sarah",
        reason="Requires specialized billing dispute inspection",
    )
    assert res_esc["agent_changed"] is True
    assert res_esc["tier_changed"] is True
    assert res_esc["metadata"]["assigned_agent"] == "agent_marcus"
    assert res_esc["metadata"]["escalation_tier"] == "tier_2"

    # Check assignment audit history
    history = db_utils.get_session_assignment_history(session_id)
    expected_entries = 2
    assert len(history) == expected_entries
    assert history[0]["new_agent"] == "agent_marcus"
    assert history[0]["previous_agent"] == "agent_sarah"
    assert history[0]["previous_tier"] == "tier_1"
    assert history[0]["new_tier"] == "tier_2"
    assert history[1]["new_agent"] == "agent_sarah"
    assert history[1]["previous_agent"] is None


def test_assign_session_webhook_dispatch(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)

    # Register webhook for assignment events
    wh = db_utils.create_webhook(url="https://httpbin.org/post", events="*", secret="secret")
    assert wh["id"] > 0

    session_id = "sess-wh-assign"
    db_utils.insert_application_logs(session_id, "Broken AC", "", "gpt-4o")
    db_utils.update_session_metadata(session_id, priority="urgent")

    dispatched_events: list[str] = []

    def fake_post(url, data, headers, timeout):
        class FakeResponse:
            status_code = 200
            ok = True
            text = "ok"

        ev = headers.get("X-Webhook-Event")
        if ev:
            dispatched_events.append(ev)
        return FakeResponse()

    monkeypatch.setattr("requests.post", fake_post)

    # Assign agent and escalate tier simultaneously
    assignment.assign_session(
        session_id=session_id,
        agent_id="agent_marcus",
        tier="tier_2",
        assigned_by="system",
        reason="Auto escalation",
    )

    assert "session.assigned" in dispatched_events
    assert "session.tier_escalated" in dispatched_events


def test_auto_assign_session_least_busy(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)

    # Pre-seed 3 active sessions for agent_sarah (tier 1), leaving agent_david (tier 1) free
    for i in range(3):
        sid = f"sess-busy-{i}"
        db_utils.insert_application_logs(sid, "Query", "Answer", "gpt-4o")
        db_utils.update_session_metadata(sid, assigned_agent="agent_sarah", status="active")

    # Create new session to auto-assign
    new_sid = "sess-to-auto-assign"
    db_utils.insert_application_logs(new_sid, "New question", "", "gpt-4o")
    db_utils.update_session_metadata(new_sid, status="active", escalation_tier="tier_1")

    # Auto assign in tier_1
    res = assignment.auto_assign_session(new_sid, strategy="least_busy", target_tier="tier_1")
    assert res["session_id"] == new_sid
    # agent_david has 0 active sessions, whereas agent_sarah has 3 => agent_david must be chosen
    assert res["metadata"]["assigned_agent"] == "agent_david"
    assert "least_busy" in res["assignment_record"]["reason"]


def test_get_agent_workload_analytics(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)

    # Create active sessions
    s1 = "sess-w1"
    db_utils.insert_application_logs(s1, "Q1", "", "gpt-4o")
    db_utils.update_session_metadata(
        s1, assigned_agent="agent_sarah", status="active", escalation_tier="tier_1"
    )

    s2 = "sess-w2"
    db_utils.insert_application_logs(s2, "Q2", "", "gpt-4o")
    db_utils.update_session_metadata(
        s2, assigned_agent="agent_sarah", status="active", escalation_tier="tier_1"
    )

    s3 = "sess-w3"
    db_utils.insert_application_logs(s3, "Q3", "A3", "gpt-4o")
    db_utils.update_session_metadata(
        s3, assigned_agent="agent_sarah", status="resolved", escalation_tier="tier_1"
    )

    # Unassigned active session
    s_unassigned = "sess-unassigned"
    db_utils.insert_application_logs(s_unassigned, "Q4", "", "gpt-4o")
    db_utils.update_session_metadata(
        s_unassigned, assigned_agent=None, status="active", escalation_tier="tier_2"
    )

    analytics = assignment.get_agent_workload_analytics()
    expected_total_active = 3  # s1, s2, s_unassigned
    expected_tier_1_active = 2
    expected_tier_2_active = 1
    assert analytics["total_active_sessions"] == expected_total_active
    assert analytics["unassigned_active_sessions"] == 1
    assert analytics["tier_distribution"]["tier_1"] == expected_tier_1_active
    assert analytics["tier_distribution"]["tier_2"] == expected_tier_2_active

    sarah_item = next(
        item for item in analytics["agents"] if item["agent"]["id"] == "agent_sarah"
    )
    expected_sarah_active = 2
    expected_sarah_total = 3
    assert sarah_item["active_sessions_count"] == expected_sarah_active
    assert sarah_item["resolved_sessions_count"] == 1
    assert sarah_item["total_sessions_count"] == expected_sarah_total
