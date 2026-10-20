"""Maintenance Vendor Directory, Work Order Vendor Dispatch & Vendor Performance Metrics.

Provides a local vendor/contractor directory, dispatch of maintenance work orders
to vendors, job completion with final cost and rating, and vendor metrics.
"""

from __future__ import annotations

from contextlib import closing

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
