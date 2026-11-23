"""Integration tests for prospective leasing CRM, tours, and applications FastAPI routes."""

from __future__ import annotations

import pytest
from api import db_utils, leasing_crm
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_PROSPECTS = 2
EXPECTED_INCOME = 8400.0
EXPECTED_CREDIT = 740


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a TestClient against an isolated SQLite database."""
    test_db = tmp_path / "test_leasing_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    monkeypatch.setattr(leasing_crm.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    leasing_crm.init_leasing_crm_db()

    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id, unit_id FROM tenants LIMIT 1").fetchone()
        tenant_id = str(row["id"])
        unit_id = str(row["unit_id"])
    finally:
        conn.close()

    db_utils.link_session_tenant("sess_lease_1", tenant_id)
    return TestClient(app), unit_id, tenant_id


def test_leasing_metrics_and_list_routes(client_with_db):
    client, _, _ = client_with_db
    m_resp = client.get("/leasing/metrics")
    assert m_resp.status_code == HTTP_200
    assert m_resp.json()["total_prospects"] >= MIN_PROSPECTS

    p_resp = client.get("/leasing/prospects")
    assert p_resp.status_code == HTTP_200
    assert p_resp.json()["total"] >= MIN_PROSPECTS


def test_leasing_full_funnel_routes(client_with_db):
    client, unit_id, _ = client_with_db

    # 1. Create, get, patch prospect
    c_resp = client.post(
        "/leasing/prospects",
        json={
            "full_name": "Priya Nair",
            "email": "priya.nair@example.com",
            "lead_source": "zillow",
            "desired_unit_id": unit_id,
            "max_budget": 3000.0,
        },
    )
    assert c_resp.status_code == HTTP_201
    pid = c_resp.json()["id"]

    assert client.get(f"/leasing/prospects/{pid}").status_code == HTTP_200
    patch_resp = client.patch(f"/leasing/prospects/{pid}", json={"notes": "Pre-qualified"})
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["notes"] == "Pre-qualified"

    # 2. Schedule, list, complete, and cancel tours
    t_resp = client.post(
        "/leasing/tours",
        json={
            "prospect_id": pid,
            "unit_id": unit_id,
            "scheduled_date": "2099-09-01",
            "tour_type": "in_person",
        },
    )
    assert t_resp.status_code == HTTP_201
    tid = t_resp.json()["id"]

    assert client.get("/leasing/tours", params={"prospect_id": pid}).json()["total"] == 1
    comp = client.post(
        f"/leasing/tours/{tid}/complete",
        json={"feedback_rating": 5, "feedback_notes": "Ready to apply"},
    )
    assert comp.status_code == HTTP_200
    assert comp.json()["status"] == "completed"

    t2 = client.post(
        "/leasing/tours",
        json={"prospect_id": pid, "unit_id": unit_id, "scheduled_date": "2099-09-05"},
    ).json()
    canc = client.post(f"/leasing/tours/{t2['id']}/cancel")
    assert canc.status_code == HTTP_200
    assert canc.json()["status"] == "cancelled"

    # 3. Submit, screen, and approve rental application
    a_resp = client.post(
        "/leasing/applications",
        json={
            "prospect_id": pid,
            "unit_id": unit_id,
            "monthly_income": EXPECTED_INCOME,
            "target_rent": 2200.0,
        },
    )
    assert a_resp.status_code == HTTP_201
    aid = a_resp.json()["id"]

    assert client.get(f"/leasing/applications/{aid}").status_code == HTTP_200
    assert client.get("/leasing/applications", params={"unit_id": unit_id}).status_code == HTTP_200

    scr = client.post(
        f"/leasing/applications/{aid}/screen",
        json={
            "credit_score": EXPECTED_CREDIT,
            "background_status": "passed",
            "eviction_history_clear": True,
        },
    )
    assert scr.status_code == HTTP_200
    assert scr.json()["recommended_decision"] == "approved"

    dec = client.post(
        f"/leasing/applications/{aid}/decision",
        json={"decision": "approved", "decision_notes": "Approved for immediate move-in"},
    )
    assert dec.status_code == HTTP_200
    assert dec.json()["status"] == "approved"


def test_unit_summary_session_actions_and_errors(client_with_db):
    client, unit_id, _ = client_with_db

    summary = client.get(f"/units/{unit_id}/leasing/summary")
    assert summary.status_code == HTTP_200
    assert summary.json()["unit_id"] == unit_id

    s_tour = client.post(
        "/sessions/sess_lease_1/leasing/schedule-tour",
        json={"prospect_id": "prs_seed_01", "scheduled_date": "2099-10-01"},
    )
    assert s_tour.status_code == HTTP_201

    s_app = client.post(
        "/sessions/sess_lease_1/leasing/submit-application",
        json={"prospect_id": "prs_seed_01", "monthly_income": 7500.0},
    )
    assert s_app.status_code == HTTP_201

    bad_sess = client.post(
        "/sessions/unlinked/leasing/schedule-tour",
        json={"prospect_id": "prs_seed_01", "scheduled_date": "2099-10-01"},
    )
    assert bad_sess.status_code == HTTP_400

    assert client.get("/leasing/prospects/prs_missing").status_code == HTTP_404
    assert client.get("/leasing/applications/app_missing").status_code == HTTP_404
