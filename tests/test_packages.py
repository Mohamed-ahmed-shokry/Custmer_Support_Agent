"""Unit tests for the packages database engine and parcel locker metrics."""

from __future__ import annotations

from pathlib import Path

import pytest
from api import db_utils, packages


@pytest.fixture
def package_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Create an isolated temporary SQLite database for testing."""
    test_db = tmp_path / "test_packages.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    packages.init_packages()
    return tmp_path


def test_generate_pickup_pin() -> None:
    expected_default_len = 6
    pin6 = packages.generate_pickup_pin(expected_default_len)
    assert len(pin6) == expected_default_len
    assert pin6.isdigit()

    expected_custom_len = 4
    pin4 = packages.generate_pickup_pin(expected_custom_len)
    assert len(pin4) == expected_custom_len
    assert pin4.isdigit()

    # Out of bounds fallback to 6
    pin_invalid = packages.generate_pickup_pin(20)
    assert len(pin_invalid) == expected_default_len


def test_init_packages_seeds_data(package_db: Path) -> None:
    expected_seed_count = 3
    pkgs = packages.list_packages()
    assert len(pkgs) == expected_seed_count
    # Check seeded contents
    ids = {p["id"] for p in pkgs}
    assert "pkg_seed_01" in ids
    assert "pkg_seed_02" in ids
    assert "pkg_seed_03" in ids

    # Second call is idempotent
    packages.init_packages()
    assert packages.count_packages() == expected_seed_count


def test_create_package_success(package_db: Path) -> None:
    pkg = packages.create_package(
        tenant_id="tnt_john_01",
        unit_id="unit_303",
        carrier="FedEx",
        tracking_number="FX-123456789",
        pickup_pin="998877",
        location="Locker Bay 3 - Slot 08",
        notes="Fragile glass",
    )
    assert pkg["id"].startswith("pkg_")
    assert pkg["tenant_id"] == "tnt_john_01"
    assert pkg["unit_id"] == "unit_303"
    assert pkg["carrier"] == "FedEx"
    assert pkg["tracking_number"] == "FX-123456789"
    assert pkg["pickup_pin"] == "998877"
    assert pkg["location"] == "Locker Bay 3 - Slot 08"
    assert pkg["status"] == "delivered"
    assert pkg["notes"] == "Fragile glass"
    assert pkg["delivered_at"] is not None
    assert pkg["picked_up_at"] is None


def test_create_package_auto_pin_and_carrier_fallback(package_db: Path) -> None:
    expected_pin_len = 6
    pkg = packages.create_package(
        tenant_id="tnt_alex_02",
        unit_id="unit_105",
        carrier="UnknownCarrier99",
        tracking_number="TRACK-999",
    )
    assert len(pkg["pickup_pin"]) == expected_pin_len
    assert pkg["pickup_pin"].isdigit()
    assert pkg["carrier"] == "Other"


def test_create_package_validation_errors(package_db: Path) -> None:
    with pytest.raises(ValueError, match="tenant_id is required"):
        packages.create_package(tenant_id="", unit_id="u1", tracking_number="T1")

    with pytest.raises(ValueError, match="unit_id is required"):
        packages.create_package(tenant_id="t1", unit_id="", tracking_number="T1")

    with pytest.raises(ValueError, match="tracking_number is required"):
        packages.create_package(tenant_id="t1", unit_id="u1", tracking_number="  ")


def test_get_package(package_db: Path) -> None:
    pkg = packages.get_package("pkg_seed_01")
    assert pkg is not None
    assert pkg["id"] == "pkg_seed_01"
    assert pkg["carrier"] == "Amazon"

    non_existent = packages.get_package("pkg_nonexistent")
    assert non_existent is None


def test_list_and_count_packages_filters(package_db: Path) -> None:
    expected_seed_count = 3
    expected_sarah_count = 2
    expected_fedex_count = 1
    expected_delivered_count = 2
    expected_picked_up_count = 1

    # Total seeded
    assert packages.count_packages() == expected_seed_count

    # Filter by tenant
    sarah_pkgs = packages.list_packages(tenant_id="tnt_sarah_01")
    assert len(sarah_pkgs) == expected_sarah_count
    assert packages.count_packages(tenant_id="tnt_sarah_01") == expected_sarah_count

    # Filter by unit
    u101_pkgs = packages.list_packages(unit_id="unit_101")
    assert len(u101_pkgs) == expected_sarah_count

    # Filter by carrier
    fedex_pkgs = packages.list_packages(carrier="FedEx")
    assert len(fedex_pkgs) == expected_fedex_count
    assert fedex_pkgs[0]["id"] == "pkg_seed_02"

    # Filter by status
    delivered = packages.list_packages(status="delivered")
    assert len(delivered) == expected_delivered_count
    picked_up = packages.list_packages(status="picked_up")
    assert len(picked_up) == expected_picked_up_count

    # Search filter
    search_res = packages.list_packages(search="apparel")
    assert len(search_res) == 1
    assert search_res[0]["id"] == "pkg_seed_01"

    # Limit and offset
    paged = packages.list_packages(limit=1, offset=1)
    assert len(paged) == 1


def test_update_package(package_db: Path) -> None:
    updated = packages.update_package(
        "pkg_seed_01",
        location="Locker Bay 1 - Slot 99",
        notes="Updated notes",
        status="delivered",
    )
    assert updated is not None
    assert updated["location"] == "Locker Bay 1 - Slot 99"
    assert updated["notes"] == "Updated notes"

    non_existent = packages.update_package("pkg_unknown", notes="foo")
    assert non_existent is None


def test_pickup_package_success(package_db: Path) -> None:
    pkg = packages.get_package("pkg_seed_01")
    assert pkg is not None
    pin = pkg["pickup_pin"]

    picked = packages.pickup_package("pkg_seed_01", pin, picked_up_at="2026-10-29T10:00:00Z")
    assert picked["status"] == "picked_up"
    assert picked["picked_up_at"] == "2026-10-29T10:00:00Z"

    # Verify persisted in DB
    refetched = packages.get_package("pkg_seed_01")
    assert refetched is not None
    assert refetched["status"] == "picked_up"


def test_pickup_package_invalid_pin(package_db: Path) -> None:
    with pytest.raises(ValueError, match="Invalid pickup PIN"):
        packages.pickup_package("pkg_seed_01", "000000")


def test_pickup_package_errors(package_db: Path) -> None:
    # Already picked up
    with pytest.raises(ValueError, match="Package has already been picked up"):
        packages.pickup_package("pkg_seed_03", "104928")

    # Non-existent
    with pytest.raises(ValueError, match="Package not found"):
        packages.pickup_package("pkg_nonexistent", "123456")

    # Returned status
    packages.update_package("pkg_seed_01", status="returned")
    with pytest.raises(ValueError, match="Package cannot be picked up with status: returned"):
        packages.pickup_package("pkg_seed_01", "482019")


def test_delete_package(package_db: Path) -> None:
    assert packages.delete_package("pkg_seed_01") is True
    assert packages.get_package("pkg_seed_01") is None
    assert packages.delete_package("pkg_seed_01") is False


def test_list_tenant_packages(package_db: Path) -> None:
    expected_all_count = 2
    expected_pending_count = 1
    all_sarah = packages.list_tenant_packages("tnt_sarah_01", pending_only=False)
    assert len(all_sarah) == expected_all_count

    pending_sarah = packages.list_tenant_packages("tnt_sarah_01", pending_only=True)
    assert len(pending_sarah) == expected_pending_count
    assert pending_sarah[0]["id"] == "pkg_seed_01"


def test_get_package_summary_metrics(package_db: Path) -> None:
    expected_total = 3
    expected_delivered = 2
    expected_picked_up = 1
    expected_zero = 0

    metrics = packages.get_package_summary_metrics()
    assert metrics["total_packages"] == expected_total
    assert metrics["delivered_packages"] == expected_delivered
    assert metrics["picked_up_packages"] == expected_picked_up
    assert metrics["returned_packages"] == expected_zero
    assert metrics["expired_packages"] == expected_zero
    assert "Amazon" in metrics["carrier_breakdown"]
    assert "FedEx" in metrics["carrier_breakdown"]
    assert "UPS" in metrics["carrier_breakdown"]
    assert metrics["average_pickup_hours"] >= 0.0
