"""Maintenance Vendor Directory, Work Order Vendor Dispatch & Vendor Performance Metrics.

Provides a local vendor/contractor directory, dispatch of maintenance work orders
to vendors, job completion with final cost and rating, and vendor metrics.
"""

from __future__ import annotations

import re
import uuid
from contextlib import closing
from datetime import UTC, datetime
from typing import Any

from api import db_utils

VALID_VENDOR_STATUSES = {"active", "inactive", "blacklisted"}
DEFAULT_VENDOR_STATUS = "active"

VALID_DISPATCH_STATUSES = {"dispatched", "completed", "cancelled"}
DEFAULT_DISPATCH_STATUS = "dispatched"

MAX_VENDOR_ID_LENGTH = 50
MAX_VENDOR_NAME_LENGTH = 150
MAX_VENDOR_CONTACT_LENGTH = 150
MAX_VENDOR_NOTES_LENGTH = 2000
MIN_RATING = 1
MAX_RATING = 5

_CREATE_VENDORS_TABLE = (
    "CREATE TABLE IF NOT EXISTS vendors ("
    "id TEXT PRIMARY KEY, "
    "name TEXT NOT NULL, "
    "trade TEXT NOT NULL DEFAULT 'general', "
    "contact_name TEXT NOT NULL DEFAULT '', "
    "email TEXT NOT NULL DEFAULT '', "
    "phone TEXT NOT NULL DEFAULT '', "
    "hourly_rate REAL DEFAULT NULL, "
    "status TEXT NOT NULL DEFAULT 'active', "
    "notes TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_VENDORS_TRADE_INDEX = "CREATE INDEX IF NOT EXISTS idx_vendors_trade ON vendors(trade)"
_CREATE_VENDOR_DISPATCHES_TABLE = (
    "CREATE TABLE IF NOT EXISTS vendor_dispatches ("
    "id TEXT PRIMARY KEY, "
    "vendor_id TEXT NOT NULL REFERENCES vendors(id) ON DELETE CASCADE, "
    "work_order_id TEXT NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE, "
    "status TEXT NOT NULL DEFAULT 'dispatched', "
    "agreed_cost REAL DEFAULT NULL, "
    "final_cost REAL DEFAULT NULL, "
    "rating INTEGER DEFAULT NULL, "
    "feedback TEXT NOT NULL DEFAULT '', "
    "dispatched_at TEXT NOT NULL, "
    "completed_at TEXT DEFAULT NULL)"
)
_CREATE_VENDOR_DISPATCHES_VENDOR_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_vendor_dispatches_vendor_id ON vendor_dispatches(vendor_id)"
)
_CREATE_VENDOR_DISPATCHES_WO_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_vendor_dispatches_work_order_id "
    "ON vendor_dispatches(work_order_id)"
)

DEFAULT_SEEDED_VENDORS = [
    {
        "id": "vnd_plumb_01",
        "name": "BlueLine Plumbing",
        "trade": "plumbing",
        "contact_name": "Dana Ortiz",
        "email": "dispatch@blueline.example.com",
        "phone": "555-0140",
        "hourly_rate": 95.0,
        "status": "active",
        "notes": "24/7 emergency leak response.",
    },
    {
        "id": "vnd_hvac_01",
        "name": "CoolBreeze HVAC",
        "trade": "hvac",
        "contact_name": "Sam Whitfield",
        "email": "service@coolbreeze.example.com",
        "phone": "555-0141",
        "hourly_rate": 110.0,
        "status": "active",
        "notes": "Seasonal maintenance contract.",
    },
    {
        "id": "vnd_elec_01",
        "name": "BrightSpark Electric",
        "trade": "electrical",
        "contact_name": "Priya Nair",
        "email": "jobs@brightspark.example.com",
        "phone": "555-0142",
        "hourly_rate": 105.0,
        "status": "active",
        "notes": "Licensed for panel upgrades.",
    },
]


def create_vendors() -> None:
    """Create vendor tables and indexes, and pre-seed sample vendors if the table is empty."""
    with closing(db_utils.get_db_connection()) as conn:
        conn.execute(_CREATE_VENDORS_TABLE)
        conn.execute(_CREATE_VENDORS_TRADE_INDEX)
        conn.execute(_CREATE_VENDOR_DISPATCHES_TABLE)
        conn.execute(_CREATE_VENDOR_DISPATCHES_VENDOR_INDEX)
        conn.execute(_CREATE_VENDOR_DISPATCHES_WO_INDEX)
        row = conn.execute("SELECT COUNT(*) FROM vendors").fetchone()
        if row and row[0] == 0:
            for v in DEFAULT_SEEDED_VENDORS:
                conn.execute(
                    "INSERT INTO vendors "
                    "(id, name, trade, contact_name, email, phone, hourly_rate, status, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        v["id"],
                        v["name"],
                        v["trade"],
                        v["contact_name"],
                        v["email"],
                        v["phone"],
                        v["hourly_rate"],
                        v["status"],
                        v["notes"],
                    ),
                )
        conn.commit()


