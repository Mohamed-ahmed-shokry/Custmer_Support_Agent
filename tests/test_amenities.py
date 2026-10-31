"""Tests for Community Amenity Reservations Database Engine (api/amenities.py)."""

from __future__ import annotations

import pytest
from api import amenities, db_utils


@pytest.fixture
def amenity_db(tmp_path, monkeypatch):
    """Provide a fresh SQLite database for amenity engine tests."""
    db_file = tmp_path / "test_amenities.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_file))
    amenities.create_amenities_tables()
    amenities.seed_default_amenities_if_empty()
    return db_file


def test_seed_default_amenities(amenity_db):
    """Verify default seeded amenities and reservations exist."""
    ams = amenities.list_amenities()
    expected_min_amenities = 5
    assert len(ams) >= expected_min_amenities

    res_list = amenities.list_reservations()
    expected_min_res = 2
    assert len(res_list) >= expected_min_res


def test_create_amenity_and_get(amenity_db):
    """Test creating a new amenity and fetching it by ID."""
    expected_hourly = 30.0
    expected_cap = 40
    created = amenities.create_amenity(
        amenity_id="amenity_pool",
        name="Resort Pool & Sundeck",
        category="poolside_cabana",
        description="Heated salt-water pool with private cabanas and daybeds.",
        capacity=expected_cap,
        hourly_rate=expected_hourly,
        deposit_amount=50.0,
        opening_hour=8,
        closing_hour=21,
    )
    assert created["id"] == "amenity_pool"
    assert created["name"] == "Resort Pool & Sundeck"
    assert created["hourly_rate"] == expected_hourly

    fetched = amenities.get_amenity("amenity_pool")
    assert fetched is not None
    assert fetched["capacity"] == expected_cap


def test_create_amenity_invalid_inputs(amenity_db):
    """Test validation errors for invalid amenity creation inputs."""
    with pytest.raises(ValueError, match="Amenity name cannot be empty"):
        amenities.create_amenity("am_bad_1", name="")

    with pytest.raises(ValueError, match="Invalid category"):
        amenities.create_amenity("am_bad_2", name="Bad Cat", category="nonexistent_space")

    with pytest.raises(ValueError, match="Capacity must be greater than zero"):
        amenities.create_amenity("am_bad_3", name="Bad Cap", capacity=0)

    with pytest.raises(ValueError, match="opening_hour must precede closing_hour"):
        amenities.create_amenity("am_bad_4", name="Bad Hours", opening_hour=22, closing_hour=8)


def test_update_amenity(amenity_db):
    """Test updating existing amenity fields."""
    expected_hourly = 35.0
    expected_cap = 60
    updated = amenities.update_amenity(
        "amenity_clubhouse",
        name="Renovated Clubhouse Lounge",
        hourly_rate=expected_hourly,
        capacity=expected_cap,
    )
    assert updated is not None
    assert updated["name"] == "Renovated Clubhouse Lounge"
    assert updated["hourly_rate"] == expected_hourly
    assert updated["capacity"] == expected_cap


def test_create_reservation_and_conflict(amenity_db):
    """Test reservation creation, fee calculation, and conflict rejection."""
    expected_fee = 105.0
    expected_deposit = 150.0
    res = amenities.create_reservation(
        reservation_id="res_test_01",
        amenity_id="amenity_rooftop",
        tenant_id="tenant_1",
        unit_id="101",
        start_time="2026-11-10T14:00:00Z",
        end_time="2026-11-10T17:00:00Z",
        attendees_count=10,
        notes="Birthday social",
    )
    assert res["id"] == "res_test_01"
    assert res["total_fee"] == expected_fee
    assert res["deposit_paid"] == expected_deposit

    # Attempt overlapping reservation should raise ValueError
    with pytest.raises(ValueError, match="already reserved during this time interval"):
        amenities.create_reservation(
            reservation_id="res_test_conflict",
            amenity_id="amenity_rooftop",
            tenant_id="tenant_2",
            unit_id="204",
            start_time="2026-11-10T15:00:00Z",
            end_time="2026-11-10T18:00:00Z",
        )


def test_update_and_delete_reservation(amenity_db):
    """Test updating reservation status and deleting a reservation."""
    res = amenities.create_reservation(
        reservation_id="res_to_cancel",
        amenity_id="amenity_fitness",
        tenant_id="tenant_1",
        unit_id="101",
        start_time="2026-11-12T08:00:00Z",
        end_time="2026-11-12T09:00:00Z",
    )
    assert res["status"] == "confirmed"

    updated = amenities.update_reservation_status(
        "res_to_cancel", "cancelled", notes="Resident unwell"
    )
    assert updated is not None
    assert updated["status"] == "cancelled"

    deleted = amenities.delete_reservation("res_to_cancel")
    assert deleted is True
    assert amenities.get_reservation("res_to_cancel") is None


def test_summary_metrics(amenity_db):
    """Test calculation of amenity booking metrics."""
    metrics = amenities.get_amenity_summary_metrics()
    expected_min_total = 2
    expected_min_active = 5
    assert metrics["total_reservations"] >= expected_min_total
    assert metrics["confirmed_count"] >= expected_min_total
    assert metrics["total_revenue"] > 0
    assert metrics["active_amenities_count"] >= expected_min_active


def test_list_amenities_and_reservations_filters(amenity_db):
    """Test filtering amenities and reservations by category, status, and tenant."""
    clubhouses = amenities.list_amenities(category="clubhouse", is_active=True)
    assert len(clubhouses) >= 1
    assert all(a["category"] == "clubhouse" for a in clubhouses)

    t1_res = amenities.list_reservations(tenant_id="tenant_1")
    assert len(t1_res) >= 1
    assert all(r["tenant_id"] == "tenant_1" for r in t1_res)

    confirmed_res = amenities.list_reservations(status="confirmed")
    assert len(confirmed_res) >= 1
    assert all(r["status"] == "confirmed" for r in confirmed_res)


def test_reservation_validation_edge_cases(amenity_db):
    """Test capacity limits, invalid times, and invalid statuses."""
    with pytest.raises(ValueError, match="exceeds amenity capacity"):
        amenities.create_reservation(
            reservation_id="res_overcap",
            amenity_id="amenity_guest_suite",
            tenant_id="tenant_1",
            unit_id="101",
            start_time="2026-11-20T14:00:00Z",
            end_time="2026-11-20T16:00:00Z",
            attendees_count=10,  # guest suite capacity is 4
        )

    with pytest.raises(ValueError, match="must be strictly after start_time"):
        amenities.create_reservation(
            reservation_id="res_bad_times",
            amenity_id="amenity_clubhouse",
            tenant_id="tenant_1",
            unit_id="101",
            start_time="2026-11-20T16:00:00Z",
            end_time="2026-11-20T14:00:00Z",
        )

    with pytest.raises(ValueError, match="Invalid status"):
        amenities.create_reservation(
            reservation_id="res_bad_status",
            amenity_id="amenity_clubhouse",
            tenant_id="tenant_1",
            unit_id="101",
            start_time="2026-11-20T14:00:00Z",
            end_time="2026-11-20T16:00:00Z",
            status="invalid_status",
        )
