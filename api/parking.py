"""Parking management, permit passes, and resident vehicle directory database engine.

Tracks property parking spots/stalls, resident vehicle registrations,
visitor parking passes, and parking violation records.
"""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from enum import StrEnum
from typing import Any

from api import db_utils


class SpotType(StrEnum):
    ASSIGNED_RESIDENT = "assigned_resident"
    VISITOR = "visitor"
    EV_CHARGING = "ev_charging"
    HANDICAP = "handicap"
    COMPACT = "compact"
    GENERAL = "general"


class SpotStatus(StrEnum):
    VACANT = "vacant"
    ASSIGNED = "assigned"
    VISITOR_OPEN = "visitor_open"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"


class VisitorPassStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ViolationType(StrEnum):
    UNAUTHORIZED_PARKING = "unauthorized_parking"
    EXPIRED_VISITOR_PASS = "expired_visitor_pass"
    BLOCKING_DRIVEWAY = "blocking_driveway"
    HANDICAP_UNAUTHORIZED = "handicap_unauthorized"
    DOUBLE_PARKED = "double_parked"
    NO_PERMIT = "no_permit"


class ViolationStatus(StrEnum):
    ISSUED = "issued"
    PAID = "paid"
    WARNING = "warning"
    TOWED = "towed"
    DISMISSED = "dismissed"


DEFAULT_PARKING_SPOTS: list[dict[str, Any]] = [
    {
        "id": "spot_101",
        "spot_number": "P-101",
        "zone": "Garage Level 1",
        "spot_type": SpotType.ASSIGNED_RESIDENT.value,
        "unit_id": "unit_101",
        "tenant_id": "tenant_101",
        "status": SpotStatus.ASSIGNED.value,
        "notes": "Assigned to Unit 101 resident",
    },
    {
        "id": "spot_102",
        "spot_number": "P-102",
        "zone": "Garage Level 1",
        "spot_type": SpotType.ASSIGNED_RESIDENT.value,
        "unit_id": "unit_102",
        "tenant_id": "tenant_102",
        "status": SpotStatus.ASSIGNED.value,
        "notes": "Assigned to Unit 102 resident",
    },
    {
        "id": "spot_ev_1",
        "spot_number": "EV-01",
        "zone": "North Lot",
        "spot_type": SpotType.EV_CHARGING.value,
        "unit_id": None,
        "tenant_id": None,
        "status": SpotStatus.VACANT.value,
        "notes": "Level 2 EV fast charger (2-hr limit)",
    },
    {
        "id": "spot_vis_1",
        "spot_number": "V-01",
        "zone": "Visitor Lot",
        "spot_type": SpotType.VISITOR.value,
        "unit_id": None,
        "tenant_id": None,
        "status": SpotStatus.VISITOR_OPEN.value,
        "notes": "Visitor stall, pass required after 8 PM",
    },
    {
        "id": "spot_vis_2",
        "spot_number": "V-02",
        "zone": "Visitor Lot",
        "spot_type": SpotType.VISITOR.value,
        "unit_id": None,
        "tenant_id": None,
        "status": SpotStatus.VISITOR_OPEN.value,
        "notes": "Visitor stall, pass required after 8 PM",
    },
    {
        "id": "spot_hc_1",
        "spot_number": "HC-01",
        "zone": "Main Entrance",
        "spot_type": SpotType.HANDICAP.value,
        "unit_id": None,
        "tenant_id": None,
        "status": SpotStatus.VACANT.value,
        "notes": "Van accessible handicap parking stall",
    },
]


