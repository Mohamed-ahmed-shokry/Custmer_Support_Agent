"""Unit tests for the SLA policy calculation, triage, and alerting engine."""

from datetime import UTC, datetime, timedelta

from api import db_utils, sla


def setup_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_sla.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_document_store()
    db_utils.create_session_labels()
    db_utils.migrate_session_labels()
    db_utils.create_feedback()
    db_utils.create_webhooks()
    db_utils.create_support_macros()
    db_utils.create_sla_policies()
    return db_path


def test_parse_timestamp():
    assert sla.parse_timestamp(None) is None
    assert sla.parse_timestamp("") is None
    assert sla.parse_timestamp("invalid-date") is None

    iso_z = "2026-10-08T12:00:00Z"
    dt1 = sla.parse_timestamp(iso_z)
    assert dt1 is not None
    assert dt1.tzinfo is not None

    sqlite_fmt = "2026-10-08 12:00:00"
    dt2 = sla.parse_timestamp(sqlite_fmt)
    assert dt2 is not None
    expected_hour = 12
    assert dt2.hour == expected_hour


def test_infer_session_category():
    assert sla.infer_session_category(None) == "general"
    assert sla.infer_session_category("urgent, random") == "general"
    assert sla.infer_session_category("maintenance, leak") == "maintenance"
    assert sla.infer_session_category([], query="My pipe is leaking") == "maintenance"
    assert sla.infer_session_category("lease, renewal") == "lease"
    assert sla.infer_session_category(["billing", "rent"]) == "billing"
    assert sla.infer_session_category("", query="Rent payment question") == "billing"


def test_calculate_session_sla_status_unknown_session(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)
    assert sla.calculate_session_sla_status("unknown-session-id") is None


def test_calculate_session_sla_status_healthy_and_policy_match(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)
    s_id = "sess-urgent-maint"
    db_utils.insert_application_logs(s_id, "Major water leak in Unit 3A", "", "gpt-4o")
    db_utils.update_session_metadata(s_id, priority="urgent", tags="maintenance, emergency")

    status = sla.calculate_session_sla_status(s_id)
    assert status is not None
    assert status["session_id"] == s_id
    assert status["priority"] == "urgent"
    assert status["category"] == "maintenance"
    expected_resp_target = 15
    expected_resol_target = 120
    assert status["response_target_minutes"] == expected_resp_target
    assert status["resolution_target_minutes"] == expected_resol_target
    assert status["policy_name"] == "Urgent Maintenance SLA"
    assert status["response_met"] is False
    assert status["response_breached"] is False
    assert status["breach_status"] in ("healthy", "approaching_breach")


def test_calculate_session_sla_status_response_met_and_breached(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)
    s_id = "sess-timing"
    base_time = datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC)

    # 1. Session created at base_time, response given at +5 min (within 15 min SLA)
    db_utils.insert_application_logs(s_id, "Need fix", "Tech dispatched", "gpt-4o")
    db_utils.update_session_metadata(s_id, priority="urgent", tags="maintenance")

    # Override start and first response timestamps for deterministic check
    first_resp_time = base_time + timedelta(minutes=5)
    with db_utils.closing(db_utils.get_db_connection()) as conn:
        conn.execute(
            "UPDATE application_logs SET created_at = ? WHERE session_id = ?",
            (base_time.strftime("%Y-%m-%d %H:%M:%S"), s_id),
        )
        conn.commit()

    # Current time is 10 minutes in -> response should be met
    status = sla.calculate_session_sla_status(s_id, current_time=first_resp_time)
    assert status is not None
    assert status["response_met"] is True
    assert status["response_breached"] is False

    # 2. Simulate session where no response given and time is now +30m (breached deadline)
    s_id_breached = "sess-breached"
    db_utils.insert_application_logs(s_id_breached, "Urgent leak", "", "gpt-4o")
    db_utils.update_session_metadata(s_id_breached, priority="urgent", tags="maintenance")
    with db_utils.closing(db_utils.get_db_connection()) as conn:
        conn.execute(
            "UPDATE application_logs SET created_at = ? WHERE session_id = ?",
            (base_time.strftime("%Y-%m-%d %H:%M:%S"), s_id_breached),
        )
        conn.commit()

    simulated_now = base_time + timedelta(minutes=30)
    status_breached = sla.calculate_session_sla_status(s_id_breached, current_time=simulated_now)
    assert status_breached is not None
    assert status_breached["response_breached"] is True
    assert status_breached["breach_status"] == "breached"


