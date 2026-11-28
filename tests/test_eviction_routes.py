"""Integration tests for eviction compliance, court filings, and payment plan FastAPI routes."""

from __future__ import annotations

import pytest
from api import db_utils, evictions
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_CASES = 2
EXPECTED_ARREARS = 1500.0


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a TestClient against an isolated SQLite database."""
    test_db = tmp_path / "test_eviction_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    monkeypatch.setattr(evictions.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    evictions.init_evictions_db()

    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id, unit_id FROM tenants LIMIT 1").fetchone()
        tenant_id = str(row["id"])
        unit_id = str(row["unit_id"])
    finally:
        conn.close()

    db_utils.link_session_tenant("sess_evc_1", tenant_id)
    return TestClient(app), unit_id, tenant_id


def test_eviction_metrics_and_list_routes(client_with_db):
    client, _, _ = client_with_db
    m_resp = client.get("/evictions/metrics")
    assert m_resp.status_code == HTTP_200
    assert m_resp.json()["total_cases"] >= MIN_CASES

    c_resp = client.get("/evictions/cases")
    assert c_resp.status_code == HTTP_200
    assert c_resp.json()["total"] >= MIN_CASES


def test_eviction_case_and_payment_plan_lifecycle_routes(client_with_db):
    client, unit_id, tenant_id = client_with_db

    # 1. Serve notice & open case
    c_resp = client.post(
        "/evictions/cases",
        json={
            "unit_id": unit_id,
            "tenant_id": tenant_id,
            "reason": "Delinquent June rent",
            "arrears_amount": EXPECTED_ARREARS,
        },
    )
    assert c_resp.status_code == HTTP_201
    cid = c_resp.json()["id"]

    assert client.get(f"/evictions/cases/{cid}").status_code == HTTP_200
    patch_resp = client.patch(f"/evictions/cases/{cid}", json={"attorney_name": "K. Adams Esq."})
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["attorney_name"] == "K. Adams Esq."

    # 2. Record court filing & close
    f_resp = client.post(
        f"/evictions/cases/{cid}/file-court",
        json={
            "court_case_number": "CV-2099-088",
            "court_name": "County Civil Court",
            "hearing_date": "2099-08-15",
        },
    )
    assert f_resp.status_code == HTTP_200
    assert f_resp.json()["status"] == "hearing_scheduled"

    # 3. Payment plan create, installment auto-cure, and default
    p_resp = client.post(
        "/evictions/payment-plans",
        json={
            "tenant_id": tenant_id,
            "unit_id": unit_id,
            "total_arrears": EXPECTED_ARREARS,
            "installment_count": 2,
            "next_due_date": "2099-08-01",
            "case_id": cid,
        },
    )
    assert p_resp.status_code == HTTP_201
    pid = p_resp.json()["id"]

    assert client.get("/evictions/payment-plans", params={"case_id": cid}).json()["total"] == 1
    inst = client.post(
        f"/evictions/payment-plans/{pid}/installment",
        json={"amount": EXPECTED_ARREARS, "notes": "Full payoff"},
    )
    assert inst.status_code == HTTP_200
    assert inst.json()["status"] == "completed"

    # Close route directly on another case
    c2 = client.post(
        "/evictions/cases",
        json={"unit_id": unit_id, "tenant_id": tenant_id, "reason": "Lease breach"},
    ).json()["id"]
    cl = client.post(
        f"/evictions/cases/{c2}/close",
        json={"status": "cured_dismissed", "resolution_notes": "Resolved"},
    )
    assert cl.status_code == HTTP_200
    assert cl.json()["status"] == "cured_dismissed"

    # Default plan route
    p2 = client.post(
        "/evictions/payment-plans",
        json={
            "tenant_id": tenant_id,
            "unit_id": unit_id,
            "total_arrears": 500.0,
            "installment_count": 2,
            "next_due_date": "2099-09-01",
        },
    ).json()["id"]
    d_resp = client.post(f"/evictions/payment-plans/{p2}/default", json={"notes": "Missed due"})
    assert d_resp.status_code == HTTP_200
    assert d_resp.json()["status"] == "defaulted"


def test_summaries_session_actions_and_errors(client_with_db):
    client, unit_id, tenant_id = client_with_db

    assert client.get(f"/tenants/{tenant_id}/evictions/summary").status_code == HTTP_200
    assert client.get(f"/units/{unit_id}/evictions/summary").status_code == HTTP_200

    s_notice = client.post(
        "/sessions/sess_evc_1/evictions/serve-notice",
        json={"reason": "Unpaid rent notice from session", "arrears_amount": 950.0},
    )
    assert s_notice.status_code == HTTP_201

    s_plan = client.post(
        "/sessions/sess_evc_1/evictions/create-payment-plan",
        json={"total_arrears": 950.0, "installment_count": 2, "next_due_date": "2099-10-01"},
    )
    assert s_plan.status_code == HTTP_201

    bad = client.post(
        "/sessions/unlinked/evictions/serve-notice",
        json={"reason": "Unlinked session test"},
    )
    assert bad.status_code == HTTP_400
    assert client.get("/evictions/cases/evc_missing").status_code == HTTP_404
