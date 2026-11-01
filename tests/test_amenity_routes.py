"""Tests for Community Amenity and Reservation FastAPI Routes (api/main.py)."""

from __future__ import annotations

import pytest
from api import amenities, db_utils
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_409 = 409


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_amenity_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    amenities.create_amenities_tables()
    amenities.seed_default_amenities_if_empty()
    return TestClient(app)


def test_list_and_get_amenities(client_with_db):
    """Test GET /amenities and GET /amenities/{id}."""
    expected_min_count = 5
    res = client_with_db.get("/amenities")
    assert res.status_code == HTTP_200
    data = res.json()
    assert len(data["items"]) >= expected_min_count

    res_single = client_with_db.get("/amenities/amenity_clubhouse")
    assert res_single.status_code == HTTP_200
    assert res_single.json()["amenity"]["name"] == "Grand Community Clubhouse"


def test_create_and_update_amenity_route(client_with_db):
    """Test POST /amenities and PATCH /amenities/{id}."""
    expected_rate = 20.0
    create_payload = {
        "name": "Co-Working Conference Hub",
        "category": "conference_room",
        "description": "Quiet conference facility with high-speed fiber.",
        "capacity": 12,
        "hourly_rate": 15.0,
        "deposit_amount": 20.0,
        "opening_hour": 8,
        "closing_hour": 20,
    }
    res = client_with_db.post("/amenities", json=create_payload)
    assert res.status_code == HTTP_201
    created_id = res.json()["amenity"]["id"]

    patch_payload = {"name": "Executive Conference Room", "hourly_rate": expected_rate}
    res_patch = client_with_db.patch(f"/amenities/{created_id}", json=patch_payload)
    assert res_patch.status_code == HTTP_200
    assert res_patch.json()["amenity"]["name"] == "Executive Conference Room"
    assert res_patch.json()["amenity"]["hourly_rate"] == expected_rate


def test_create_reservation_route_and_conflict(client_with_db):
    """Test booking an amenity and asserting 409 conflict on overlapping times."""
    expected_fee = 45.0
    payload = {
        "amenity_id": "amenity_bbq",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "start_time": "2026-11-25T13:00:00Z",
        "end_time": "2026-11-25T16:00:00Z",
        "attendees_count": 6,
        "notes": "Holiday BBQ",
    }
    res = client_with_db.post("/amenity-reservations", json=payload)
    assert res.status_code == HTTP_201
    res_data = res.json()["reservation"]
    assert res_data["total_fee"] == expected_fee
    res_id = res_data["id"]

    # Overlapping conflict test
    conflict_payload = {
        "amenity_id": "amenity_bbq",
        "tenant_id": "tenant_2",
        "unit_id": "unit_204",
        "start_time": "2026-11-25T14:00:00Z",
        "end_time": "2026-11-25T17:00:00Z",
        "attendees_count": 4,
    }
    res_conflict = client_with_db.post("/amenity-reservations", json=conflict_payload)
    assert res_conflict.status_code == HTTP_409

    # Update status test
    res_update = client_with_db.patch(
        f"/amenity-reservations/{res_id}",
        json={"status": "cancelled", "notes": "Cancelled by resident"},
    )
    assert res_update.status_code == HTTP_200
    assert res_update.json()["reservation"]["status"] == "cancelled"

    # Delete test
    res_del = client_with_db.delete(f"/amenity-reservations/{res_id}")
    assert res_del.status_code == HTTP_200
    assert res_del.json()["status"] == "deleted"


def test_amenity_metrics_route(client_with_db):
    """Test GET /amenity-reservations/metrics."""
    expected_min_total = 2
    expected_min_active = 5
    res = client_with_db.get("/amenity-reservations/metrics")
    assert res.status_code == HTTP_200
    data = res.json()
    assert data["total_reservations"] >= expected_min_total
    assert data["active_amenities_count"] >= expected_min_active


def test_tenant_reservations_route(client_with_db):
    """Test GET /tenants/{id}/amenity-reservations."""
    res = client_with_db.get("/tenants/tenant_1/amenity-reservations")
    assert res.status_code == HTTP_200
    data = res.json()
    assert len(data["items"]) >= 1
    assert data["items"][0]["tenant_id"] == "tenant_1"