def test_calculate_session_sla_status_resolution_met(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)
    s_id = "sess-resolved"
    db_utils.insert_application_logs(s_id, "Question", "Answer", "gpt-4o")
    db_utils.update_session_metadata(
        s_id, priority="medium", status="resolved", resolution_notes="Completed"
    )

    status = sla.calculate_session_sla_status(s_id)
    assert status is not None
    assert status["resolution_met"] is True
    assert status["response_met"] is True
    assert status["breach_status"] == "met"


def test_evaluate_and_dispatch_sla_alerts(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)
    base_time = datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC)

    # Register webhook for SLA events
    wh = db_utils.create_webhook(
        url="https://httpbin.org/post",
        events="*",
        secret="test-secret",
    )
    assert wh["id"] > 0

    # Create session that breaches response SLA
    s_id = "sess-alert-test"
    db_utils.insert_application_logs(s_id, "Leak in living room", "", "gpt-4o")
    db_utils.update_session_metadata(s_id, priority="urgent", tags="maintenance")

    with db_utils.closing(db_utils.get_db_connection()) as conn:
        conn.execute(
            "UPDATE application_logs SET created_at = ? WHERE session_id = ?",
            (base_time.strftime("%Y-%m-%d %H:%M:%S"), s_id),
        )
        conn.commit()

    # Mock requests.post to avoid real HTTP requests in unit test
    called_events = []

    def fake_post(url, data, headers, timeout):
        class FakeResponse:
            status_code = 200
            ok = True
            text = "ok"

        called_events.append(headers.get("X-Webhook-Event"))
        return FakeResponse()

    monkeypatch.setattr("requests.post", fake_post)

    simulated_now = base_time + timedelta(minutes=45)
    eval_result = sla.evaluate_and_dispatch_sla_alerts(
        current_time=simulated_now,
        approaching_threshold_minutes=30,
    )

    assert eval_result["total_sessions_checked"] >= 1
    assert eval_result["alerts_triggered"] >= 1
    assert any(a["session_id"] == s_id for a in eval_result["alerts"])
    assert "sla.breached" in called_events


def test_get_sla_compliance_analytics(monkeypatch, tmp_path):
    setup_temp_db(monkeypatch, tmp_path)

    # Empty store
    analytics_empty = sla.get_sla_compliance_analytics()
    assert analytics_empty["total_tracked_sessions"] == 0
    expected_full_comp = 100.0
    assert analytics_empty["compliance_rate"] == expected_full_comp

    # Add resolved session (met)
    s1 = "s-met"
    db_utils.insert_application_logs(s1, "Q1", "A1", "gpt-4o")
    db_utils.update_session_metadata(s1, priority="urgent", status="resolved")

    # Add active session
    s2 = "s-active"
    db_utils.insert_application_logs(s2, "Q2", "A2", "gpt-4o")
    db_utils.update_session_metadata(s2, priority="high", status="active")

    analytics = sla.get_sla_compliance_analytics()
    expected_tracked = 2
    assert analytics["total_tracked_sessions"] == expected_tracked
    min_compliance = 50.0
    assert analytics["compliance_rate"] >= min_compliance
    assert "urgent" in analytics["priority_breakdown"]
    assert "high" in analytics["priority_breakdown"]
