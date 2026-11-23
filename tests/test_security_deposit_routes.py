"""Integration tests for security deposit escrow, deductions, and dispute FastAPI routes."""

from __future__ import annotations

import pytest
from api import db_utils, security_deposits
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_DEPOSITS = 2
EXPECTED_PRINCIPAL = 1800.0
EXPECTED_DEDUCTION = 120.0
EXPECTED_NET = 1680.0


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a TestClient against an isolated SQLite database."""
    test_db = tmp_path / "test_deposit_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    monkeypatch.setattr(security_deposits.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    security_deposits.init_security_deposits_db()

    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id, unit_id FROM tenants LIMIT 1").fetchone()
        tenant_id = str(row["id"])
        unit_id = str(row["unit_id"])
    finally:
        conn.close()

    db_utils.link_session_tenant("sess_dep_1", tenant_id)
    return TestClient(app), unit_id, tenant_id


def test_deposit_metrics_and_list_routes(client_with_db):
    client, _, _ = client_with_db
    resp = client.get("/deposits/metrics")
    assert resp.status_code == HTTP_200
    data = resp.json()
    assert data["total_deposits"] >= MIN_DEPOSITS

    list_resp = client.get("/deposits")
    assert list_resp.status_code == HTTP_200
    assert list_resp.json()["total"] >= MIN_DEPOSITS


def test_deposit_full_lifecycle_routes(client_with_db):
    client, unit_id, tenant_id = client_with_db

    # 1. Create deposit
    create_resp = client.post(
        "/deposits",
        json={
            "unit_id": unit_id,
            "tenant_id": tenant_id,
            "principal_amount": EXPECTED_PRINCIPAL,
            "escrow_account_ref": "ESC-ROUTE-01",
        },
    )
    assert create_resp.status_code == HTTP_201
    dep_id = create_resp.json()["id"]

    # 2. Get & Patch
    get_resp = client.get(f"/deposits/{dep_id}")
    assert get_resp.status_code == HTTP_200
    assert get_resp.json()["principal_amount"] == EXPECTED_PRINCIPAL

    patch_resp = client.patch(f"/deposits/{dep_id}", json={"notes": "Verified escrow"})
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["notes"] == "Verified escrow"

    # 3. Add, list, delete deduction
    ded_resp = client.post(
        f"/deposits/{dep_id}/deductions",
        json={
            "category": "cleaning",
            "description": "Carpet steam clean",
            "amount": EXPECTED_DEDUCTION,
            "evidence_ref": "INSP-99",
        },
    )
    assert ded_resp.status_code == HTTP_201
    ded_id = ded_resp.json()["id"]

    ded_list = client.get(f"/deposits/{dep_id}/deductions")
    assert ded_list.status_code == HTTP_200
    assert ded_list.json()["total"] == 1

    # 4. Issue disposition statement
    stmt_resp = client.post(
        f"/deposits/{dep_id}/statement",
        json={"move_out_date": "2099-08-01", "forwarding_address": "123 Elm St"},
    )
    assert stmt_resp.status_code == HTTP_200
    assert stmt_resp.json()["net_refundable"] == EXPECTED_NET
    assert "Carpet steam clean" in stmt_resp.json()["statement_markdown"]

    # 5. Open, list, resolve dispute
    dsp_resp = client.post(
        f"/deposits/{dep_id}/disputes",
        json={"disputed_amount": 120.0, "reason": "Carpet was already worn at move-in"},
    )
    assert dsp_resp.status_code == HTTP_201
    dsp_id = dsp_resp.json()["id"]

    dsp_list = client.get("/deposits/disputes", params={"deposit_id": dep_id})
    assert dsp_list.status_code == HTTP_200
    assert dsp_list.json()["total"] == 1

    res_resp = client.post(
        f"/deposits/disputes/{dsp_id}/resolve",
        json={
            "status": "resolved_upheld",
            "resolution_notes": "Inspection photos confirmed stains",
        },
    )
    assert res_resp.status_code == HTTP_200
    assert res_resp.json()["status"] == "resolved_upheld"

    # 6. Issue refund
    ref_resp = client.post(f"/deposits/{dep_id}/refund", json={"refund_method": "ach"})
    assert ref_resp.status_code == HTTP_200
    assert ref_resp.json()["status"] == "partial_refund"
    assert ref_resp.json()["refund_amount"] == EXPECTED_NET

    # 7. Delete deduction route
    del_resp = client.delete(f"/deposits/deductions/{ded_id}")
    assert del_resp.status_code == HTTP_200
    assert del_resp.json()["deleted"] is True


def test_summaries_and_session_actions_and_404s(client_with_db):
    client, unit_id, tenant_id = client_with_db

    u_resp = client.get(f"/units/{unit_id}/deposits/summary")
    assert u_resp.status_code == HTTP_200
    assert u_resp.json()["total_deposits"] >= 1

    t_resp = client.get(f"/tenants/{tenant_id}/deposits/summary")
    assert t_resp.status_code == HTTP_200
    dep_id = t_resp.json()["primary_deposit"]["id"]

    # 1-click session add deduction
    s_ded = client.post(
        "/sessions/sess_dep_1/deposits/add-deduction",
        json={
            "deposit_id": dep_id,
            "category": "key_replacement",
            "description": "Unreturned mailbox key",
            "amount": 35.0,
        },
    )
    assert s_ded.status_code == HTTP_201

    # 1-click session open dispute
    s_dsp = client.post(
        "/sessions/sess_dep_1/deposits/open-dispute",
        json={
            "deposit_id": dep_id,
            "disputed_amount": 35.0,
            "reason": "Mailbox key was left on kitchen counter",
        },
    )
    assert s_dsp.status_code == HTTP_201

    # Unlinked session returns 400
    bad_sess = client.post(
        "/sessions/unlinked_sess/deposits/open-dispute",
        json={"deposit_id": dep_id, "disputed_amount": 10.0, "reason": "Test unlinked session"},
    )
    assert bad_sess.status_code == HTTP_400

    # Missing deposit returns 404
    assert client.get("/deposits/dep_missing").status_code == HTTP_404
