"""Tests for the maintenance vendor directory and work order dispatch engine."""

from __future__ import annotations

from contextlib import closing

import pytest
from api import db_utils, vendors


@pytest.fixture
def vendor_db(monkeypatch, tmp_path):
    """Isolated SQLite DB with units, tenants, work orders and vendor tables."""
    monkeypatch.setattr(db_utils, "DB_NAME", str(tmp_path / "vendors.db"))
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_work_orders()
    vendors.create_vendors()
    return tmp_path


def test_create_vendors_seeds_defaults_idempotently(vendor_db):
    vendors.create_vendors()
    with closing(db_utils.get_db_connection()) as conn:
        rows = conn.execute("SELECT id FROM vendors ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == ["vnd_elec_01", "vnd_hvac_01", "vnd_plumb_01"]