def init_parking_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize parking spots, vehicles, visitor passes, and violations tables."""
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS parking_spots (
                id TEXT PRIMARY KEY,
                spot_number TEXT NOT NULL UNIQUE,
                zone TEXT NOT NULL,
                spot_type TEXT NOT NULL,
                unit_id TEXT,
                tenant_id TEXT,
                status TEXT NOT NULL DEFAULT 'vacant',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_parking_spots_zone ON parking_spots(zone)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_parking_spots_status ON parking_spots(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_parking_spots_unit ON parking_spots(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_parking_spots_tenant ON parking_spots(tenant_id)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS resident_vehicles (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                license_plate TEXT NOT NULL,
                state_province TEXT NOT NULL DEFAULT 'CA',
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                color TEXT,
                year INTEGER,
                permit_number TEXT UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_vehicles_tenant ON resident_vehicles(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_vehicles_unit ON resident_vehicles(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_vehicles_plate ON resident_vehicles(license_plate)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS visitor_parking_passes (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                visitor_name TEXT NOT NULL,
                vehicle_plate TEXT NOT NULL,
                pass_code TEXT NOT NULL UNIQUE,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_vpasses_unit ON visitor_parking_passes(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_vpasses_tenant ON visitor_parking_passes(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_vpasses_status ON visitor_parking_passes(status)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS parking_violations (
                id TEXT PRIMARY KEY,
                spot_id TEXT,
                license_plate TEXT NOT NULL,
                violation_type TEXT NOT NULL,
                fine_amount REAL NOT NULL DEFAULT 50.0,
                status TEXT NOT NULL DEFAULT 'issued',
                vehicle_id TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_violations_plate ON parking_violations(license_plate)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_violations_status ON parking_violations(status)"
        )

        # Seed defaults
        cursor.execute("SELECT COUNT(*) FROM parking_spots")
        count = cursor.fetchone()[0]
        if count == 0:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            for s in DEFAULT_PARKING_SPOTS:
                cursor.execute(
                    """
                    INSERT INTO parking_spots (
                        id, spot_number, zone, spot_type, unit_id, tenant_id,
                        status, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        s["id"],
                        s["spot_number"],
                        s["zone"],
                        s["spot_type"],
                        s["unit_id"],
                        s["tenant_id"],
                        s["status"],
                        s["notes"],
                        now,
                        now,
                    ),
                )
        conn.commit()
    finally:
        if owns_conn:
            conn.close()


def generate_pass_code() -> str:
    """Generate a clean human-readable visitor pass code like VP-78429."""
    digits = "".join(secrets.choice("0123456789") for _ in range(5))
    return f"VP-{digits}"


# ---------------------------------------------------------------------------
# Parking Spots CRUD
# ---------------------------------------------------------------------------


def create_parking_spot(  # noqa: PLR0913, PLR0917
    spot_number: str,
    zone: str,
    spot_type: str = SpotType.ASSIGNED_RESIDENT.value,
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str = SpotStatus.VACANT.value,
    notes: str | None = None,
    spot_id: str | None = None,
) -> dict[str, Any]:
    """Create a new parking stall."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        sid = spot_id or f"spot_{secrets.token_hex(4)}"
        now = datetime.datetime.now(datetime.UTC).isoformat()
        cursor.execute(
            """
            INSERT INTO parking_spots (
                id, spot_number, zone, spot_type, unit_id, tenant_id,
                status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                spot_number.strip().upper(),
                zone.strip(),
                spot_type,
                unit_id,
                tenant_id,
                status,
                notes,
                now,
                now,
            ),
        )
        conn.commit()
        return get_parking_spot(sid) or {}
    finally:
        conn.close()


