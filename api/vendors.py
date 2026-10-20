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
