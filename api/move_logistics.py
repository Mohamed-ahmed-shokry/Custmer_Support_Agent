"""Database schema, CRUD operations, move logistics, and elevator engine."""

from __future__ import annotations

import datetime
import json
import secrets
import sqlite3
from enum import StrEnum
from typing import Any

from api import db_utils

# Constants
MIN_SEEDED_MOVES = 2
MIN_SEEDED_ELEVATOR_BOOKINGS = 2


class MoveType(StrEnum):
    MOVE_IN = "move_in"
    MOVE_OUT = "move_out"
    INTERNAL_TRANSFER = "internal_transfer"


class MoveStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ElevatorSlot(StrEnum):
    SLOT_MORNING_08_12 = "08:00-12:00"
    SLOT_AFTERNOON_12_16 = "12:00-16:00"
    SLOT_EVENING_16_20 = "16:00-20:00"


class ElevatorBookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class COIStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    WAIVED = "waived"
    REJECTED = "rejected"


def _generate_move_number(move_type: str = MoveType.MOVE_IN) -> str:
    if move_type == MoveType.MOVE_IN:
        prefix = "MOV-IN"
    elif move_type == MoveType.MOVE_OUT:
        prefix = "MOV-OUT"
    else:
        prefix = "MOV-TRF"
    suffix = secrets.token_hex(3).upper()
    year = datetime.datetime.now(datetime.UTC).year
    return f"{prefix}-{year}-{suffix}"


def _generate_booking_number() -> str:
    suffix = secrets.token_hex(3).upper()
    year = datetime.datetime.now(datetime.UTC).year
    return f"ELV-{year}-{suffix}"