def get_parking_spot(spot_id: str) -> dict[str, Any] | None:
    """Get parking stall by ID."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM parking_spots WHERE id = ?", (spot_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def list_parking_spots(  # noqa: PLR0913, PLR0917
    zone: str | None = None,
    spot_type: str | None = None,
    status: str | None = None,
    unit_id: str | None = None,
    tenant_id: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List parking spots with optional filters."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM parking_spots WHERE 1=1"
        params: list[Any] = []

        if zone:
            query += " AND zone = ?"
            params.append(zone)
        if spot_type:
            query += " AND spot_type = ?"
            params.append(spot_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if search:
            query += " AND (spot_number LIKE ? OR zone LIKE ? OR notes LIKE ?)"
            s_param = f"%{search}%"
            params.extend([s_param, s_param, s_param])

        query += " ORDER BY zone ASC, spot_number ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def update_parking_spot(  # noqa: PLR0913, PLR0917
    spot_id: str,
    spot_number: str | None = None,
    zone: str | None = None,
    spot_type: str | None = None,
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    notes: str | None = None,
    clear_unit: bool = False,
    clear_tenant: bool = False,
) -> dict[str, Any] | None:
    """Update parking stall details."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        current = get_parking_spot(spot_id)
        if not current:
            return None

        now = datetime.datetime.now(datetime.UTC).isoformat()
        new_spot_number = (
            spot_number.strip().upper() if spot_number is not None else current["spot_number"]
        )
        new_zone = zone.strip() if zone is not None else current["zone"]
        new_spot_type = spot_type if spot_type is not None else current["spot_type"]
        new_status = status if status is not None else current["status"]
        new_notes = notes if notes is not None else current["notes"]

        new_unit_id = None if clear_unit else (
            unit_id if unit_id is not None else current["unit_id"]
        )
        new_tenant_id = None if clear_tenant else (
            tenant_id if tenant_id is not None else current["tenant_id"]
        )

        cursor.execute(
            """
            UPDATE parking_spots
            SET spot_number = ?, zone = ?, spot_type = ?, unit_id = ?, tenant_id = ?,
                status = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_spot_number,
                new_zone,
                new_spot_type,
                new_unit_id,
                new_tenant_id,
                new_status,
                new_notes,
                now,
                spot_id,
            ),
        )
        conn.commit()
        return get_parking_spot(spot_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Resident Vehicles CRUD
# ---------------------------------------------------------------------------


def register_vehicle(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    license_plate: str,
    make: str,
    model: str,
    state_province: str = "CA",
    color: str | None = None,
    year: int | None = None,
    permit_number: str | None = None,
    notes: str | None = None,
    vehicle_id: str | None = None,
) -> dict[str, Any]:
    """Register a resident vehicle."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        clean_plate = license_plate.strip().upper().replace(" ", "")
        vid = vehicle_id or f"veh_{secrets.token_hex(4)}"
        permit = permit_number or f"PERMIT-{secrets.token_hex(3).upper()}"
        now = datetime.datetime.now(datetime.UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO resident_vehicles (
                id, tenant_id, unit_id, license_plate, state_province, make, model,
                color, year, permit_number, is_active, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                vid,
                tenant_id,
                unit_id,
                clean_plate,
                state_province.strip().upper(),
                make.strip(),
                model.strip(),
                color.strip() if color else None,
                year,
                permit,
                notes,
                now,
                now,
            ),
        )
        conn.commit()
        return get_vehicle(vid) or {}
    finally:
        conn.close()


def get_vehicle(vehicle_id: str) -> dict[str, Any] | None:
    """Get vehicle by ID."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM resident_vehicles WHERE id = ?", (vehicle_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def list_vehicles(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    license_plate: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List registered resident vehicles."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM resident_vehicles WHERE 1=1"
        params: list[Any] = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if license_plate:
            query += " AND license_plate = ?"
            params.append(license_plate.strip().upper().replace(" ", ""))
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(1 if is_active else 0)
        if search:
            query += (
                " AND (license_plate LIKE ? OR make LIKE ? "
                "OR model LIKE ? OR permit_number LIKE ?)"
            )
            s_param = f"%{search}%"
            params.extend([s_param, s_param, s_param, s_param])

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def update_vehicle(  # noqa: PLR0913, PLR0917
    vehicle_id: str,
    make: str | None = None,
    model: str | None = None,
    color: str | None = None,
    year: int | None = None,
    permit_number: str | None = None,
    is_active: bool | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update vehicle registration."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        current = get_vehicle(vehicle_id)
        if not current:
            return None

        now = datetime.datetime.now(datetime.UTC).isoformat()
        new_make = make.strip() if make is not None else current["make"]
        new_model = model.strip() if model is not None else current["model"]
        new_color = color.strip() if color is not None else current["color"]
        new_year = year if year is not None else current["year"]
        new_permit = permit_number if permit_number is not None else current["permit_number"]
        new_active = (
            (1 if is_active else 0) if is_active is not None else current["is_active"]
        )
        new_notes = notes if notes is not None else current["notes"]

        cursor.execute(
            """
            UPDATE resident_vehicles
            SET make = ?, model = ?, color = ?, year = ?, permit_number = ?,
                is_active = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_make,
                new_model,
                new_color,
                new_year,
                new_permit,
                new_active,
                new_notes,
                now,
                vehicle_id,
            ),
        )
        conn.commit()
        return get_vehicle(vehicle_id)
    finally:
        conn.close()


