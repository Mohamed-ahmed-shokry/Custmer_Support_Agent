"""Integration tests for resident subletting, occupancy, and unauthorized rental FastAPI routes."""

# ruff: noqa: PLR2004, E501

from __future__ import annotations

import pytest
from api import db_utils, sublets
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_sublet_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_billing_transactions()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    sublets.init_sublets_db()

    # Link test session to tenant_1
    db_utils.link_session_tenant("sess_sub_1", "tenant_1")
    return TestClient(app)


def test_get_sublet_metrics_route(client_with_db):
    """Test GET /sublets/metrics."""
    res = client_with_db.get("/sublets/metrics")
    assert res.status_code == HTTP_200
    data = res.json()
    assert "total_sublet_requests" in data
    assert "pending_requests" in data
    assert "total_registered_occupants" in data
    assert "total_rental_alerts" in data


def test_sublet_crud_and_approval_routes(client_with_db):
    """Test POST, GET, PATCH, and approval/rejection endpoints for sublets."""
    create_payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "subtenant_name": "Marcus Aurelius",
        "subtenant_email": "marcus@rome.example",
        "subtenant_phone": "(555) 777-8899",
        "start_date": "2026-12-01",
        "end_date": "2027-02-28",
        "sublet_type": "full_unit",
        "monthly_rent": 1650.0,
        "administrative_fee": 150.0,
        "reason": "Diplomatic sabbatical",
        "notes": "Verified references",
    }
    create_res = client_with_db.post("/sublets", json=create_payload)
    assert create_res.status_code == HTTP_201
    created_sub = create_res.json()["sublet"]
    sub_id = created_sub["id"]
    assert created_sub["subtenant_name"] == "Marcus Aurelius"
    assert created_sub["status"] == "pending"

    # List sublets
    list_res = client_with_db.get("/sublets?tenant_id=tenant_1")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["count"] >= 1

    # Get single sublet
    get_res = client_with_db.get(f"/sublets/{sub_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["sublet"]["id"] == sub_id

    # Update sublet
    patch_res = client_with_db.patch(
        f"/sublets/{sub_id}",
        json={"monthly_rent": 1700.0, "reason": "Extended sabbatical"},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["sublet"]["monthly_rent"] == 1700.0

    # Approve sublet
    approve_res = client_with_db.post(
        f"/sublets/{sub_id}/approve",
        json={
            "reviewed_by": "Senior PM Claudius",
            "assess_fee": True,
            "fee_amount": 150.0,
            "notes": "All background cleared",
            "auto_register_occupant": True,
        },
    )
    assert approve_res.status_code == HTTP_200
    assert approve_res.json()["sublet"]["status"] == "approved"
    assert approve_res.json()["sublet"]["fee_paid"] == 1


def test_sublet_rejection_and_fee_assessment_routes(client_with_db):
    """Test rejecting a sublet and assessing administrative review fee."""
    create_payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "subtenant_name": "Julius Caesar",
        "subtenant_email": "julius@rome.example",
        "start_date": "2026-12-15",
        "end_date": "2027-01-15",
    }
    create_res = client_with_db.post("/sublets", json=create_payload)
    sub_id = create_res.json()["sublet"]["id"]

    # Reject
    reject_res = client_with_db.post(
        f"/sublets/{sub_id}/reject",
        json={"reason": "Lease prohibits sublets under 30 days", "reviewed_by": "Senate PM"},
    )
    assert reject_res.status_code == HTTP_200
    assert reject_res.json()["sublet"]["status"] == "rejected"

    # Assess fee on another request
    sub2_res = client_with_db.post(
        "/sublets",
        json={
            "tenant_id": "tenant_1",
            "subtenant_name": "Brutus",
            "subtenant_email": "brutus@rome.example",
            "start_date": "2026-12-01",
            "end_date": "2027-03-01",
        },
    )
    sub2_id = sub2_res.json()["sublet"]["id"]
    fee_res = client_with_db.post(f"/sublets/{sub2_id}/assess-fee", json={"fee_amount": 150.0})
    assert fee_res.status_code == HTTP_200
    assert fee_res.json()["status"] == "posted"


def test_occupant_and_unit_occupancy_routes(client_with_db):
    """Test occupant registration, update, list, and unit occupancy calculation."""
    occ_payload = {
        "unit_id": "unit_101",
        "tenant_id": "tenant_1",
        "full_name": "Octavia Minor",
        "check_in_date": "2026-11-20",
        "email": "octavia@rome.example",
        "phone": "(555) 444-3322",
        "occupant_type": "temporary_guest",
        "relationship_to_tenant": "sister",
        "id_verified": 1,
        "background_cleared": 1,
        "notes": "Holiday visit",
    }
    reg_res = client_with_db.post("/sublets/occupants", json=occ_payload)
    assert reg_res.status_code == HTTP_201
    occ = reg_res.json()["occupant"]
    occ_id = occ["id"]
    assert occ["full_name"] == "Octavia Minor"

    # List occupants
    list_res = client_with_db.get("/sublets/occupants?unit_id=unit_101")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["count"] >= 1

    # Get single occupant
    get_res = client_with_db.get(f"/sublets/occupants/{occ_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["occupant"]["id"] == occ_id

    # Update occupant
    patch_res = client_with_db.patch(f"/sublets/occupants/{occ_id}", json={"status": "departed"})
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["occupant"]["status"] == "departed"

    # Unit occupancy calculation
    occ_calc_res = client_with_db.get("/units/unit_101/occupancy")
    assert occ_calc_res.status_code == HTTP_200
    occ_data = occ_calc_res.json()
    assert occ_data["unit_id"] == "unit_101"
    assert occ_data["max_occupancy_limit"] >= 3
    assert "is_over_capacity" in occ_data


def test_unauthorized_rental_alerts_routes(client_with_db):
    """Test unauthorized rental alert logging, listing, updating, and fine assessment."""
    alert_payload = {
        "unit_id": "unit_101",
        "tenant_id": "tenant_1",
        "platform": "airbnb",
        "listing_url": "https://airbnb.com/rooms/rome-101",
        "evidence_summary": "Active listing showing unit 101 balcony with nightly rates",
        "reported_by": "Night Concierge",
    }
    report_res = client_with_db.post("/sublets/unauthorized-alerts", json=alert_payload)
    assert report_res.status_code == HTTP_201
    alert = report_res.json()["alert"]
    alert_id = alert["id"]
    assert alert["platform"] == "airbnb"
    assert alert["status"] == "suspected"

    # List alerts
    list_res = client_with_db.get("/sublets/unauthorized-alerts?unit_id=unit_101")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["count"] >= 1

    # Get single alert
    get_res = client_with_db.get(f"/sublets/unauthorized-alerts/{alert_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["alert"]["id"] == alert_id

    # Update alert
    patch_res = client_with_db.patch(
        f"/sublets/unauthorized-alerts/{alert_id}",
        json={"status": "investigating", "investigated_by": "Security Officer Titus"},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["alert"]["status"] == "investigating"

    # Assess fine
    fine_res = client_with_db.post(
        f"/sublets/unauthorized-alerts/{alert_id}/assess-fine",
        json={"fine_amount": 250.0},
    )
    assert fine_res.status_code == HTTP_200
    assert fine_res.json()["status"] == "posted"
    assert fine_res.json()["fine_amount"] == 250.0


def test_unit_and_tenant_sublet_summaries(client_with_db):
    """Test unit and tenant comprehensive sublet summary endpoints."""
    unit_res = client_with_db.get("/units/unit_101/sublet/summary")
    assert unit_res.status_code == HTTP_200
    unit_data = unit_res.json()
    assert unit_data["unit_id"] == "unit_101"
    assert "occupancy" in unit_data
    assert "sublets" in unit_data

    tenant_res = client_with_db.get("/tenants/tenant_1/sublet/summary")
    assert tenant_res.status_code == HTTP_200
    tenant_data = tenant_res.json()
    assert tenant_data["tenant_id"] == "tenant_1"
    assert "registered_occupants" in tenant_data
    assert "rental_alerts" in tenant_data


def test_session_1click_sublet_actions(client_with_db):
    """Test 1-click sublet submission and unauthorized rental reporting from active chat session."""
    # Sublet request from session
    sub_action_res = client_with_db.post(
        "/sessions/sess_sub_1/submit-sublet-request",
        json={
            "subtenant_name": "Cicero Orator",
            "subtenant_email": "cicero@rome.example",
            "start_date": "2026-12-01",
            "end_date": "2027-02-01",
            "sublet_type": "full_unit",
            "monthly_rent": 1500.0,
            "reason": "Court trial in provincial capital",
        },
    )
    assert sub_action_res.status_code == HTTP_201
    assert sub_action_res.json()["status"] == "submitted"
    assert "Cicero Orator" in sub_action_res.json()["message"]

    # Unauthorized rental report from session
    report_action_res = client_with_db.post(
        "/sessions/sess_sub_1/report-unauthorized-rental",
        json={
            "platform": "vrbo",
            "evidence_summary": "Neighbor in 102 reported strangers unlocking door with code",
            "listing_url": "https://vrbo.com/12345",
        },
    )
    assert report_action_res.status_code == HTTP_201
    assert report_action_res.json()["status"] == "reported"

    # Test invalid session
    invalid_res = client_with_db.post(
        "/sessions/nonexistent_session/submit-sublet-request",
        json={
            "subtenant_name": "Ghost",
            "subtenant_email": "ghost@example.com",
            "start_date": "2026-12-01",
            "end_date": "2027-01-01",
        },
    )
    assert invalid_res.status_code == HTTP_400
