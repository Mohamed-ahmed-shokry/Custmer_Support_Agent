"""Unit tests for move logistics, freight elevator bookings, and checklist engine."""

import sqlite3

import pytest
from api import move_logistics
from api.move_logistics import (
    COIStatus,
    ElevatorBookingStatus,
    ElevatorSlot,
    MoveStatus,
    MoveType,
)

MIN_EXPECTED_MOVES = 2
MIN_EXPECTED_BOOKINGS = 2


@pytest.fixture
def memory_db():
    """In-memory SQLite database connection with move logistics schema."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS units (
            id TEXT PRIMARY KEY,
            unit_number TEXT NOT NULL,
            building TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            FOREIGN KEY (unit_id) REFERENCES units(id)
        )
        """
    )
    cursor.execute(
        "INSERT INTO units (id, unit_number, building) VALUES ('unit_PH1', 'PH1', 'Main Tower')"
    )
    cursor.execute(
        "INSERT INTO units (id, unit_number, building) VALUES ('unit_101', '101', 'West Wing')"
    )
    cursor.execute(
        "INSERT INTO tenants (id, name, email, unit_id) VALUES "
        "('tenant_3', 'Elena Rostova', 'elena@example.com', 'unit_PH1')"
    )
    cursor.execute(
        "INSERT INTO tenants (id, name, email, unit_id) VALUES "
        "('tenant_1', 'Marcus Vance', 'marcus@example.com', 'unit_101')"
    )
    conn.commit()

    move_logistics.init_move_logistics_db(conn)
    yield conn
    conn.close()


def test_init_move_logistics_db_seeds(memory_db):
    """Test table creation and seed data verification."""
    moves = move_logistics.list_move_events(conn=memory_db)
    assert len(moves) >= MIN_EXPECTED_MOVES
    elena_move = next(m for m in moves if m["tenant_id"] == "tenant_3")
    assert elena_move["move_type"] == MoveType.MOVE_IN.value
    assert elena_move["coi_status"] == COIStatus.VERIFIED.value
    assert len(elena_move["checklist_items"]) > 0

    bookings = move_logistics.list_freight_elevator_bookings(conn=memory_db)
    assert len(bookings) >= MIN_EXPECTED_BOOKINGS
    elena_booking = next(b for b in bookings if b["tenant_id"] == "tenant_3")
    assert elena_booking["status"] == ElevatorBookingStatus.CONFIRMED.value


def test_create_and_get_move_event(memory_db):
    """Test creating a new move event and retrieving it."""
    new_move = move_logistics.create_move_event(
        tenant_id="tenant_1",
        unit_id="unit_101",
        move_type=MoveType.INTERNAL_TRANSFER.value,
        scheduled_date="2026-12-01",
        moving_company="Quick Mover Co.",
        mover_contact_phone="+1-555-111-2222",
        coi_status=COIStatus.PENDING.value,
        notes="Moving from 101 to 205",
        conn=memory_db,
    )
    assert new_move["id"].startswith("move_")
    assert new_move["move_type"] == MoveType.INTERNAL_TRANSFER.value
    assert new_move["status"] == MoveStatus.SCHEDULED.value
    assert len(new_move["checklist_items"]) > 0

    fetched = move_logistics.get_move_event(new_move["id"], conn=memory_db)
    assert fetched is not None
    assert fetched["tenant_name"] == "Marcus Vance"
    assert fetched["unit_number"] == "101"


def test_update_move_event_and_checklist(memory_db):
    """Test updating move fields and toggling checklist progress."""
    moves = move_logistics.list_move_events(tenant_id="tenant_1", conn=memory_db)
    move = moves[0]
    move_id = move["id"]

    updated = move_logistics.update_move_event(
        move_id=move_id,
        coi_status=COIStatus.VERIFIED.value,
        moving_company="Global Van Lines",
        status=MoveStatus.IN_PROGRESS.value,
        conn=memory_db,
    )
    assert updated is not None
    assert updated["coi_status"] == COIStatus.VERIFIED.value
    assert updated["status"] == MoveStatus.IN_PROGRESS.value
    assert updated["moving_company"] == "Global Van Lines"

    item_id = updated["checklist_items"][0]["id"]
    initial_pct = updated["checklist_progress_pct"]
    toggled = move_logistics.update_move_checklist_item(
        move_id, item_id, completed=True, conn=memory_db
    )
    assert toggled is not None
    assert toggled["checklist_progress_pct"] >= initial_pct


def test_book_freight_elevator_and_collision_prevention(memory_db):
    """Test elevator booking and collision prevention."""
    booking_date = "2026-11-25"
    slot = ElevatorSlot.SLOT_MORNING_08_12.value

    b1 = move_logistics.book_freight_elevator(
        tenant_id="tenant_1",
        unit_id="unit_101",
        booking_date=booking_date,
        time_slot=slot,
        notes="First reservation",
        conn=memory_db,
    )
    assert b1["id"].startswith("elv_")
    assert b1["status"] == ElevatorBookingStatus.CONFIRMED.value

    with pytest.raises(ValueError, match="already booked"):
        move_logistics.book_freight_elevator(
            tenant_id="tenant_3",
            unit_id="unit_PH1",
            booking_date=booking_date,
            time_slot=slot,
            notes="Colliding reservation",
            conn=memory_db,
        )


def test_cancel_elevator_booking(memory_db):
    """Test cancelling an existing elevator booking."""
    bookings = move_logistics.list_freight_elevator_bookings(conn=memory_db)
    booking = bookings[0]
    cancelled = move_logistics.cancel_elevator_booking(booking["id"], conn=memory_db)
    assert cancelled is not None
    assert cancelled["status"] == ElevatorBookingStatus.CANCELLED.value


def test_move_logistics_metrics_summary(memory_db):
    """Test metrics aggregation."""
    metrics = move_logistics.get_move_logistics_metrics_summary(conn=memory_db)
    assert metrics["total_moves"] >= MIN_EXPECTED_MOVES
    assert metrics["scheduled_moves"] >= 1
    assert "pending_cois" in metrics
    assert "verified_cois" in metrics
    assert "active_elevator_bookings" in metrics
    assert metrics["avg_checklist_progress_pct"] >= 0.0