def delete_vehicle(vehicle_id: str) -> bool:
    """Delete a vehicle registration."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM resident_vehicles WHERE id = ?", (vehicle_id,))
        conn.commit()
        return bool(cursor.rowcount > 0)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Visitor Parking Passes CRUD
# ---------------------------------------------------------------------------


def issue_visitor_pass(  # noqa: PLR0913, PLR0917
    unit_id: str,
    tenant_id: str,
    visitor_name: str,
    vehicle_plate: str,
    start_time: str,
    end_time: str,
    pass_code: str | None = None,
    notes: str | None = None,
    pass_id: str | None = None,
) -> dict[str, Any]:
    """Issue a visitor parking pass."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        pid = pass_id or f"vpass_{secrets.token_hex(4)}"
        code = pass_code or generate_pass_code()
        now = datetime.datetime.now(datetime.UTC).isoformat()
        clean_plate = vehicle_plate.strip().upper().replace(" ", "")

        cursor.execute(
            """
            INSERT INTO visitor_parking_passes (
                id, unit_id, tenant_id, visitor_name, vehicle_plate, pass_code,
                start_time, end_time, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                pid,
                unit_id,
                tenant_id,
                visitor_name.strip(),
                clean_plate,
                code,
                start_time,
                end_time,
                notes,
                now,
                now,
            ),
        )
        conn.commit()
        return get_visitor_pass(pid) or {}
    finally:
        conn.close()


def get_visitor_pass(pass_id: str) -> dict[str, Any] | None:
    """Get visitor pass by ID or code."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM visitor_parking_passes WHERE id = ? OR pass_code = ?",
            (pass_id, pass_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def list_visitor_passes(  # noqa: PLR0913, PLR0917
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    vehicle_plate: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List visitor parking passes."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM visitor_parking_passes WHERE 1=1"
        params: list[Any] = []

        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if vehicle_plate:
            query += " AND vehicle_plate = ?"
            params.append(vehicle_plate.strip().upper().replace(" ", ""))

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def update_visitor_pass(
    pass_id: str,
    status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update visitor pass status or notes."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        current = get_visitor_pass(pass_id)
        if not current:
            return None

        now = datetime.datetime.now(datetime.UTC).isoformat()
        new_status = status if status is not None else current["status"]
        new_notes = notes if notes is not None else current["notes"]

        cursor.execute(
            """
            UPDATE visitor_parking_passes
            SET status = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, new_notes, now, pass_id),
        )
        conn.commit()
        return get_visitor_pass(pass_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Parking Violations CRUD
# ---------------------------------------------------------------------------


def record_violation(  # noqa: PLR0913, PLR0917
    spot_id: str | None,
    license_plate: str,
    violation_type: str,
    fine_amount: float = 50.0,
    status: str = ViolationStatus.ISSUED.value,
    notes: str | None = None,
    vehicle_id: str | None = None,
    violation_id: str | None = None,
) -> dict[str, Any]:
    """Record a parking violation notice."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        vid = violation_id or f"viol_{secrets.token_hex(4)}"
        clean_plate = license_plate.strip().upper().replace(" ", "")
        now = datetime.datetime.now(datetime.UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO parking_violations (
                id, spot_id, license_plate, violation_type, fine_amount,
                status, vehicle_id, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vid,
                spot_id,
                clean_plate,
                violation_type,
                fine_amount,
                status,
                vehicle_id,
                notes,
                now,
                now,
            ),
        )
        conn.commit()
        return get_violation(vid) or {}
    finally:
        conn.close()


def get_violation(violation_id: str) -> dict[str, Any] | None:
    """Get parking violation by ID."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM parking_violations WHERE id = ?", (violation_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def list_violations(  # noqa: PLR0913, PLR0917
    spot_id: str | None = None,
    license_plate: str | None = None,
    violation_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List recorded parking violations."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM parking_violations WHERE 1=1"
        params: list[Any] = []

        if spot_id:
            query += " AND spot_id = ?"
            params.append(spot_id)
        if license_plate:
            query += " AND license_plate = ?"
            params.append(license_plate.strip().upper().replace(" ", ""))
        if violation_type:
            query += " AND violation_type = ?"
            params.append(violation_type)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def update_violation(
    violation_id: str,
    status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update violation status or notes."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        current = get_violation(violation_id)
        if not current:
            return None

        now = datetime.datetime.now(datetime.UTC).isoformat()
        new_status = status if status is not None else current["status"]
        new_notes = notes if notes is not None else current["notes"]

        cursor.execute(
            """
            UPDATE parking_violations
            SET status = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, new_notes, now, violation_id),
        )
        conn.commit()
        return get_violation(violation_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Parking Summary Metrics
# ---------------------------------------------------------------------------


def get_parking_summary_metrics() -> dict[str, Any]:
    """Calculate aggregate metrics for parking management."""
    init_parking_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()

        # Total spots & by status
        cursor.execute("SELECT COUNT(*) FROM parking_spots")
        total_spots = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT COUNT(*) FROM parking_spots WHERE status = ?",
            (SpotStatus.ASSIGNED.value,),
        )
        assigned_spots = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT COUNT(*) FROM parking_spots WHERE status = ?",
            (SpotStatus.VACANT.value,),
        )
        vacant_spots = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT COUNT(*) FROM parking_spots WHERE spot_type = ?",
            (SpotType.VISITOR.value,),
        )
        visitor_spots = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT COUNT(*) FROM parking_spots WHERE spot_type = ?",
            (SpotType.EV_CHARGING.value,),
        )
        ev_spots = cursor.fetchone()[0] or 0

        # Resident vehicles
        cursor.execute("SELECT COUNT(*) FROM resident_vehicles WHERE is_active = 1")
        active_vehicles = cursor.fetchone()[0] or 0

        # Visitor passes
        cursor.execute(
            "SELECT COUNT(*) FROM visitor_parking_passes WHERE status = ?",
            (VisitorPassStatus.ACTIVE.value,),
        )
        active_visitor_passes = cursor.fetchone()[0] or 0

        # Violations
        cursor.execute(
            "SELECT COUNT(*) FROM parking_violations WHERE status IN ('issued', 'warning')"
        )
        open_violations = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COALESCE(SUM(fine_amount), 0.0) FROM parking_violations")
        total_fines = float(cursor.fetchone()[0] or 0.0)

        occupancy_rate = (
            round((assigned_spots / total_spots) * 100.0, 1) if total_spots > 0 else 0.0
        )

        return {
            "total_spots": total_spots,
            "assigned_spots": assigned_spots,
            "vacant_spots": vacant_spots,
            "visitor_spots": visitor_spots,
            "ev_charging_spots": ev_spots,
            "occupancy_rate_pct": occupancy_rate,
            "active_vehicles_count": active_vehicles,
            "active_visitor_passes": active_visitor_passes,
            "open_violations_count": open_violations,
            "total_fines_assessed": total_fines,
        }
    finally:
        conn.close()
