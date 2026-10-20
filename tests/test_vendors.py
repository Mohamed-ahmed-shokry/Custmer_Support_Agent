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


def test_delete_vendor(vendor_db):
    assert vendors.delete_vendor("vnd_elec_01") is True
    assert vendors.get_vendor("vnd_elec_01") is None
    assert vendors.delete_vendor("vnd_elec_01") is False


def test_get_dispatch_returns_none_for_unknown_or_blank(vendor_db):
    assert vendors.get_dispatch("vdp_missing") is None
    assert vendors.get_dispatch(" ") is None


def _make_work_order(work_order_id: str = "wo_test_1", status: str = "submitted") -> dict:
    return db_utils.create_work_order(
        work_order_id=work_order_id,
        unit_id="unit_101",
        title="Leaking faucet",
        description="Kitchen faucet drips constantly.",
        category="plumbing",
        status=status,
    )


def test_dispatch_vendor_assigns_and_schedules_work_order(vendor_db):
    _make_work_order()
    dispatch = vendors.dispatch_vendor(
        "wo_test_1", "vnd_plumb_01", agreed_cost=150, scheduled_date="2026-11-03"
    )
    assert dispatch["id"].startswith("vdp_")
    assert dispatch["status"] == "dispatched"
    assert dispatch["agreed_cost"] == 150.0  # noqa: PLR2004
    work_order = db_utils.get_work_order("wo_test_1")
    assert work_order is not None
    assert work_order["assigned_to"] == "BlueLine Plumbing"
    assert work_order["status"] == "scheduled"
    assert work_order["scheduled_date"] == "2026-11-03"
    assert work_order["estimated_cost"] == 150.0  # noqa: PLR2004


def test_dispatch_vendor_keeps_in_progress_status(vendor_db):
    dispatch = vendors.dispatch_vendor("wo_102", "vnd_hvac_01")
    assert dispatch["agreed_cost"] is None
    work_order = db_utils.get_work_order("wo_102")
    assert work_order is not None
    assert work_order["status"] == "in_progress"
    assert work_order["assigned_to"] == "CoolBreeze HVAC"


def test_dispatch_vendor_rejections(vendor_db):
    _make_work_order()
    with pytest.raises(ValueError, match="Vendor 'nope' not found"):
        vendors.dispatch_vendor("wo_test_1", "nope")
    with pytest.raises(ValueError, match="Work order 'nope' not found"):
        vendors.dispatch_vendor("nope", "vnd_plumb_01")
    with pytest.raises(ValueError, match="is completed and cannot"):
        vendors.dispatch_vendor("wo_103", "vnd_plumb_01")
    vendors.update_vendor("vnd_elec_01", status="blacklisted")
    with pytest.raises(ValueError, match="is blacklisted and cannot"):
        vendors.dispatch_vendor("wo_test_1", "vnd_elec_01")
    with pytest.raises(ValueError, match="must not be negative"):
        vendors.dispatch_vendor("wo_test_1", "vnd_plumb_01", agreed_cost=-5)

    vendors.dispatch_vendor("wo_test_1", "vnd_plumb_01")
    with pytest.raises(ValueError, match="already has an active dispatch"):
        vendors.dispatch_vendor("wo_test_1", "vnd_hvac_01")


def test_complete_dispatch_records_cost_rating_and_closes_work_order(vendor_db):
    _make_work_order()
    dispatch = vendors.dispatch_vendor("wo_test_1", "vnd_plumb_01", agreed_cost=150)
    completed = vendors.complete_dispatch(
        dispatch["id"],
        final_cost=140.5,
        rating=5,
        feedback="Fast and tidy.",
        resolution_notes="Replaced cartridge.",
    )
    assert completed["status"] == "completed"
    assert completed["final_cost"] == 140.5  # noqa: PLR2004
    assert completed["rating"] == 5  # noqa: PLR2004
    assert completed["feedback"] == "Fast and tidy."
    assert completed["completed_at"]
    work_order = db_utils.get_work_order("wo_test_1")
    assert work_order is not None
    assert work_order["status"] == "completed"
    assert work_order["actual_cost"] == 140.5  # noqa: PLR2004
    assert work_order["resolution_notes"] == "Replaced cartridge."

    with pytest.raises(ValueError, match="is completed and cannot be completed"):
        vendors.complete_dispatch(dispatch["id"])


def test_complete_dispatch_validation(vendor_db):
    _make_work_order()
    dispatch = vendors.dispatch_vendor("wo_test_1", "vnd_plumb_01")
    with pytest.raises(ValueError, match="Dispatch 'nope' not found"):
        vendors.complete_dispatch("nope")
    with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
        vendors.complete_dispatch(dispatch["id"], rating=6)
    with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
        vendors.complete_dispatch(dispatch["id"], rating=0)
    with pytest.raises(ValueError, match="must not be negative"):
        vendors.complete_dispatch(dispatch["id"], final_cost=-1)
    # failed attempts leave the dispatch active
    still_active = vendors.get_dispatch(dispatch["id"])
    assert still_active is not None
    assert still_active["status"] == "dispatched"


def test_list_dispatches_filters(vendor_db):
    _make_work_order()
    first = vendors.dispatch_vendor("wo_test_1", "vnd_plumb_01")
    second = vendors.dispatch_vendor("wo_102", "vnd_hvac_01")
    vendors.complete_dispatch(second["id"], final_cost=99, rating=4)

    items, total = vendors.list_dispatches()
    assert total == 2  # noqa: PLR2004
    assert {d["id"] for d in items} == {first["id"], second["id"]}

    items, total = vendors.list_dispatches(vendor_id="vnd_plumb_01")
    assert [d["id"] for d in items] == [first["id"]]
    items, total = vendors.list_dispatches(work_order_id="wo_102")
    assert [d["id"] for d in items] == [second["id"]]
    items, total = vendors.list_dispatches(status="Completed")
    assert [d["id"] for d in items] == [second["id"]]
    items, total = vendors.list_dispatches(limit=1, offset=1)
    assert total == 2  # noqa: PLR2004
    assert len(items) == 1
