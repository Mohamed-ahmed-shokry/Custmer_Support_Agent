"""Route tests for the resident package & parcel delivery locker endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from api import db_utils, main, packages
from fastapi.testclient import TestClient

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

client = TestClient(main.app)


@pytest.fixture
def package_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> list[tuple[str, dict[str, Any]]]:
    """Point the API at an isolated DB with units, tenants, packages, and webhooks."""
    monkeypatch.setattr(db_utils, "DB_NAME", str(tmp_path / "package_routes.db"))
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    db_utils.create_application_logs()
    packages.init_packages()

    dispatched: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        main.webhooks,
        "dispatch_event",
        lambda ev, data: dispatched.append((ev, data)),
    )
    return dispatched


def test_create_package_success(package_api: list[tuple[str, dict[str, Any]]]) -> None:
    res = client.post(
        "/packages",
        json={
            "tenant_id": "tenant_1",
            "unit_id": "unit_101",
            "carrier": "Amazon",
            "tracking_number": "TBA123456789",
            "pickup_pin": "554433",
            "location": "Locker A-05",
            "notes": "Books",
        },
    )
    assert res.status_code == HTTP_CREATED
    data = res.json()["package"]
    assert data["carrier"] == "Amazon"
    assert data["tracking_number"] == "TBA123456789"
    assert data["pickup_pin"] == "554433"
    assert data["location"] == "Locker A-05"
    assert data["status"] == "delivered"

    # Verify webhook fired
    delivered_events = [ev for ev in package_api if ev[0] == "package.delivered"]
    assert len(delivered_events) == 1
    assert delivered_events[0][1]["tracking_number"] == "TBA123456789"


def test_create_package_unknown_tenant_or_unit(
    package_api: list[tuple[str, dict[str, Any]]],
) -> None:
    # Unknown tenant
    res_t = client.post(
        "/packages",
        json={
            "tenant_id": "tnt_nonexistent",
            "unit_id": "unit_101",
            "tracking_number": "TBA1",
        },
    )
    assert res_t.status_code == HTTP_NOT_FOUND

    # Unknown unit
    res_u = client.post(
        "/packages",
        json={
            "tenant_id": "tenant_1",
            "unit_id": "unit_nonexistent",
            "tracking_number": "TBA1",
        },
    )
    assert res_u.status_code == HTTP_NOT_FOUND


def test_get_and_list_packages(package_api: list[tuple[str, dict[str, Any]]]) -> None:
    expected_total = 3
    expected_single = 1

    # List all seeded
    res = client.get("/packages")
    assert res.status_code == HTTP_OK
    body = res.json()
    assert body["total"] == expected_total
    assert len(body["items"]) == expected_total

    # Filter by carrier
    res_fedex = client.get("/packages", params={"carrier": "FedEx"})
    assert res_fedex.status_code == HTTP_OK
    assert res_fedex.json()["total"] == expected_single
    assert res_fedex.json()["items"][0]["carrier"] == "FedEx"

    # Filter by status
    res_picked = client.get("/packages", params={"status": "picked_up"})
    assert res_picked.status_code == HTTP_OK
    assert res_picked.json()["total"] == expected_single

    # Get single
    res_single = client.get("/packages/pkg_seed_01")
    assert res_single.status_code == HTTP_OK
    assert res_single.json()["package"]["id"] == "pkg_seed_01"

    # Get non-existent
    res_none = client.get("/packages/pkg_nonexistent")
    assert res_none.status_code == HTTP_NOT_FOUND


def test_update_and_delete_package(package_api: list[tuple[str, dict[str, Any]]]) -> None:
    # Patch
    res_patch = client.patch(
        "/packages/pkg_seed_01",
        json={"location": "Front Desk Shelf C", "notes": "Moved from locker"},
    )
    assert res_patch.status_code == HTTP_OK
    assert res_patch.json()["package"]["location"] == "Front Desk Shelf C"

    # Patch non-existent
    res_patch_none = client.patch(
        "/packages/pkg_nonexistent",
        json={"location": "Desk"},
    )
    assert res_patch_none.status_code == HTTP_NOT_FOUND

    # Delete
    res_del = client.delete("/packages/pkg_seed_01")
    assert res_del.status_code == HTTP_OK
    assert res_del.json()["status"] == "deleted"

    # Delete non-existent
    res_del_none = client.delete("/packages/pkg_seed_01")
    assert res_del_none.status_code == HTTP_NOT_FOUND


def test_pickup_package_flow(package_api: list[tuple[str, dict[str, Any]]]) -> None:
    # Success pickup with valid PIN
    res = client.post(
        "/packages/pkg_seed_01/pickup",
        json={"pickup_pin": "482019"},
    )
    assert res.status_code == HTTP_OK
    data = res.json()["package"]
    assert data["status"] == "picked_up"
    assert data["picked_up_at"] is not None

    # Verify webhook fired
    picked_events = [ev for ev in package_api if ev[0] == "package.picked_up"]
    assert len(picked_events) == 1
    assert picked_events[0][1]["package_id"] == "pkg_seed_01"

    # Double pickup attempt should fail
    res_double = client.post(
        "/packages/pkg_seed_01/pickup",
        json={"pickup_pin": "482019"},
    )
    assert res_double.status_code == HTTP_BAD_REQUEST

    # Invalid PIN attempt
    res_wrong_pin = client.post(
        "/packages/pkg_seed_02/pickup",
        json={"pickup_pin": "000000"},
    )
    assert res_wrong_pin.status_code == HTTP_BAD_REQUEST

    # Non-existent package
    res_not_found = client.post(
        "/packages/pkg_nonexistent/pickup",
        json={"pickup_pin": "123456"},
    )
    assert res_not_found.status_code == HTTP_NOT_FOUND


def test_get_package_metrics(package_api: list[tuple[str, dict[str, Any]]]) -> None:
    expected_total = 3
    expected_delivered = 2
    expected_picked_up = 1

    res = client.get("/packages/metrics")
    assert res.status_code == HTTP_OK
    metrics = res.json()
    assert metrics["total_packages"] == expected_total
    assert metrics["delivered_packages"] == expected_delivered
    assert metrics["picked_up_packages"] == expected_picked_up
    assert "Amazon" in metrics["carrier_breakdown"]


def test_list_tenant_packages_route(package_api: list[tuple[str, dict[str, Any]]]) -> None:
    expected_sarah_total = 2
    expected_sarah_pending = 1

    res = client.get("/tenants/tenant_1/packages")
    assert res.status_code == HTTP_OK
    assert res.json()["total"] == expected_sarah_total

    # Filter pending only
    res_pending = client.get("/tenants/tenant_1/packages", params={"pending_only": True})
    assert res_pending.status_code == HTTP_OK
    assert res_pending.json()["total"] == expected_sarah_pending
    assert res_pending.json()["items"][0]["status"] == "delivered"

    # Unknown tenant
    res_unknown = client.get("/tenants/tnt_nonexistent/packages")
    assert res_unknown.status_code == HTTP_NOT_FOUND


def test_session_intake_package_route(package_api: list[tuple[str, dict[str, Any]]]) -> None:
    session_id = "sess_delivery_test"

    # Unlinked session -> 400
    res_unlinked = client.post(
        f"/sessions/{session_id}/intake-package",
        json={
            "carrier": "UPS",
            "tracking_number": "1Z888888",
            "location": "Locker Bay 1 - Slot 09",
        },
    )
    assert res_unlinked.status_code == HTTP_BAD_REQUEST

    # Link tenant to session
    db_utils.link_session_tenant(session_id, "tenant_1")

    # Success intake
    res_linked = client.post(
        f"/sessions/{session_id}/intake-package",
        json={
            "carrier": "UPS",
            "tracking_number": "1Z888888",
            "location": "Locker Bay 1 - Slot 09",
        },
    )
    assert res_linked.status_code == HTTP_CREATED
    pkg = res_linked.json()["package"]
    assert pkg["tenant_id"] == "tenant_1"
    assert pkg["unit_id"] == "unit_101"
    assert pkg["carrier"] == "UPS"
    assert pkg["tracking_number"] == "1Z888888"
