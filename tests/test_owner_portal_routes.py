"""Integration tests for property owner portal, statements, and CapEx approval FastAPI routes."""

from __future__ import annotations

import pytest
from api import db_utils, owner_portal
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_OWNERS = 2
EXPECTED_NET = 8500.0


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a TestClient against an isolated SQLite database."""
    test_db = tmp_path / "test_owner_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    monkeypatch.setattr(owner_portal.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    owner_portal.init_owner_portal_db()

    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id, unit_id FROM tenants LIMIT 1").fetchone()
        tenant_id = str(row["id"])
        unit_id = str(row["unit_id"])
    finally:
        conn.close()

    db_utils.link_session_tenant("sess_own_1", tenant_id)
    return TestClient(app), unit_id, tenant_id


def test_owner_metrics_and_list_routes(client_with_db):
    client, _, _ = client_with_db
    m_resp = client.get("/owners/metrics")
    assert m_resp.status_code == HTTP_200
    assert m_resp.json()["total_owners"] >= MIN_OWNERS

    list_resp = client.get("/owners")
    assert list_resp.status_code == HTTP_200
    assert list_resp.json()["total"] >= MIN_OWNERS


def test_owner_statements_and_approvals_lifecycle_routes(client_with_db):
    client, unit_id, _ = client_with_db

    # 1. Create, get, patch owner
    c_resp = client.post(
        "/owners",
        json={
            "full_name": "Victor Sterling",
            "email": "victor@sterling.example",
            "entity_name": "Sterling Asset Trust",
            "management_fee_pct": 10.0,
            "reserve_balance": 2000.0,
        },
    )
    assert c_resp.status_code == HTTP_201
    oid = c_resp.json()["id"]

    assert client.get(f"/owners/{oid}").status_code == HTTP_200
    p_resp = client.patch(f"/owners/{oid}", json={"notes": "VIP owner"})
    assert p_resp.status_code == HTTP_200
    assert p_resp.json()["notes"] == "VIP owner"

    # 2. Generate, list, fetch, and disburse statement
    s_resp = client.post(
        f"/owners/{oid}/statements",
        json={
            "period_month": "2099-08",
            "gross_rent_collected": 10000.0,
            "operating_expenses": 500.0,
            "reserve_contribution": 0.0,
        },
    )
    assert s_resp.status_code == HTTP_201
    sid = s_resp.json()["id"]
    assert s_resp.json()["net_disbursement"] == EXPECTED_NET
    assert "Cash Flow Summary" in s_resp.json()["statement_markdown"]

    assert client.get("/owners/statements", params={"owner_id": oid}).json()["total"] == 1
    assert client.get(f"/owners/statements/{sid}").status_code == HTTP_200

    d_resp = client.post(f"/owners/statements/{sid}/disburse", json={"notes": "Paid ACH"})
    assert d_resp.status_code == HTTP_200
    assert d_resp.json()["status"] == "disbursed"

    # 3. Create, list, decide CapEx approval
    a_resp = client.post(
        f"/owners/{oid}/approvals",
        json={
            "title": "Elevator Controller Upgrade",
            "estimated_cost": 6500.0,
            "unit_id": unit_id,
            "category": "capex",
            "vendor_name": "Metro Lift Corp",
        },
    )
    assert a_resp.status_code == HTTP_201
    aid = a_resp.json()["id"]

    assert client.get("/owners/approvals", params={"owner_id": oid}).json()["total"] == 1
    dec = client.post(
        f"/owners/approvals/{aid}/decision",
        json={"decision": "approved", "owner_decision_notes": "Approved for Q3"},
    )
    assert dec.status_code == HTTP_200
    assert dec.json()["status"] == "approved"

    # 4. Owner portfolio summary
    sum_resp = client.get(f"/owners/{oid}/summary")
    assert sum_resp.status_code == HTTP_200
    assert sum_resp.json()["total_disbursed"] == EXPECTED_NET


def test_unit_summary_session_escalation_and_errors(client_with_db):
    client, unit_id, _ = client_with_db

    u_resp = client.get(f"/units/{unit_id}/owner-approvals/summary")
    assert u_resp.status_code == HTTP_200
    assert u_resp.json()["unit_id"] == unit_id

    sess_resp = client.post(
        "/sessions/sess_own_1/owners/request-approval",
        json={
            "owner_id": "own_seed_01",
            "title": "Emergency Water Heater Replacement",
            "estimated_cost": 1850.0,
            "category": "major_repair",
        },
    )
    assert sess_resp.status_code == HTTP_201

    bad_sess = client.post(
        "/sessions/unlinked/owners/request-approval",
        json={"owner_id": "own_seed_01", "title": "Test Repair", "estimated_cost": 500.0},
    )
    assert bad_sess.status_code == HTTP_400

    assert client.get("/owners/own_missing").status_code == HTTP_404
    assert client.get("/owners/statements/stm_missing").status_code == HTTP_404
