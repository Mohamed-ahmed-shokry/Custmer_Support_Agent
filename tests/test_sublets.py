"""Unit tests for resident subletting, roommate replacement, and guest room occupancy."""

from __future__ import annotations

import sqlite3

import pytest
from api import sublets

# Test constants
EXPECTED_SEEDED_SUBLETS = 2
EXPECTED_SEEDED_OCCUPANTS = 2
EXPECTED_SEEDED_ALERTS = 1
CUSTOM_MONTHLY_RENT = 1200.0
ADMIN_FEE = 150.0
FINE_AMOUNT = 250.0
MIN_OCCUPANCY_LIMIT = 3


@pytest.fixture
def memory_db():
    """Create an isolated in-memory SQLite database connection with seeded records."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create parent tables
    cursor.execute(
        """
        CREATE TABLE units (
            id TEXT PRIMARY KEY,
            unit_number TEXT NOT NULL,
            building_name TEXT NOT NULL DEFAULT '',
            monthly_rent REAL NOT NULL DEFAULT 0.0,
            notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE tenants (
            id TEXT PRIMARY KEY,
            unit_id TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            balance_due REAL DEFAULT 0.0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE billing_transactions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'posted',
            due_date TEXT NOT NULL,
            description TEXT NOT NULL,
            notes TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    # Insert baseline test units and tenants
    cursor.execute(
        "INSERT INTO units (id, unit_number, building_name, monthly_rent) "
        "VALUES ('u1', '101', 'Tower A', 1500.0), ('u2', '202', 'Tower B', 2200.0)"
    )
    cursor.execute(
        "INSERT INTO tenants (id, unit_id, first_name, last_name, email, phone) "
        "VALUES ('t1', 'u1', 'Alice', 'Smith', 'alice@example.com', '555-0101'), "
        "('t2', 'u2', 'Bob', 'Jones', 'bob@example.com', '555-0202')"
    )
    conn.commit()

    sublets.init_sublets_db(conn)
    return conn


def test_init_sublets_db_and_seed(memory_db):
    """Test table creation and seed data population."""
    cursor = memory_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM sublet_requests")
    assert cursor.fetchone()[0] >= EXPECTED_SEEDED_SUBLETS

    cursor.execute("SELECT COUNT(*) FROM sublet_occupants")
    assert cursor.fetchone()[0] >= EXPECTED_SEEDED_OCCUPANTS

    cursor.execute("SELECT COUNT(*) FROM unauthorized_rental_alerts")
    assert cursor.fetchone()[0] >= EXPECTED_SEEDED_ALERTS


def test_create_sublet_request(memory_db):
    """Test creating a new sublet request."""
    req = sublets.create_sublet_request(
        tenant_id="t1",
        unit_id="u1",
        subtenant_name="Carlos Santana",
        subtenant_email="carlos@example.com",
        subtenant_phone="555-1234",
        start_date="2026-12-01",
        end_date="2027-03-01",
        sublet_type=sublets.SubletType.FULL_UNIT,
        monthly_rent=1500.0,
        administrative_fee=ADMIN_FEE,
        reason="Semester abroad study",
        notes="All documentation verified",
        conn=memory_db,
    )

    assert req["id"].startswith("sub_")
    assert req["subtenant_name"] == "Carlos Santana"
    assert req["status"] == sublets.SubletStatus.PENDING
    assert req["fee_paid"] == 0
    assert req["first_name"] == "Alice"
    assert req["unit_number"] == "101"


def test_get_and_list_sublet_requests(memory_db):
    """Test retrieving single request and listing with filters."""
    sublet_list = sublets.list_sublet_requests(unit_id="u1", conn=memory_db)
    assert len(sublet_list) >= 1

    first = sublet_list[0]
    fetched = sublets.get_sublet_request(first["id"], conn=memory_db)
    assert fetched is not None
    assert fetched["id"] == first["id"]


def test_update_sublet_request(memory_db):
    """Test updating fields on a sublet request."""
    req = sublets.create_sublet_request(
        tenant_id="t2",
        unit_id="u2",
        subtenant_name="Dana Scully",
        subtenant_email="dana@example.com",
        start_date="2026-11-20",
        end_date="2027-01-20",
        conn=memory_db,
    )

    updated = sublets.update_sublet_request(
        req["id"],
        {"monthly_rent": CUSTOM_MONTHLY_RENT, "reason": "Field assignment"},
        conn=memory_db,
    )
    assert updated["monthly_rent"] == CUSTOM_MONTHLY_RENT
    assert updated["reason"] == "Field assignment"


def test_approve_sublet_request_and_fee(memory_db):
    """Test approving a sublet request, ledger fee assessment, and occupant registration."""
    req = sublets.create_sublet_request(
        tenant_id="t1",
        unit_id="u1",
        subtenant_name="Fox Mulder",
        subtenant_email="fox@example.com",
        start_date="2026-12-01",
        end_date="2027-04-01",
        conn=memory_db,
    )

    approved = sublets.approve_sublet_request(
        sublet_id=req["id"],
        reviewed_by="Property Manager Skinner",
        assess_fee=True,
        fee_amount=ADMIN_FEE,
        notes="Approved with full background pass",
        auto_register_occupant=True,
        conn=memory_db,
    )

    assert approved["status"] == sublets.SubletStatus.APPROVED
    assert approved["reviewed_by"] == "Property Manager Skinner"
    assert approved["fee_paid"] == 1
    assert approved["fee_transaction_id"].startswith("tx_sub_fee_")

    # Verify occupant was auto-registered
    occupants = sublets.list_occupants(sublet_id=req["id"], conn=memory_db)
    assert len(occupants) == 1
    assert occupants[0]["full_name"] == "Fox Mulder"
    assert occupants[0]["id_verified"] == 1

    # Verify transaction posted to billing_transactions
    cursor = memory_db.cursor()
    cursor.execute(
        "SELECT * FROM billing_transactions WHERE id = ?",
        (approved["fee_transaction_id"],),
    )
    tx_row = cursor.fetchone()
    assert tx_row is not None
    assert tx_row["amount"] == ADMIN_FEE


def test_reject_sublet_request(memory_db):
    """Test rejecting a sublet request with reason."""
    req = sublets.create_sublet_request(
        tenant_id="t2",
        unit_id="u2",
        subtenant_name="Walter Skinner",
        subtenant_email="walter@example.com",
        start_date="2026-12-01",
        end_date="2027-02-01",
        conn=memory_db,
    )

    rejected = sublets.reject_sublet_request(
        sublet_id=req["id"],
        reason="Credit check score did not meet 650 minimum threshold",
        reviewed_by="Assistant Manager",
        conn=memory_db,
    )

    assert rejected["status"] == sublets.SubletStatus.REJECTED
    assert "Credit check score" in rejected["notes"]


def test_occupant_registration_and_occupancy_calc(memory_db):
    """Test registering occupants and unit occupancy calculations."""
    occ = sublets.register_occupant(
        unit_id="u1",
        tenant_id="t1",
        full_name="Samantha Mulder",
        check_in_date="2026-11-15",
        expected_check_out_date="2026-12-15",
        occupant_type=sublets.OccupantType.TEMPORARY_GUEST,
        relationship_to_tenant="sister",
        id_verified=1,
        background_cleared=0,
        notes="Visiting guest for holidays",
        conn=memory_db,
    )

    assert occ["id"].startswith("occ_")
    assert occ["full_name"] == "Samantha Mulder"

    # Test updating occupant
    updated_occ = sublets.update_occupant(
        occ["id"],
        {"status": sublets.OccupantStatus.DEPARTED},
        conn=memory_db,
    )
    assert updated_occ["status"] == sublets.OccupantStatus.DEPARTED

    # Test calculate occupancy
    calc = sublets.calculate_unit_occupancy("u1", conn=memory_db)
    assert calc["unit_id"] == "u1"
    assert calc["max_occupancy_limit"] >= MIN_OCCUPANCY_LIMIT
    assert "total_current_occupancy" in calc
    assert not calc["is_over_capacity"]


def test_unauthorized_rental_alert_and_fine(memory_db):
    """Test reporting an unauthorized short-term rental and assessing fine."""
    alert = sublets.report_unauthorized_rental(
        unit_id="u2",
        tenant_id="t2",
        platform="airbnb",
        listing_url="https://airbnb.com/rooms/123456",
        evidence_summary="Found online listing offering nightly stays with building photos",
        reported_by="Leasing Agent",
        conn=memory_db,
    )

    assert alert["id"].startswith("ura_")
    assert alert["status"] == sublets.RentalAlertStatus.SUSPECTED

    # Update alert
    updated_alert = sublets.update_unauthorized_rental_alert(
        alert["id"],
        {
            "status": sublets.RentalAlertStatus.INVESTIGATING,
            "investigated_by": "Compliance Lead",
        },
        conn=memory_db,
    )
    assert updated_alert["status"] == sublets.RentalAlertStatus.INVESTIGATING

    # Assess fine
    fine_res = sublets.assess_unauthorized_rental_fine(
        alert["id"],
        fine_amount=FINE_AMOUNT,
        conn=memory_db,
    )
    assert fine_res["fine_amount"] == FINE_AMOUNT
    assert fine_res["transaction_id"].startswith("tx_sub_fine_")

    # Check alert updated to confirmed_violation
    alert_check = sublets.get_unauthorized_rental_alert(alert["id"], conn=memory_db)
    assert alert_check["status"] == sublets.RentalAlertStatus.CONFIRMED_VIOLATION
    assert alert_check["penalty_fee"] == FINE_AMOUNT


def test_unit_and_tenant_summaries_and_metrics(memory_db):
    """Test unit summary, tenant summary, and metrics aggregator."""
    unit_sum = sublets.get_unit_sublet_summary("u1", conn=memory_db)
    assert "occupancy" in unit_sum
    assert "sublets" in unit_sum

    tenant_sum = sublets.get_tenant_sublet_summary("t1", conn=memory_db)
    assert "sublets" in tenant_sum
    assert "registered_occupants" in tenant_sum

    metrics = sublets.get_sublet_metrics_summary(conn=memory_db)
    assert metrics["total_sublet_requests"] >= EXPECTED_SEEDED_SUBLETS
    assert "sublets_by_status" in metrics
    assert "total_registered_occupants" in metrics
    assert "total_rental_alerts" in metrics
