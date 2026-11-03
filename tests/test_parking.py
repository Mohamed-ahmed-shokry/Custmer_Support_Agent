"""Unit tests for the parking management and vehicle directory database engine."""

from __future__ import annotations

import sqlite3

import pytest
from api import db_utils, parking
from api.parking import (
    SpotStatus,
    SpotType,
    ViolationStatus,
    ViolationType,
    VisitorPassStatus,
)

MIN_DEFAULT_SPOTS = 6
MIN_ZONE_SPOTS = 2
TEST_VIOLATION_FINE = 75.0
TEST_HANDICAP_FINE = 250.0


@pytest.fixture
def test_parking_db(tmp_path, monkeypatch):
    """Provide an isolated SQLite database for parking tests."""
    db_file = str(tmp_path / "test_parking.db")
    monkeypatch.setattr(db_utils, "DB_NAME", db_file)

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    parking.init_parking_db(conn)
    conn.close()
    return db_file


def test_init_parking_db_seeds_defaults(test_parking_db):
    """Test that default parking spots are seeded upon database initialization."""
    spots = parking.list_parking_spots()
    assert len(spots) >= MIN_DEFAULT_SPOTS
    spot_numbers = [s["spot_number"] for s in spots]
    assert "P-101" in spot_numbers
    assert "EV-01" in spot_numbers
    assert "V-01" in spot_numbers


def test_create_and_get_parking_spot(test_parking_db):
    """Test creating and retrieving an individual parking spot."""
    spot = parking.create_parking_spot(
        spot_number="P-205",
        zone="Garage Level 2",
        spot_type=SpotType.COMPACT.value,
        unit_id="unit_205",
        tenant_id="tenant_205",
        status=SpotStatus.ASSIGNED.value,
        notes="Compact sedan only",
    )
    assert spot["id"].startswith("spot_")
    assert spot["spot_number"] == "P-205"
    assert spot["zone"] == "Garage Level 2"
    assert spot["spot_type"] == SpotType.COMPACT.value

    retrieved = parking.get_parking_spot(spot["id"])
    assert retrieved is not None
    assert retrieved["spot_number"] == "P-205"


def test_list_and_update_parking_spot(test_parking_db):
    """Test filtering spots and updating assignment status."""
    spots = parking.list_parking_spots(zone="Garage Level 1")
    assert len(spots) >= MIN_ZONE_SPOTS

    # Update spot status and unit assignment
    spot_to_update = spots[0]
    updated = parking.update_parking_spot(
        spot_to_update["id"],
        status=SpotStatus.MAINTENANCE.value,
        notes="Repaving stripe lines",
    )
    assert updated is not None
    assert updated["status"] == SpotStatus.MAINTENANCE.value
    assert updated["notes"] == "Repaving stripe lines"

    # Clear unit
    cleared = parking.update_parking_spot(
        spot_to_update["id"],
        clear_unit=True,
        clear_tenant=True,
        status=SpotStatus.VACANT.value,
    )
    assert cleared is not None
    assert cleared["unit_id"] is None
    assert cleared["tenant_id"] is None
    assert cleared["status"] == SpotStatus.VACANT.value


def test_register_and_list_vehicles(test_parking_db):
    """Test resident vehicle registration, lookup, and search."""
    veh = parking.register_vehicle(
        tenant_id="tenant_101",
        unit_id="unit_101",
        license_plate="7XYZ890",
        make="Toyota",
        model="RAV4",
        state_province="CA",
        color="Silver",
        year=2022,
        permit_number="PERM-101A",
    )
    assert veh["id"].startswith("veh_")
    assert veh["license_plate"] == "7XYZ890"
    assert veh["permit_number"] == "PERM-101A"
    assert veh["is_active"] == 1

    # Retrieve
    retrieved = parking.get_vehicle(veh["id"])
    assert retrieved is not None
    assert retrieved["make"] == "Toyota"

    # List by tenant
    tenant_vehs = parking.list_vehicles(tenant_id="tenant_101")
    assert len(tenant_vehs) == 1

    # Search filter
    found = parking.list_vehicles(search="RAV4")
    assert len(found) == 1
    assert found[0]["license_plate"] == "7XYZ890"


