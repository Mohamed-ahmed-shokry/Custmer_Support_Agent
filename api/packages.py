"""Resident Package & Parcel Delivery Locker Management Engine.

Provides package intake logging, secure pickup PIN verification, carrier tracking,
delivery metrics, and parcel locker operations.
"""

from __future__ import annotations

import secrets
from contextlib import closing
from datetime import UTC, datetime
from typing import Any

from api import db_utils

VALID_CARRIERS = {"Amazon", "UPS", "FedEx", "USPS", "DHL", "OnTrac", "Other"}
DEFAULT_CARRIER = "Amazon"

VALID_PACKAGE_STATUSES = {"delivered", "picked_up", "returned", "expired"}
DEFAULT_PACKAGE_STATUS = "delivered"

MAX_CARRIER_LENGTH = 50
MAX_TRACKING_LENGTH = 100
MAX_LOCATION_LENGTH = 100
MAX_NOTES_LENGTH = 2000
PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8

_CREATE_PACKAGES_TABLE = (
    "CREATE TABLE IF NOT EXISTS packages ("
    "id TEXT PRIMARY KEY, "
    "tenant_id TEXT NOT NULL, "
    "unit_id TEXT NOT NULL, "
    "carrier TEXT NOT NULL DEFAULT 'Amazon', "
    "tracking_number TEXT NOT NULL, "
    "pickup_pin TEXT NOT NULL, "
    "location TEXT NOT NULL DEFAULT 'Locker Room', "
    "status TEXT NOT NULL DEFAULT 'delivered', "
    "delivered_at TEXT NOT NULL, "
    "picked_up_at TEXT DEFAULT NULL, "
    "notes TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_PACKAGES_TENANT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_packages_tenant_id ON packages(tenant_id)"
)
_CREATE_PACKAGES_UNIT_INDEX = "CREATE INDEX IF NOT EXISTS idx_packages_unit_id ON packages(unit_id)"
_CREATE_PACKAGES_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_packages_status ON packages(status)"
)
_CREATE_PACKAGES_TRACKING_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_packages_tracking ON packages(tracking_number)"
)

DEFAULT_SEEDED_PACKAGES: list[dict[str, Any]] = [
    {
        "id": "pkg_seed_01",
        "tenant_id": "tnt_sarah_01",
        "unit_id": "unit_101",
        "carrier": "Amazon",
        "tracking_number": "TBA309481029104",
        "pickup_pin": "482019",
        "location": "Locker Bay 1 - Slot 04",
        "status": "delivered",
        "delivered_at": "2026-10-28T14:30:00Z",
        "picked_up_at": None,
        "notes": "Small parcel (apparel).",
    },
    {
        "id": "pkg_seed_02",
        "tenant_id": "tnt_marcus_02",
        "unit_id": "unit_204",
        "carrier": "FedEx",
        "tracking_number": "9274890284710293",
        "pickup_pin": "719302",
        "location": "Locker Bay 2 - Slot 11",
        "status": "delivered",
        "delivered_at": "2026-10-28T16:15:00Z",
        "picked_up_at": None,
        "notes": "Medium box (electronics).",
    },
    {
        "id": "pkg_seed_03",
        "tenant_id": "tnt_sarah_01",
        "unit_id": "unit_101",
        "carrier": "UPS",
        "tracking_number": "1Z9999999999999999",
        "pickup_pin": "104928",
        "location": "Front Desk Shelf A",
        "status": "picked_up",
        "delivered_at": "2026-10-26T10:00:00Z",
        "picked_up_at": "2026-10-26T17:30:00Z",
        "notes": "Overnight delivery signed at desk.",
    },
]