def normalize_vendor_id(value: str | None) -> str:
    """Validate and clean a vendor ID."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Vendor ID must not be blank.")
    if len(cleaned) > MAX_VENDOR_ID_LENGTH:
        raise ValueError(f"Vendor ID must be at most {MAX_VENDOR_ID_LENGTH} characters.")
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", cleaned):
        raise ValueError(
            "Vendor ID may only contain alphanumeric characters, underscores, hyphens, and periods."
        )
    return cleaned


def normalize_vendor_name(value: str | None) -> str:
    """Validate and clean a vendor display name."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Vendor name must not be blank.")
    if len(cleaned) > MAX_VENDOR_NAME_LENGTH:
        raise ValueError(f"Vendor name must be at most {MAX_VENDOR_NAME_LENGTH} characters.")
    return cleaned


def normalize_vendor_trade(value: str | None) -> str:
    """Validate a vendor trade against the work order categories."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return db_utils.DEFAULT_WORK_ORDER_CATEGORY
    if cleaned not in db_utils.VALID_WORK_ORDER_CATEGORIES:
        valid = ", ".join(sorted(db_utils.VALID_WORK_ORDER_CATEGORIES))
        raise ValueError(f"Invalid vendor trade '{cleaned}'. Expected one of: {valid}.")
    return cleaned


def normalize_vendor_status(value: str | None) -> str:
    """Validate a vendor status."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT_VENDOR_STATUS
    if cleaned not in VALID_VENDOR_STATUSES:
        valid = ", ".join(sorted(VALID_VENDOR_STATUSES))
        raise ValueError(f"Invalid vendor status '{cleaned}'. Expected one of: {valid}.")
    return cleaned


def _clean_text(value: str | None, label: str, max_length: int) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) > max_length:
        raise ValueError(f"{label} must be at most {max_length} characters.")
    return cleaned


def _clean_rate(value: float | None) -> float | None:
    if value is None:
        return None
    rate = float(value)
    if rate < 0:
        raise ValueError("Hourly rate must not be negative.")
    return rate


