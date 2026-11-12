"""Tests for Move Logistics & Freight Elevator FastAPI Routes."""

from __future__ import annotations

import pytest
from api import db_utils, move_logistics
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
HTTP_409 = 409
MIN_MOVES_COUNT = 2


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_move_logistics_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    move_logistics.init_move_logistics_db()

    # Link test session to tenant_3
    db_utils.link_session_tenant("sess_test_1", "tenant_3")
    return TestClient(app)


def test_get_move_logistics_metrics_route(client_with_db):
    """Test GET /move-logistics/metrics."""
    res = client_with_db.get("/move-logistics/metrics")
    assert res.status_code == HTTP_200
    data = res.json()
    assert data["total_moves"] >= MIN_MOVES_COUNT
    assert "pending_cois" in data
    assert "active_elevator_bookings" in data


def test_create_and_get_move_event_routes(client_with_db):
    """Test POST /move-logistics and GET /move-logistics/{id}."""
    payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "move_type": "move_out",
        "scheduled_date": "2026-12-01",
        "moving_company": "Pacific Movers",
        "mover_contact_phone": "+1-555-987-6543",
        "notes": "Relocating out of state",
    }
    create_res = client_with_db.post("/move-logistics", json=payload)
    assert create_res.status_code == HTTP_201
    created = create_res.json()["move_event"]
    assert created["move_type"] == "move_out"
    assert created["moving_company"] == "Pacific Movers"

    # Get single
    get_res = client_with_db.get(f"/move-logistics/{created['id']}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["move_event"]["id"] == created["id"]

    # List
    list_res = client_with_db.get("/move-logistics", params={"tenant_id": "tenant_1"})
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1


def test_update_move_event_and_toggle_checklist_routes(client_with_db):
    """Test PATCH /move-logistics/{id} and POST /move-logistics/{id}/checklist."""
    list_res = client_with_db.get("/move-logistics")
    move_id = list_res.json()["items"][0]["id"]

    # Update COI and status
    patch_res = client_with_db.patch(
        f"/move-logistics/{move_id}",
        json={"coi_status": "verified", "status": "in_progress"},
    )
    assert patch_res.status_code == HTTP_200
    updated = patch_res.json()["move_event"]
    assert updated["coi_status"] == "verified"
    assert updated["status"] == "in_progress"

    # Toggle checklist item
    item_id = updated["checklist_items"][0]["id"]
    check_res = client_with_db.post(
        f"/move-logistics/{move_id}/checklist",
        json={"item_id": item_id, "completed": True},
    )
    assert check_res.status_code == HTTP_200
    assert check_res.json()["move_event"]["checklist_items"][0]["completed"] is True


def test_elevator_booking_lifecycle_and_collision_route(client_with_db):
    """Test elevator booking, collision rejection, and cancellation."""
    booking_date = "2026-11-28"
    slot = "08:00-12:00"

    book_res = client_with_db.post(
        "/elevator-bookings",
        json={
            "tenant_id": "tenant_3",
            "unit_id": "unit_PH1",
            "booking_date": booking_date,
            "time_slot": slot,
            "deposit_collected": True,
            "deposit_amount": 300.0,
            "notes": "Morning freight slot",
        },
    )
    assert book_res.status_code == HTTP_201
    booking = book_res.json()["booking"]
    assert booking["time_slot"] == slot

    # Collision test (same slot on same date)
    dup_res = client_with_db.post(
        "/elevator-bookings",
        json={
            "tenant_id": "tenant_1",
            "unit_id": "unit_101",
            "booking_date": booking_date,
            "time_slot": slot,
        },
    )
    assert dup_res.status_code == HTTP_409
    assert "already booked" in dup_res.json()["detail"]

    # Cancel booking
    cancel_res = client_with_db.post(f"/elevator-bookings/{booking['id']}/cancel")
    assert cancel_res.status_code == HTTP_200
    assert cancel_res.json()["booking"]["status"] == "cancelled"


def test_session_schedule_move_and_reserve_elevator_routes(client_with_db):
    """Test 1-click session actions for move and elevator reservation."""
    # 1. Schedule move from session
    move_res = client_with_db.post(
        "/sessions/sess_test_1/schedule-move",
        json={
            "move_type": "move_in",
            "scheduled_date": "2026-11-29",
            "moving_company": "White Glove Movers",
            "notes": "Booked from live resident chat session",
        },
    )
    assert move_res.status_code == HTTP_201
    created_move = move_res.json()["move_event"]
    assert created_move["tenant_id"] == "tenant_3"
    assert created_move["unit_id"] == "unit_PH1"

    # 2. Reserve elevator from session
    elv_res = client_with_db.post(
        "/sessions/sess_test_1/reserve-elevator",
        json={
            "booking_date": "2026-11-29",
            "time_slot": "12:00-16:00",
            "notes": "Afternoon slot for white glove delivery",
        },
    )
    assert elv_res.status_code == HTTP_201
    created_elv = elv_res.json()["booking"]
    assert created_elv["tenant_id"] == "tenant_3"
    assert created_elv["unit_id"] == "unit_PH1"
    assert created_elv["time_slot"] == "12:00-16:00"