def generate_pickup_pin(length: int = 6) -> str:
    """Generate a cryptographically secure numeric pickup PIN of specified length."""
    if length < PIN_MIN_LENGTH or length > PIN_MAX_LENGTH:
        length = 6
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def init_packages() -> None:
    """Create packages tables and indexes, and pre-seed sample packages if empty."""
    with closing(db_utils.get_db_connection()) as conn:
        conn.execute(_CREATE_PACKAGES_TABLE)
        conn.execute(_CREATE_PACKAGES_TENANT_INDEX)
        conn.execute(_CREATE_PACKAGES_UNIT_INDEX)
        conn.execute(_CREATE_PACKAGES_STATUS_INDEX)
        conn.execute(_CREATE_PACKAGES_TRACKING_INDEX)
        conn.commit()

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM packages")
        count = cursor.fetchone()[0]
        if count == 0:
            now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            for pkg in DEFAULT_SEEDED_PACKAGES:
                cursor.execute(
                    """
                    INSERT INTO packages (
                        id, tenant_id, unit_id, carrier, tracking_number,
                        pickup_pin, location, status, delivered_at, picked_up_at,
                        notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pkg["id"],
                        pkg["tenant_id"],
                        pkg["unit_id"],
                        pkg["carrier"],
                        pkg["tracking_number"],
                        pkg["pickup_pin"],
                        pkg["location"],
                        pkg["status"],
                        pkg["delivered_at"],
                        pkg["picked_up_at"],
                        pkg["notes"],
                        now_iso,
                        now_iso,
                    ),
                )
            conn.commit()


def create_package(  # noqa: PLR0913
    *,
    tenant_id: str,
    unit_id: str,
    carrier: str = DEFAULT_CARRIER,
    tracking_number: str,
    pickup_pin: str | None = None,
    location: str = "Locker Bay 1",
    notes: str = "",
    delivered_at: str | None = None,
) -> dict[str, Any]:
    """Create a new package record with validated carrier, location, and secure PIN."""
    init_packages()

    clean_tenant_id = (tenant_id or "").strip()
    clean_unit_id = (unit_id or "").strip()
    if not clean_tenant_id:
        raise ValueError("tenant_id is required")
    if not clean_unit_id:
        raise ValueError("unit_id is required")

    carrier_title = carrier.strip() if carrier else DEFAULT_CARRIER
    matched_carrier = None
    for valid_c in VALID_CARRIERS:
        if valid_c.lower() == carrier_title.lower():
            matched_carrier = valid_c
            break
    if not matched_carrier:
        matched_carrier = "Other"

    clean_tracking = (tracking_number or "").strip()
    if not clean_tracking:
        raise ValueError("tracking_number is required")
    if len(clean_tracking) > MAX_TRACKING_LENGTH:
        clean_tracking = clean_tracking[:MAX_TRACKING_LENGTH]

    clean_location = (location or "Locker Bay 1").strip()
    if len(clean_location) > MAX_LOCATION_LENGTH:
        clean_location = clean_location[:MAX_LOCATION_LENGTH]

    clean_notes = (notes or "").strip()
    if len(clean_notes) > MAX_NOTES_LENGTH:
        clean_notes = clean_notes[:MAX_NOTES_LENGTH]

    pin_is_valid = (
        pickup_pin is not None
        and pickup_pin.strip().isdigit()
        and PIN_MIN_LENGTH <= len(pickup_pin.strip()) <= PIN_MAX_LENGTH
    )
    final_pin = pickup_pin.strip() if pin_is_valid and pickup_pin else generate_pickup_pin()

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    final_delivered_at = delivered_at.strip() if delivered_at and delivered_at.strip() else now_iso

    pkg_id = f"pkg_{secrets.token_hex(6)}"

    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO packages (
                id, tenant_id, unit_id, carrier, tracking_number,
                pickup_pin, location, status, delivered_at, picked_up_at,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pkg_id,
                clean_tenant_id,
                clean_unit_id,
                matched_carrier,
                clean_tracking,
                final_pin,
                clean_location,
                DEFAULT_PACKAGE_STATUS,
                final_delivered_at,
                None,
                clean_notes,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

    pkg = get_package(pkg_id)
    if not pkg:
        raise RuntimeError("Failed to retrieve created package")
    return pkg


def get_package(package_id: str) -> dict[str, Any] | None:
    """Retrieve a single package by its ID."""
    init_packages()
    with closing(db_utils.get_db_connection()) as conn:
        conn.row_factory = db_utils.sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM packages WHERE id = ?", (package_id.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_packages(  # noqa: PLR0913
    *,
    tenant_id: str | None = None,
    unit_id: str | None = None,
    carrier: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List packages filtered by resident, unit, carrier, status, or search query."""
    init_packages()
    query = "SELECT * FROM packages WHERE 1=1"
    params: list[Any] = []

    if tenant_id and tenant_id.strip():
        query += " AND tenant_id = ?"
        params.append(tenant_id.strip())
    if unit_id and unit_id.strip():
        query += " AND unit_id = ?"
        params.append(unit_id.strip())
    if carrier and carrier.strip():
        query += " AND LOWER(carrier) = LOWER(?)"
        params.append(carrier.strip())
    if status and status.strip():
        query += " AND LOWER(status) = LOWER(?)"
        params.append(status.strip())
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        query += (
            " AND (LOWER(tracking_number) LIKE ? OR LOWER(location) LIKE ? OR LOWER(notes) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    query += " ORDER BY delivered_at DESC LIMIT ? OFFSET ?"
    params.extend([max(1, limit), max(0, offset)])

    with closing(db_utils.get_db_connection()) as conn:
        conn.row_factory = db_utils.sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]


def count_packages(
    *,
    tenant_id: str | None = None,
    unit_id: str | None = None,
    carrier: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> int:
    """Count packages matching the given filters."""
    init_packages()
    query = "SELECT COUNT(*) FROM packages WHERE 1=1"
    params: list[Any] = []

    if tenant_id and tenant_id.strip():
        query += " AND tenant_id = ?"
        params.append(tenant_id.strip())
    if unit_id and unit_id.strip():
        query += " AND unit_id = ?"
        params.append(unit_id.strip())
    if carrier and carrier.strip():
        query += " AND LOWER(carrier) = LOWER(?)"
        params.append(carrier.strip())
    if status and status.strip():
        query += " AND LOWER(status) = LOWER(?)"
        params.append(status.strip())
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        query += (
            " AND (LOWER(tracking_number) LIKE ? OR LOWER(location) LIKE ? OR LOWER(notes) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return int(cursor.fetchone()[0])


def update_package(
    package_id: str,
    *,
    location: str | None = None,
    notes: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    """Update location, notes, or status for an existing package."""
    init_packages()
    existing = get_package(package_id)
    if not existing:
        return None

    updates: list[str] = []
    params: list[Any] = []

    if location is not None:
        clean_loc = location.strip()[:MAX_LOCATION_LENGTH]
        updates.append("location = ?")
        params.append(clean_loc)

    if notes is not None:
        clean_notes = notes.strip()[:MAX_NOTES_LENGTH]
        updates.append("notes = ?")
        params.append(clean_notes)

    if status is not None:
        clean_status = status.strip().lower()
        if clean_status in VALID_PACKAGE_STATUSES:
            updates.append("status = ?")
            params.append(clean_status)

    if not updates:
        return existing

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    updates.append("updated_at = ?")
    params.append(now_iso)

    params.append(package_id.strip())
    query = f"UPDATE packages SET {', '.join(updates)} WHERE id = ?"

    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

    return get_package(package_id)


def pickup_package(
    package_id: str,
    pickup_pin: str,
    *,
    picked_up_at: str | None = None,
) -> dict[str, Any]:
    """Verify pickup PIN and transition package to picked_up status."""
    init_packages()
    existing = get_package(package_id)
    if not existing:
        raise ValueError(f"Package not found: {package_id}")

    if existing["status"] == "picked_up":
        raise ValueError("Package has already been picked up")
    if existing["status"] != "delivered":
        raise ValueError(f"Package cannot be picked up with status: {existing['status']}")

    cleaned_pin = (pickup_pin or "").strip()
    if cleaned_pin != existing["pickup_pin"]:
        raise ValueError("Invalid pickup PIN")

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    final_picked_up_at = picked_up_at.strip() if picked_up_at and picked_up_at.strip() else now_iso

    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE packages
            SET status = 'picked_up',
                picked_up_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (final_picked_up_at, now_iso, package_id.strip()),
        )
        conn.commit()

    updated = get_package(package_id)
    if not updated:
        raise RuntimeError("Failed to retrieve updated package after pickup")
    return updated


def delete_package(package_id: str) -> bool:
    """Delete a package record from the database."""
    init_packages()
    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM packages WHERE id = ?", (package_id.strip(),))
        conn.commit()
        return bool(cursor.rowcount > 0)


def list_tenant_packages(
    tenant_id: str,
    *,
    pending_only: bool = False,
) -> list[dict[str, Any]]:
    """Retrieve all packages for a resident, optionally filtering to pending deliveries."""
    status_filter = "delivered" if pending_only else None
    return list_packages(tenant_id=tenant_id, status=status_filter, limit=100)


def _process_package_rows(
    rows: list[Any],
) -> tuple[dict[str, int], list[float], float, dict[str, int]]:
    """Helper to process package rows for status counts, carrier breakdown, and durations."""
    status_counts = {"delivered": 0, "picked_up": 0, "returned": 0, "expired": 0}
    carrier_breakdown: dict[str, int] = {}
    pickup_durations_hours: list[float] = []
    oldest_pending_hours = 0.0
    now_dt = datetime.now(UTC)

    for r in rows:
        st, cr, del_at_str, pu_at_str = r[0], r[1], r[2], r[3]
        carrier_breakdown[cr] = carrier_breakdown.get(cr, 0) + 1

        if st in status_counts:
            status_counts[st] += 1

        if st == "delivered" and del_at_str:
            try:
                cleaned_del = del_at_str.replace("Z", "+00:00")
                del_dt = datetime.fromisoformat(cleaned_del)
                if del_dt.tzinfo is None:
                    del_dt = del_dt.replace(tzinfo=UTC)
                age_hours = (now_dt - del_dt).total_seconds() / 3600.0
                oldest_pending_hours = max(oldest_pending_hours, age_hours)
            except Exception:
                pass
        elif st == "picked_up" and del_at_str and pu_at_str:
            try:
                cleaned_del = del_at_str.replace("Z", "+00:00")
                cleaned_pu = pu_at_str.replace("Z", "+00:00")
                del_dt = datetime.fromisoformat(cleaned_del)
                pu_dt = datetime.fromisoformat(cleaned_pu)
                if del_dt.tzinfo is None:
                    del_dt = del_dt.replace(tzinfo=UTC)
                if pu_dt.tzinfo is None:
                    pu_dt = pu_dt.replace(tzinfo=UTC)
                diff_hours = (pu_dt - del_dt).total_seconds() / 3600.0
                if diff_hours >= 0:
                    pickup_durations_hours.append(diff_hours)
            except Exception:
                pass

    return status_counts, pickup_durations_hours, oldest_pending_hours, carrier_breakdown


def get_package_summary_metrics() -> dict[str, Any]:
    """Calculate portfolio package intake, locker occupancy, and turnaround metrics."""
    init_packages()
    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, carrier, delivered_at, picked_up_at FROM packages")
        rows = cursor.fetchall()

    status_counts, pickup_durations_hours, oldest_pending_hours, carrier_breakdown = (
        _process_package_rows(rows)
    )

    average_pickup_hours = (
        round(sum(pickup_durations_hours) / len(pickup_durations_hours), 1)
        if pickup_durations_hours
        else 0.0
    )

    return {
        "total_packages": len(rows),
        "delivered_packages": status_counts["delivered"],
        "picked_up_packages": status_counts["picked_up"],
        "returned_packages": status_counts["returned"],
        "expired_packages": status_counts["expired"],
        "carrier_breakdown": carrier_breakdown,
        "average_pickup_hours": average_pickup_hours,
        "oldest_pending_hours": round(oldest_pending_hours, 1),
    }
