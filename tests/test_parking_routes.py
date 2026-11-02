"""Tests for Parking Management and Vehicle Directory FastAPI Routes (api/main.py)."""

from __future__ import annotations

import pytest
from api import db_utils, parking
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
HTTP_409 = 409
MIN_DEFAULT_SPOTS = 6
TEST_FINE = 65.0


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_parking_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    parking.init_parking_db()

    return TestClient(app)


def test_parking_spots_routes(client_with_db):
    """Test spot listing, creation, and updating."""
    # List default spots
    res = client_with_db.get("/parking/spots")
    assert res.status_code == HTTP_200
    assert len(res.json()["items"]) >= MIN_DEFAULT_SPOTS

    # Create new spot
    create_payload = {
        "spot_number": "P-999",
        "zone": "North Perimeter",
        "spot_type": "visitor",
        "status": "visitor_open",
        "notes": "Added temporary visitor spot",
    }
    create_res = client_with_db.post("/parking/spots", json=create_payload)
    assert create_res.status_code == HTTP_201
    spot_id = create_res.json()["spot"]["id"]

    # Duplicate spot conflict
    dup_res = client_with_db.post("/parking/spots", json=create_payload)
    assert dup_res.status_code == HTTP_409

    # Get spot
    get_res = client_with_db.get(f"/parking/spots/{spot_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["spot"]["spot_number"] == "P-999"

    # Patch spot
    patch_res = client_with_db.patch(
        f"/parking/spots/{spot_id}",
        json={"status": "maintenance", "notes": "Fresh paint"},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["spot"]["status"] == "maintenance"


def test_vehicle_registration_routes(client_with_db):
    """Test vehicle registration, listing, tenant lookup, and de-registration."""
    # Register vehicle
    veh_payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "license_plate": "7XYZ999",
        "state_province": "CA",
        "make": "Subaru",
        "model": "Outback",
        "color": "Green",
        "year": 2023,
    }
    reg_res = client_with_db.post("/parking/vehicles", json=veh_payload)
    assert reg_res.status_code == HTTP_201
    veh_id = reg_res.json()["vehicle"]["id"]
    assert reg_res.json()["vehicle"]["license_plate"] == "7XYZ999"

    # List vehicles
    list_res = client_with_db.get("/parking/vehicles?tenant_id=tenant_1")
    assert list_res.status_code == HTTP_200
    assert len(list_res.json()["items"]) == 1

    # List tenant vehicles endpoint
    tenant_vehs = client_with_db.get("/tenants/tenant_1/vehicles")
    assert tenant_vehs.status_code == HTTP_200
    assert len(tenant_vehs.json()["items"]) == 1

    # Update vehicle
    update_res = client_with_db.patch(
        f"/parking/vehicles/{veh_id}",
        json={"color": "Forest Green"},
    )
    assert update_res.status_code == HTTP_200
    assert update_res.json()["vehicle"]["color"] == "Forest Green"

    # Delete vehicle
    del_res = client_with_db.delete(f"/parking/vehicles/{veh_id}")
    assert del_res.status_code == HTTP_200
    assert del_res.json()["status"] == "deleted"


def test_visitor_pass_routes(client_with_db):
    """Test visitor pass issuance, lookup, and revocation."""
    pass_payload = {
        "unit_id": "unit_101",
        "tenant_id": "tenant_1",
        "visitor_name": "Marcus Vance",
        "vehicle_plate": "5ABC888",
        "start_time": "2026-11-02T08:00:00Z",
        "end_time": "2026-11-03T08:00:00Z",
        "notes": "Weekend guest pass",
    }
    issue_res = client_with_db.post("/parking/visitor-passes", json=pass_payload)
    assert issue_res.status_code == HTTP_201
    pass_data = issue_res.json()["pass_info"]
    pass_id = pass_data["id"]
    assert pass_data["pass_code"].startswith("VP-")

    # List visitor passes
    list_res = client_with_db.get("/parking/visitor-passes")
    assert list_res.status_code == HTTP_200
    assert len(list_res.json()["items"]) >= 1

    # Revoke pass
    revoke_res = client_with_db.patch(
        f"/parking/visitor-passes/{pass_id}",
        json={"status": "revoked"},
    )
    assert revoke_res.status_code == HTTP_200
    assert revoke_res.json()["pass_info"]["status"] == "revoked"


def test_session_issue_visitor_pass_route(client_with_db):
    """Test 1-click visitor pass issuance from active resident chat session."""
    session_id = "sess_resident_parking_101"
    db_utils.link_session_tenant(session_id, "tenant_1")

    payload = {
        "visitor_name": "Sarah Connor",
        "vehicle_plate": "T800XYZ",
        "start_time": "2026-11-02T18:00:00Z",
        "end_time": "2026-11-02T23:59:59Z",
        "notes": "Visiting tonight",
    }
    res = client_with_db.post(f"/sessions/{session_id}/issue-visitor-pass", json=payload)
    assert res.status_code == HTTP_201
    assert res.json()["pass_info"]["visitor_name"] == "Sarah Connor"
    assert res.json()["pass_info"]["unit_id"] == "unit_101"


def test_parking_violations_and_metrics_routes(client_with_db):
    """Test recording violations, status updates, and summary metrics."""
    viol_payload = {
        "spot_id": "spot_101",
        "license_plate": "ILLEGAL9",
        "violation_type": "blocking_driveway",
        "fine_amount": TEST_FINE,
        "notes": "Blocking garage entrance ramp",
    }
    viol_res = client_with_db.post("/parking/violations", json=viol_payload)
    assert viol_res.status_code == HTTP_201
    viol_id = viol_res.json()["violation"]["id"]

    # List violations
    viols = client_with_db.get("/parking/violations")
    assert viols.status_code == HTTP_200
    assert len(viols.json()["items"]) >= 1

    # Update violation status
    up_viol = client_with_db.patch(
        f"/parking/violations/{viol_id}",
        json={"status": "paid"},
    )
    assert up_viol.status_code == HTTP_200
    assert up_viol.json()["violation"]["status"] == "paid"

    # Check metrics
    metrics_res = client_with_db.get("/parking/metrics")
    assert metrics_res.status_code == HTTP_200
    metrics = metrics_res.json()
    assert metrics["total_spots"] >= MIN_DEFAULT_SPOTS
    assert metrics["total_fines_assessed"] >= TEST_FINE