def get_vendor(vendor_id: str) -> dict[str, Any] | None:
    """Fetch a vendor by ID, or None when it does not exist."""
    cleaned_id = (vendor_id or "").strip()
    if not cleaned_id:
        return None
    with closing(db_utils.get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM vendors WHERE id = ?", (cleaned_id,)).fetchone()
        return dict(row) if row else None


def create_vendor(  # noqa: PLR0913
    name: str,
    *,
    trade: str = "general",
    contact_name: str = "",
    email: str = "",
    phone: str = "",
    hourly_rate: float | None = None,
    status: str = "active",
    notes: str = "",
    vendor_id: str | None = None,
) -> dict[str, Any]:
    """Create a vendor, generating a `vnd_` ID when none is supplied."""
    norm_id = normalize_vendor_id(vendor_id or f"vnd_{uuid.uuid4().hex[:8]}")
    values = (
        norm_id,
        normalize_vendor_name(name),
        normalize_vendor_trade(trade),
        _clean_text(contact_name, "Contact name", MAX_VENDOR_CONTACT_LENGTH),
        _clean_text(email, "Email", MAX_VENDOR_CONTACT_LENGTH),
        _clean_text(phone, "Phone", MAX_VENDOR_CONTACT_LENGTH),
        _clean_rate(hourly_rate),
        normalize_vendor_status(status),
        _clean_text(notes, "Notes", MAX_VENDOR_NOTES_LENGTH),
    )
    with closing(db_utils.get_db_connection()) as conn:
        if conn.execute("SELECT id FROM vendors WHERE id = ?", (norm_id,)).fetchone():
            raise ValueError(f"Vendor with ID '{norm_id}' already exists.")
        conn.execute(
            "INSERT INTO vendors "
            "(id, name, trade, contact_name, email, phone, hourly_rate, status, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        conn.commit()
    created = get_vendor(norm_id)
    if created is None:
        raise RuntimeError("Failed to retrieve created vendor.")
    return created


def list_vendors(  # noqa: PLR0913
    *,
    trade: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List vendors with optional trade/status/search filters; returns (items, total)."""
    where: list[str] = []
    params: list[Any] = []
    if trade and trade.strip():
        where.append("trade = ?")
        params.append(trade.strip().lower())
    if status and status.strip():
        where.append("status = ?")
        params.append(status.strip().lower())
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        where.append("(LOWER(name) LIKE ? OR LOWER(contact_name) LIKE ? OR LOWER(notes) LIKE ?)")
        params.extend([pattern, pattern, pattern])
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with closing(db_utils.get_db_connection()) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM vendors{clause}", params).fetchone()[0])
        rows = conn.execute(
            f"SELECT * FROM vendors{clause} ORDER BY name ASC LIMIT ? OFFSET ?",  # noqa: S608
            [*params, max(1, limit), max(0, offset)],
        ).fetchall()
    return [dict(r) for r in rows], total


def update_vendor(  # noqa: PLR0913
    vendor_id: str,
    *,
    name: str | None = None,
    trade: str | None = None,
    contact_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    hourly_rate: float | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update the supplied fields of a vendor; returns None when it does not exist."""
    current = get_vendor(vendor_id)
    if not current:
        return None
    values = (
        normalize_vendor_name(name) if name is not None else current["name"],
        normalize_vendor_trade(trade) if trade is not None else current["trade"],
        (
            _clean_text(contact_name, "Contact name", MAX_VENDOR_CONTACT_LENGTH)
            if contact_name is not None
            else current["contact_name"]
        ),
        _clean_text(email, "Email", MAX_VENDOR_CONTACT_LENGTH)
        if email is not None
        else current["email"],
        _clean_text(phone, "Phone", MAX_VENDOR_CONTACT_LENGTH)
        if phone is not None
        else current["phone"],
        _clean_rate(hourly_rate) if hourly_rate is not None else current["hourly_rate"],
        normalize_vendor_status(status) if status is not None else current["status"],
        _clean_text(notes, "Notes", MAX_VENDOR_NOTES_LENGTH)
        if notes is not None
        else current["notes"],
        current["id"],
    )
    with closing(db_utils.get_db_connection()) as conn:
        conn.execute(
            "UPDATE vendors SET name = ?, trade = ?, contact_name = ?, email = ?, phone = ?, "
            "hourly_rate = ?, status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            values,
        )
        conn.commit()
    return get_vendor(current["id"])


def delete_vendor(vendor_id: str) -> bool:
    """Delete a vendor (and its dispatch history); returns True when a row was removed."""
    cleaned_id = (vendor_id or "").strip()
    with closing(db_utils.get_db_connection()) as conn:
        conn.execute("DELETE FROM vendor_dispatches WHERE vendor_id = ?", (cleaned_id,))
        cursor = conn.execute("DELETE FROM vendors WHERE id = ?", (cleaned_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def get_dispatch(dispatch_id: str) -> dict[str, Any] | None:
    """Fetch a vendor dispatch by ID, or None when it does not exist."""
    cleaned_id = (dispatch_id or "").strip()
    if not cleaned_id:
        return None
    with closing(db_utils.get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM vendor_dispatches WHERE id = ?", (cleaned_id,)).fetchone()
        return dict(row) if row else None


def dispatch_vendor(
    work_order_id: str,
    vendor_id: str,
    *,
    agreed_cost: float | None = None,
    scheduled_date: str | None = None,
) -> dict[str, Any]:
    """Dispatch an open work order to an active vendor.

    Sets the work order's `assigned_to` to the vendor name, moves a `submitted` work order
    to `scheduled`, and records an active dispatch. Raises ValueError (with "not found" in the
    message for unknown records) when the dispatch is not allowed.
    """
    vendor = get_vendor(vendor_id)
    if not vendor:
        raise ValueError(f"Vendor '{vendor_id}' not found.")
    if vendor["status"] != "active":
        raise ValueError(f"Vendor '{vendor['id']}' is {vendor['status']} and cannot be dispatched.")
    work_order = db_utils.get_work_order(work_order_id)
    if not work_order:
        raise ValueError(f"Work order '{work_order_id}' not found.")
    if work_order["status"] in {"completed", "cancelled"}:
        raise ValueError(
            f"Work order '{work_order['id']}' is {work_order['status']} and cannot be dispatched."
        )
    cost = _clean_rate(agreed_cost)
    dispatch_id = f"vdp_{uuid.uuid4().hex[:8]}"
    with closing(db_utils.get_db_connection()) as conn:
        active = conn.execute(
            "SELECT id FROM vendor_dispatches WHERE work_order_id = ? AND status = 'dispatched'",
            (work_order["id"],),
        ).fetchone()
        if active:
            raise ValueError(
                f"Work order '{work_order['id']}' already has an active dispatch '{active['id']}'."
            )
        conn.execute(
            "INSERT INTO vendor_dispatches "
            "(id, vendor_id, work_order_id, status, agreed_cost, dispatched_at) "
            "VALUES (?, ?, ?, 'dispatched', ?, ?)",
            (dispatch_id, vendor["id"], work_order["id"], cost, datetime.now(UTC).isoformat()),
        )
        conn.commit()
    db_utils.update_work_order(
        work_order["id"],
        assigned_to=vendor["name"],
        status="scheduled" if work_order["status"] == "submitted" else None,
        scheduled_date=scheduled_date,
        estimated_cost=cost,
    )
    created = get_dispatch(dispatch_id)
    if created is None:
        raise RuntimeError("Failed to retrieve created dispatch.")
    return created
