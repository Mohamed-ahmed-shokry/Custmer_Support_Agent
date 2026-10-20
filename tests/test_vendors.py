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


def test_normalize_vendor_validators():
    assert vendors.normalize_vendor_id("  vnd_1 ") == "vnd_1"
    with pytest.raises(ValueError, match="blank"):
        vendors.normalize_vendor_id("  ")
    with pytest.raises(ValueError, match="at most"):
        vendors.normalize_vendor_id("a" * 51)
    with pytest.raises(ValueError, match="alphanumeric"):
        vendors.normalize_vendor_id("bad id!")
    assert vendors.normalize_vendor_name(" Acme ") == "Acme"
    with pytest.raises(ValueError, match="blank"):
        vendors.normalize_vendor_name("")
    with pytest.raises(ValueError, match="at most"):
        vendors.normalize_vendor_name("n" * 151)
    assert vendors.normalize_vendor_trade(" HVAC ") == "hvac"
    assert vendors.normalize_vendor_trade(None) == "general"
    with pytest.raises(ValueError, match="Invalid vendor trade"):
        vendors.normalize_vendor_trade("astrology")
    assert vendors.normalize_vendor_status("") == "active"
    assert vendors.normalize_vendor_status("Inactive") == "inactive"
    with pytest.raises(ValueError, match="Invalid vendor status"):
        vendors.normalize_vendor_status("retired")


def test_create_and_get_vendor(vendor_db):
    created = vendors.create_vendor(
        name=" Rapid Roofers ",
        trade="structural",
        phone="555-0199",
        hourly_rate=80,
        vendor_id="vnd_roof",
    )
    assert created["id"] == "vnd_roof"
    assert created["name"] == "Rapid Roofers"
    assert created["trade"] == "structural"
    assert created["hourly_rate"] == 80.0  # noqa: PLR2004
    assert created["status"] == "active"
    assert vendors.get_vendor("vnd_roof") == created
    assert vendors.get_vendor("missing") is None
    assert vendors.get_vendor("  ") is None

    generated = vendors.create_vendor(name="Auto ID Co")
    assert generated["id"].startswith("vnd_")


def test_create_vendor_rejects_invalid_input(vendor_db):
    with pytest.raises(ValueError, match="already exists"):
        vendors.create_vendor(name="Dup", vendor_id="vnd_plumb_01")
    with pytest.raises(ValueError, match="must not be negative"):
        vendors.create_vendor(name="Neg", hourly_rate=-1)
    with pytest.raises(ValueError, match="Notes must be at most"):
        vendors.create_vendor(name="Long", notes="x" * 2001)
    with pytest.raises(ValueError, match="blank"):
        vendors.create_vendor(name=" ")


def test_list_vendors_filters_and_pagination(vendor_db):
    items, total = vendors.list_vendors()
    assert total == 3  # noqa: PLR2004
    assert [v["name"] for v in items] == [
        "BlueLine Plumbing",
        "BrightSpark Electric",
        "CoolBreeze HVAC",
    ]

    items, total = vendors.list_vendors(trade="HVAC")
    assert total == 1
    assert items[0]["id"] == "vnd_hvac_01"

    items, total = vendors.list_vendors(search="priya")
    assert [v["id"] for v in items] == ["vnd_elec_01"]

    items, total = vendors.list_vendors(status="inactive")
    assert (items, total) == ([], 0)

    items, total = vendors.list_vendors(limit=1, offset=1)
    assert total == 3  # noqa: PLR2004
    assert [v["id"] for v in items] == ["vnd_elec_01"]


def test_update_vendor(vendor_db):
    updated = vendors.update_vendor(
        "vnd_plumb_01",
        name="BlueLine Plumbing & Drain",
        status="inactive",
        hourly_rate=100,
        phone="555-0000",
    )
    assert updated is not None
    assert updated["name"] == "BlueLine Plumbing & Drain"
    assert updated["status"] == "inactive"
    assert updated["hourly_rate"] == 100.0  # noqa: PLR2004
    assert updated["phone"] == "555-0000"
    assert updated["trade"] == "plumbing"  # untouched fields are preserved

    assert vendors.update_vendor("missing", name="X") is None
    with pytest.raises(ValueError, match="Invalid vendor status"):
        vendors.update_vendor("vnd_plumb_01", status="gone")