def test_update_and_delete_vehicle(test_parking_db):
    """Test updating vehicle details and deleting registration."""
    veh = parking.register_vehicle(
        tenant_id="tenant_102",
        unit_id="unit_102",
        license_plate="8ABC123",
        make="Honda",
        model="Civic",
        color="Blue",
        year=2020,
    )
    # Update color and deactivate
    updated = parking.update_vehicle(
        veh["id"],
        color="Midnight Blue",
        is_active=False,
    )
    assert updated is not None
    assert updated["color"] == "Midnight Blue"
    assert updated["is_active"] == 0

    # Delete vehicle
    del_ok = parking.delete_vehicle(veh["id"])
    assert del_ok is True
    assert parking.get_vehicle(veh["id"]) is None


def test_issue_and_list_visitor_passes(test_parking_db):
    """Test issuing and tracking digital visitor parking passes."""
    vpass = parking.issue_visitor_pass(
        unit_id="unit_101",
        tenant_id="tenant_101",
        visitor_name="Alex Smith",
        vehicle_plate="6MNO456",
        start_time="2026-11-02T10:00:00Z",
        end_time="2026-11-04T10:00:00Z",
        notes="Visiting family",
    )
    assert vpass["id"].startswith("vpass_")
    assert vpass["pass_code"].startswith("VP-")
    assert vpass["status"] == VisitorPassStatus.ACTIVE.value

    # Lookup by code
    by_code = parking.get_visitor_pass(vpass["pass_code"])
    assert by_code is not None
    assert by_code["id"] == vpass["id"]

    # Revoke pass
    revoked = parking.update_visitor_pass(vpass["id"], status=VisitorPassStatus.REVOKED.value)
    assert revoked is not None
    assert revoked["status"] == VisitorPassStatus.REVOKED.value


def test_record_and_update_parking_violations(test_parking_db):
    """Test parking violation recording, lookup, and resolution."""
    viol = parking.record_violation(
        spot_id="spot_101",
        license_plate="9BAD999",
        violation_type=ViolationType.UNAUTHORIZED_PARKING.value,
        fine_amount=TEST_VIOLATION_FINE,
        notes="Parked in assigned resident spot without decal",
    )
    assert viol["id"].startswith("viol_")
    assert viol["license_plate"] == "9BAD999"
    assert viol["status"] == ViolationStatus.ISSUED.value
    assert viol["fine_amount"] == TEST_VIOLATION_FINE

    # List violations
    viols = parking.list_violations(license_plate="9BAD999")
    assert len(viols) == 1

    # Update status to paid
    updated = parking.update_violation(
        viol["id"],
        status=ViolationStatus.PAID.value,
        notes="Paid online via resident portal",
    )
    assert updated is not None
    assert updated["status"] == ViolationStatus.PAID.value


def test_parking_summary_metrics(test_parking_db):
    """Test summary KPI metrics calculations."""
    # Register a vehicle, a pass, and a violation
    parking.register_vehicle(
        tenant_id="tenant_101",
        unit_id="unit_101",
        license_plate="TEST1234",
        make="Tesla",
        model="Model 3",
    )
    parking.issue_visitor_pass(
        unit_id="unit_101",
        tenant_id="tenant_101",
        visitor_name="Guest One",
        vehicle_plate="GUEST123",
        start_time="2026-11-02T12:00:00Z",
        end_time="2026-11-03T12:00:00Z",
    )
    parking.record_violation(
        spot_id="spot_hc_1",
        license_plate="ILLEGAL1",
        violation_type=ViolationType.HANDICAP_UNAUTHORIZED.value,
        fine_amount=TEST_HANDICAP_FINE,
    )

    metrics = parking.get_parking_summary_metrics()
    assert metrics["total_spots"] >= MIN_DEFAULT_SPOTS
    assert metrics["assigned_spots"] >= MIN_ZONE_SPOTS
    assert metrics["visitor_spots"] >= MIN_ZONE_SPOTS
    assert metrics["active_vehicles_count"] >= 1
    assert metrics["active_visitor_passes"] >= 1
    assert metrics["open_violations_count"] >= 1
    assert metrics["total_fines_assessed"] >= TEST_HANDICAP_FINE