def init_move_logistics_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize database tables for move logistics and freight elevator bookings."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS move_logistics_events (
                id TEXT PRIMARY KEY,
                move_number TEXT UNIQUE NOT NULL,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                move_type TEXT NOT NULL DEFAULT 'move_in',
                scheduled_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                moving_company TEXT,
                mover_contact_phone TEXT,
                coi_status TEXT NOT NULL DEFAULT 'pending',
                coi_document_url TEXT,
                coi_notes TEXT,
                loading_dock_required INTEGER NOT NULL DEFAULT 1,
                loading_dock_assigned TEXT,
                key_handover_status TEXT NOT NULL DEFAULT 'pending',
                keys_count INTEGER NOT NULL DEFAULT 2,
                fobs_count INTEGER NOT NULL DEFAULT 2,
                forwarding_address TEXT,
                security_deposit_action TEXT DEFAULT 'pending',
                inspection_id TEXT,
                notes TEXT,
                checklist_progress_pct REAL NOT NULL DEFAULT 0.0,
                checklist_items_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS freight_elevator_bookings (
                id TEXT PRIMARY KEY,
                booking_number TEXT UNIQUE NOT NULL,
                move_id TEXT,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                time_slot TEXT NOT NULL,
                elevator_identifier TEXT NOT NULL DEFAULT 'Freight Elevator #1',
                status TEXT NOT NULL DEFAULT 'confirmed',
                deposit_collected INTEGER NOT NULL DEFAULT 0,
                deposit_amount REAL NOT NULL DEFAULT 250.0,
                padding_installed INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (move_id) REFERENCES move_logistics_events(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id),
                UNIQUE(booking_date, time_slot, elevator_identifier)
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_move_events_tenant ON move_logistics_events(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_move_events_unit ON move_logistics_events(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_move_events_date "
            "ON move_logistics_events(scheduled_date)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_elevator_tenant ON freight_elevator_bookings(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_elevator_date "
            "ON freight_elevator_bookings(booking_date)"
        )

        conn.commit()
        _seed_default_move_logistics(conn)
    finally:
        if close_conn:
            conn.close()


def _default_checklist_items(move_type: str) -> list[dict[str, Any]]:
    if move_type == MoveType.MOVE_IN:
        return [
            {
                "id": "coi_submission",
                "label": "Moving Company Certificate of Insurance (COI)",
                "completed": False,
            },
            {
                "id": "elevator_reserved",
                "label": "Freight Elevator Time Slot Reserved",
                "completed": False,
            },
            {
                "id": "loading_dock_permit",
                "label": "Loading Dock Parking Permit Issued",
                "completed": False,
            },
            {
                "id": "inspection_scheduled",
                "label": "Move-In Condition Inspection Completed",
                "completed": False,
            },
            {
                "id": "keys_issued",
                "label": "Keys & Digital Access Fobs Handover",
                "completed": False,
            },
        ]
    return [
        {
            "id": "notice_given",
            "label": "Formal Notice of Vacancy Confirmed",
            "completed": True,
        },
        {
            "id": "coi_submission",
            "label": "Moving Company Certificate of Insurance (COI)",
            "completed": False,
        },
        {
            "id": "elevator_reserved",
            "label": "Freight Elevator Time Slot Reserved",
            "completed": False,
        },
        {
            "id": "forwarding_address",
            "label": "Forwarding Address on File",
            "completed": False,
        },
        {
            "id": "inspection_scheduled",
            "label": "Move-Out Walk-Through Inspection",
            "completed": False,
        },
        {
            "id": "keys_returned",
            "label": "All Unit Keys & Access Fobs Returned",
            "completed": False,
        },
        {
            "id": "deposit_accounting",
            "label": "Security Deposit Statement & Refund Processed",
            "completed": False,
        },
    ]


def _calculate_checklist_progress(checklist: list[dict[str, Any]]) -> float:
    if not checklist:
        return 0.0
    completed_count = sum(1 for item in checklist if item.get("completed", False))
    return round((completed_count / len(checklist)) * 100.0, 1)


def _seed_default_move_logistics(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM move_logistics_events")
    count_moves = cursor.fetchone()[0]

    now_utc = datetime.datetime.now(datetime.UTC)
    now_iso = now_utc.isoformat()
    upcoming_move_date = (now_utc + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    if count_moves < MIN_SEEDED_MOVES:
        move_1_id = "move_elena_ph1"
        chk_1 = _default_checklist_items(MoveType.MOVE_IN)
        chk_1[0]["completed"] = True
        chk_1[1]["completed"] = True
        chk_progress_1 = _calculate_checklist_progress(chk_1)

        cursor.execute(
            """
            INSERT OR IGNORE INTO move_logistics_events (
                id, move_number, tenant_id, unit_id, move_type, scheduled_date,
                status, moving_company, mover_contact_phone, coi_status, coi_document_url,
                coi_notes, loading_dock_required, loading_dock_assigned, key_handover_status,
                keys_count, fobs_count, forwarding_address, security_deposit_action,
                inspection_id, notes, checklist_progress_pct, checklist_items_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                move_1_id,
                "MOV-IN-2026-ELENA1",
                "tenant_3",
                "unit_PH1",
                MoveType.MOVE_IN.value,
                upcoming_move_date,
                MoveStatus.SCHEDULED.value,
                "Apex Elite Moving & White Glove Delivery",
                "+1-555-432-8899",
                COIStatus.VERIFIED.value,
                "https://documents.property.internal/coi/apex_elite_2026.pdf",
                "$2,000,000 general liability policy with building named as additional insured.",
                1,
                "Dock Bay #2 (South Loading Bay)",
                "scheduled",
                3,
                3,
                None,
                "paid_in_full",
                "insp_ph1_movein",
                "Elevator padding and floor runners required for marble lobby floor.",
                chk_progress_1,
                json.dumps(chk_1),
                now_iso,
                now_iso,
            ),
        )

        move_2_id = "move_marcus_101"
        chk_2 = _default_checklist_items(MoveType.MOVE_OUT)
        chk_2[1]["completed"] = True
        chk_progress_2 = _calculate_checklist_progress(chk_2)
        move_2_date = (now_utc + datetime.timedelta(days=21)).strftime("%Y-%m-%d")

        cursor.execute(
            """
            INSERT OR IGNORE INTO move_logistics_events (
                id, move_number, tenant_id, unit_id, move_type, scheduled_date,
                status, moving_company, mover_contact_phone, coi_status, coi_document_url,
                coi_notes, loading_dock_required, loading_dock_assigned, key_handover_status,
                keys_count, fobs_count, forwarding_address, security_deposit_action,
                inspection_id, notes, checklist_progress_pct, checklist_items_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                move_2_id,
                "MOV-OUT-2026-MARCUS1",
                "tenant_1",
                "unit_101",
                MoveType.MOVE_OUT.value,
                move_2_date,
                MoveStatus.SCHEDULED.value,
                "Metro City Movers Inc.",
                "+1-555-876-2211",
                COIStatus.PENDING.value,
                None,
                "Awaiting updated policy certificate naming property management.",
                1,
                "Dock Bay #1",
                "pending",
                2,
                2,
                "450 Grand Avenue, Apt 14B, Seattle, WA 98101",
                "pending",
                None,
                "Resident relocating for work. Final move-out inspection needed.",
                chk_progress_2,
                json.dumps(chk_2),
                now_iso,
                now_iso,
            ),
        )

    cursor.execute("SELECT COUNT(*) FROM freight_elevator_bookings")
    count_bookings = cursor.fetchone()[0]

    if count_bookings < MIN_SEEDED_ELEVATOR_BOOKINGS:
        cursor.execute(
            """
            INSERT OR IGNORE INTO freight_elevator_bookings (
                id, booking_number, move_id, tenant_id, unit_id, booking_date,
                time_slot, elevator_identifier, status, deposit_collected,
                deposit_amount, padding_installed, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "elv_booking_elena_ph1",
                "ELV-2026-ELENA1",
                "move_elena_ph1",
                "tenant_3",
                "unit_PH1",
                upcoming_move_date,
                ElevatorSlot.SLOT_MORNING_08_12.value,
                "Freight Elevator #1",
                ElevatorBookingStatus.CONFIRMED.value,
                1,
                300.0,
                1,
                "Key locked out on penthouse call for designated moving team.",
                now_iso,
                now_iso,
            ),
        )

        move_2_date = (now_utc + datetime.timedelta(days=21)).strftime("%Y-%m-%d")
        cursor.execute(
            """
            INSERT OR IGNORE INTO freight_elevator_bookings (
                id, booking_number, move_id, tenant_id, unit_id, booking_date,
                time_slot, elevator_identifier, status, deposit_collected,
                deposit_amount, padding_installed, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "elv_booking_marcus_101",
                "ELV-2026-MARCUS1",
                "move_marcus_101",
                "tenant_1",
                "unit_101",
                move_2_date,
                ElevatorSlot.SLOT_AFTERNOON_12_16.value,
                "Freight Elevator #1",
                ElevatorBookingStatus.CONFIRMED.value,
                0,
                250.0,
                1,
                "Afternoon move window. Key to be picked up from front desk.",
                now_iso,
                now_iso,
            ),
        )

    conn.commit()


def create_move_event(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    move_type: str = MoveType.MOVE_IN.value,
    scheduled_date: str = "",
    moving_company: str | None = None,
    mover_contact_phone: str | None = None,
    coi_status: str = COIStatus.PENDING.value,
    coi_document_url: str | None = None,
    loading_dock_required: bool = True,
    loading_dock_assigned: str | None = None,
    keys_count: int = 2,
    fobs_count: int = 2,
    forwarding_address: str | None = None,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a new move-in/move-out logistics event."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_move_logistics_db(conn)
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        if not scheduled_date:
            scheduled_date = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=7)
            ).strftime("%Y-%m-%d")

        move_id = f"move_{secrets.token_hex(6)}"
        move_number = _generate_move_number(move_type)
        checklist = _default_checklist_items(move_type)
        progress_pct = _calculate_checklist_progress(checklist)

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO move_logistics_events (
                id, move_number, tenant_id, unit_id, move_type, scheduled_date,
                status, moving_company, mover_contact_phone, coi_status, coi_document_url,
                loading_dock_required, loading_dock_assigned, keys_count, fobs_count,
                forwarding_address, notes, checklist_progress_pct, checklist_items_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                move_id,
                move_number,
                tenant_id,
                unit_id,
                move_type,
                scheduled_date,
                MoveStatus.SCHEDULED.value,
                moving_company,
                mover_contact_phone,
                coi_status,
                coi_document_url,
                1 if loading_dock_required else 0,
                loading_dock_assigned,
                keys_count,
                fobs_count,
                forwarding_address,
                notes,
                progress_pct,
                json.dumps(checklist),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        return get_move_event(move_id, conn=conn) or {}
    finally:
        if close_conn:
            conn.close()


def get_move_event(move_id: str, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Retrieve a single move logistics event by ID or move number."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_move_logistics_db(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.*, t.name as tenant_name, t.email as tenant_email, u.unit_number, u.building
            FROM move_logistics_events m
            LEFT JOIN tenants t ON m.tenant_id = t.id
            LEFT JOIN units u ON m.unit_id = u.id
            WHERE m.id = ? OR m.move_number = ?
            """,
            (move_id, move_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["checklist_items"] = json.loads(d.get("checklist_items_json", "[]"))
        except Exception:
            d["checklist_items"] = []
        return d
    finally:
        if close_conn:
            conn.close()


def update_move_event(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    move_id: str,
    status: str | None = None,
    scheduled_date: str | None = None,
    moving_company: str | None = None,
    mover_contact_phone: str | None = None,
    coi_status: str | None = None,
    coi_document_url: str | None = None,
    coi_notes: str | None = None,
    loading_dock_assigned: str | None = None,
    key_handover_status: str | None = None,
    forwarding_address: str | None = None,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update fields on an existing move logistics event."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        current = get_move_event(move_id, conn=conn)
        if not current:
            return None

        updates = []
        params = []
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if scheduled_date is not None:
            updates.append("scheduled_date = ?")
            params.append(scheduled_date)
        if moving_company is not None:
            updates.append("moving_company = ?")
            params.append(moving_company)
        if mover_contact_phone is not None:
            updates.append("mover_contact_phone = ?")
            params.append(mover_contact_phone)
        if coi_status is not None:
            updates.append("coi_status = ?")
            params.append(coi_status)
        if coi_document_url is not None:
            updates.append("coi_document_url = ?")
            params.append(coi_document_url)
        if coi_notes is not None:
            updates.append("coi_notes = ?")
            params.append(coi_notes)
        if loading_dock_assigned is not None:
            updates.append("loading_dock_assigned = ?")
            params.append(loading_dock_assigned)
        if key_handover_status is not None:
            updates.append("key_handover_status = ?")
            params.append(key_handover_status)
        if forwarding_address is not None:
            updates.append("forwarding_address = ?")
            params.append(forwarding_address)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)

        if not updates:
            return current

        updates.append("updated_at = ?")
        params.append(now_iso)
        params.append(current["id"])

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE move_logistics_events SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return get_move_event(current["id"], conn=conn)
    finally:
        if close_conn:
            conn.close()


def update_move_checklist_item(
    move_id: str,
    item_id: str,
    completed: bool,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Toggle or set completion of a specific checklist step."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        current = get_move_event(move_id, conn=conn)
        if not current:
            return None

        checklist = current.get("checklist_items", [])
        found = False
        for item in checklist:
            if item.get("id") == item_id:
                item["completed"] = completed
                found = True
                break

        if not found:
            return current

        progress_pct = _calculate_checklist_progress(checklist)
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE move_logistics_events
            SET checklist_items_json = ?, checklist_progress_pct = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(checklist), progress_pct, now_iso, current["id"]),
        )
        conn.commit()
        return get_move_event(current["id"], conn=conn)
    finally:
        if close_conn:
            conn.close()


def list_move_events(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    move_type: str | None = None,
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List move logistics events with optional filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        conn.row_factory = sqlite3.Row
        query = """
            SELECT m.*, t.name as tenant_name, t.email as tenant_email, u.unit_number, u.building
            FROM move_logistics_events m
            LEFT JOIN tenants t ON m.tenant_id = t.id
            LEFT JOIN units u ON m.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []
        if tenant_id:
            query += " AND m.tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND m.unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND m.status = ?"
            params.append(status)
        if move_type:
            query += " AND m.move_type = ?"
            params.append(move_type)

        query += " ORDER BY m.scheduled_date ASC LIMIT ?"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["checklist_items"] = json.loads(d.get("checklist_items_json", "[]"))
            except Exception:
                d["checklist_items"] = []
            result.append(d)
        return result
    finally:
        if close_conn:
            conn.close()


def book_freight_elevator(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    booking_date: str,
    time_slot: str,
    move_id: str | None = None,
    elevator_identifier: str = "Freight Elevator #1",
    deposit_collected: bool = False,
    deposit_amount: float = 250.0,
    padding_installed: bool = True,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Book a freight elevator slot ensuring no double-booking collision."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, booking_number, tenant_id FROM freight_elevator_bookings
            WHERE booking_date = ? AND time_slot = ? AND elevator_identifier = ?
              AND status = 'confirmed'
            """,
            (booking_date, time_slot, elevator_identifier),
        )
        collision = cursor.fetchone()
        if collision:
            raise ValueError(
                f"Elevator slot {time_slot} on {booking_date} for "
                f"{elevator_identifier} is already booked (booking ID: {collision[0]})."
            )

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        booking_id = f"elv_{secrets.token_hex(6)}"
        booking_number = _generate_booking_number()

        cursor.execute(
            """
            INSERT INTO freight_elevator_bookings (
                id, booking_number, move_id, tenant_id, unit_id, booking_date,
                time_slot, elevator_identifier, status, deposit_collected,
                deposit_amount, padding_installed, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                booking_id,
                booking_number,
                move_id,
                tenant_id,
                unit_id,
                booking_date,
                time_slot,
                elevator_identifier,
                ElevatorBookingStatus.CONFIRMED.value,
                1 if deposit_collected else 0,
                deposit_amount,
                1 if padding_installed else 0,
                notes,
                now_iso,
                now_iso,
            ),
        )

        if move_id:
            update_move_checklist_item(move_id, "elevator_reserved", completed=True, conn=conn)

        conn.commit()
        return get_freight_elevator_booking(booking_id, conn=conn) or {}
    finally:
        if close_conn:
            conn.close()


def get_freight_elevator_booking(
    booking_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Get a freight elevator booking by ID or booking number."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT b.*, t.name as tenant_name, t.email as tenant_email, u.unit_number, u.building
            FROM freight_elevator_bookings b
            LEFT JOIN tenants t ON b.tenant_id = t.id
            LEFT JOIN units u ON b.unit_id = u.id
            WHERE b.id = ? OR b.booking_number = ?
            """,
            (booking_id, booking_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if close_conn:
            conn.close()


def list_freight_elevator_bookings(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    booking_date: str | None = None,
    status: str | None = None,
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List freight elevator bookings with optional filtering."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        conn.row_factory = sqlite3.Row
        query = """
            SELECT b.*, t.name as tenant_name, t.email as tenant_email, u.unit_number, u.building
            FROM freight_elevator_bookings b
            LEFT JOIN tenants t ON b.tenant_id = t.id
            LEFT JOIN units u ON b.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []
        if tenant_id:
            query += " AND b.tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND b.unit_id = ?"
            params.append(unit_id)
        if booking_date:
            query += " AND b.booking_date = ?"
            params.append(booking_date)
        if status:
            query += " AND b.status = ?"
            params.append(status)

        query += " ORDER BY b.booking_date ASC LIMIT ?"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        if close_conn:
            conn.close()


def cancel_elevator_booking(
    booking_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Cancel an existing elevator booking."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        current = get_freight_elevator_booking(booking_id, conn=conn)
        if not current:
            return None

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE freight_elevator_bookings SET status = ?, updated_at = ? WHERE id = ?",
            (ElevatorBookingStatus.CANCELLED.value, now_iso, current["id"]),
        )
        conn.commit()
        return get_freight_elevator_booking(current["id"], conn=conn)
    finally:
        if close_conn:
            conn.close()


def get_move_logistics_metrics_summary(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Calculate portfolio-wide move-in/out logistics KPIs and elevator booking stats."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM move_logistics_events")
        total_moves = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM move_logistics_events WHERE status = 'scheduled'")
        scheduled_moves = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM move_logistics_events WHERE status = 'in_progress'")
        in_progress_moves = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM move_logistics_events WHERE status = 'completed'")
        completed_moves = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM move_logistics_events WHERE coi_status = 'pending'")
        pending_cois = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM move_logistics_events WHERE coi_status = 'verified'")
        verified_cois = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM freight_elevator_bookings WHERE status = 'confirmed'")
        active_elevator_bookings = cursor.fetchone()[0]

        cursor.execute(
            "SELECT AVG(checklist_progress_pct) FROM move_logistics_events "
            "WHERE status != 'cancelled'"
        )
        avg_progress = cursor.fetchone()[0] or 0.0

        return {
            "total_moves": total_moves,
            "scheduled_moves": scheduled_moves,
            "in_progress_moves": in_progress_moves,
            "completed_moves": completed_moves,
            "pending_cois": pending_cois,
            "verified_cois": verified_cois,
            "active_elevator_bookings": active_elevator_bookings,
            "avg_checklist_progress_pct": round(float(avg_progress), 1),
        }
    finally:
        if close_conn:
            conn.close()
