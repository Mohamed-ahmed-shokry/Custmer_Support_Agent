"""Maintenance Vendor Directory, Work Order Vendor Dispatch & Vendor Performance Metrics.

Provides a local vendor/contractor directory, dispatch of maintenance work orders
to vendors, job completion with final cost and rating, and vendor metrics.
"""

from __future__ import annotations

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
