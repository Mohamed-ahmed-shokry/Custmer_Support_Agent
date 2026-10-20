"""Route tests for the maintenance vendor directory and dispatch endpoints."""

from __future__ import annotations

import pytest
from api import db_utils, main, vendors
from fastapi.testclient import TestClient

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE_ENTITY = 422

client = TestClient(main.app)


@pytest.fixture
def vendor_api(monkeypatch, tmp_path):
    """Point the API at an isolated DB with vendors, work orders and webhooks."""
    monkeypatch.setattr(db_utils, "DB_NAME", str(tmp_path / "vendor_routes.db"))
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_work_orders()
    db_utils.create_webhooks()
    vendors.create_vendors()
    dispatched: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        main.webhooks, "dispatch_event", lambda ev, data: dispatched.append((ev, data))
    )
    return dispatched


def test_create_get_and_list_vendors(vendor_api):
    res = client.post(
        "/vendors",
        json={"id": "vnd_roof", "name": "Rapid Roofers", "trade": "structural", "hourly_rate": 80},
    )
    assert res.status_code == HTTP_CREATED
    assert res.json()["vendor"]["id"] == "vnd_roof"

    assert client.post("/vendors", json={"id": "vnd_roof", "name": "Dup"}).status_code == (
        HTTP_CONFLICT
    )
    assert client.post("/vendors", json={"name": "Bad", "trade": "astrology"}).status_code == (
        HTTP_UNPROCESSABLE_ENTITY
    )

    got = client.get("/vendors/vnd_roof")
    assert got.status_code == HTTP_OK
    assert got.json()["vendor"]["name"] == "Rapid Roofers"
    assert client.get("/vendors/missing").status_code == HTTP_NOT_FOUND

    listing = client.get("/vendors", params={"trade": "structural"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == "vnd_roof"
    assert client.get("/vendors").json()["total"] == 4  # noqa: PLR2004

    metrics = client.get("/vendors/metrics")
    assert metrics.status_code == HTTP_OK
    assert metrics.json()["total_vendors"] == 4  # noqa: PLR2004


def test_update_and_delete_vendor(vendor_api):
    res = client.patch("/vendors/vnd_plumb_01", json={"status": "inactive", "phone": "555-1"})
    assert res.status_code == HTTP_OK
    body = res.json()["vendor"]
    assert body["status"] == "inactive"
    assert body["phone"] == "555-1"
    assert body["trade"] == "plumbing"

    assert client.patch("/vendors/missing", json={"name": "X"}).status_code == HTTP_NOT_FOUND
    assert client.patch("/vendors/vnd_plumb_01", json={"status": "gone"}).status_code == (
        HTTP_UNPROCESSABLE_ENTITY
    )

    deleted = client.delete("/vendors/vnd_plumb_01")
    assert deleted.status_code == HTTP_OK
    assert deleted.json() == {"status": "deleted", "vendor_id": "vnd_plumb_01"}
    assert client.delete("/vendors/vnd_plumb_01").status_code == HTTP_NOT_FOUND


def test_dispatch_vendor_route_lifecycle_start(vendor_api):
    created = client.post(
        "/work-orders",
        json={
            "id": "wo_route_1",
            "unit_id": "unit_101",
            "title": "Leaking faucet",
            "description": "Kitchen faucet drips.",
            "category": "plumbing",
        },
    )
    assert created.status_code == HTTP_CREATED

    res = client.post(
        "/work-orders/wo_route_1/dispatch-vendor",
        json={"vendor_id": "vnd_plumb_01", "agreed_cost": 150, "scheduled_date": "2026-11-03"},
    )
    assert res.status_code == HTTP_CREATED
    dispatch = res.json()["dispatch"]
    assert dispatch["status"] == "dispatched"
    assert dispatch["agreed_cost"] == 150.0  # noqa: PLR2004
    work_order = client.get("/work-orders/wo_route_1").json()["work_order"]
    assert work_order["assigned_to"] == "BlueLine Plumbing"
    assert work_order["status"] == "scheduled"
    assert [e for e, _ in vendor_api if e == "vendor.dispatched"] == ["vendor.dispatched"]
    payload = next(d for e, d in vendor_api if e == "vendor.dispatched")
    assert payload["dispatch_id"] == dispatch["id"]
    assert payload["work_order_id"] == "wo_route_1"

    # second dispatch of the same work order conflicts
    dup = client.post("/work-orders/wo_route_1/dispatch-vendor", json={"vendor_id": "vnd_hvac_01"})
    assert dup.status_code == HTTP_CONFLICT


def test_dispatch_vendor_route_error_statuses(vendor_api):
    missing_wo = client.post(
        "/work-orders/nope/dispatch-vendor", json={"vendor_id": "vnd_plumb_01"}
    )
    assert missing_wo.status_code == HTTP_NOT_FOUND
    missing_vendor = client.post("/work-orders/wo_101/dispatch-vendor", json={"vendor_id": "nope"})
    assert missing_vendor.status_code == HTTP_NOT_FOUND
    closed = client.post("/work-orders/wo_103/dispatch-vendor", json={"vendor_id": "vnd_plumb_01"})
    assert closed.status_code == HTTP_CONFLICT
    invalid = client.post(
        "/work-orders/wo_101/dispatch-vendor", json={"vendor_id": "vnd_plumb_01", "agreed_cost": -1}
    )
    assert invalid.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert not vendor_api


def test_complete_dispatch_route_and_history(vendor_api):
    assert (
        client.post(
            "/work-orders",
            json={
                "id": "wo_route_2",
                "unit_id": "unit_101",
                "title": "Sink",
                "description": "Clogged sink.",
                "category": "plumbing",
            },
        ).status_code
        == HTTP_CREATED
    )
    dispatch = client.post(
        "/work-orders/wo_route_2/dispatch-vendor", json={"vendor_id": "vnd_plumb_01"}
    ).json()["dispatch"]
    vendor_api.clear()

    res = client.post(
        f"/vendor-dispatches/{dispatch['id']}/complete",
        json={"final_cost": 120.5, "rating": 5, "feedback": "Great", "resolution_notes": "Fixed"},
    )
    assert res.status_code == HTTP_OK
    done = res.json()["dispatch"]
    assert done["status"] == "completed"
    assert done["final_cost"] == 120.5  # noqa: PLR2004
    assert done["rating"] == 5  # noqa: PLR2004
    work_order = client.get("/work-orders/wo_route_2").json()["work_order"]
    assert work_order["status"] == "completed"
    assert work_order["actual_cost"] == 120.5  # noqa: PLR2004
    events = [e for e, _ in vendor_api]
    assert "vendor.job_completed" in events
    payload = next(d for e, d in vendor_api if e == "vendor.job_completed")
    assert payload["rating"] == 5  # noqa: PLR2004

    history = client.get("/vendors/vnd_plumb_01/dispatches").json()
    assert history["total"] == 1
    assert history["items"][0]["id"] == dispatch["id"]
    assert (
        client.get("/vendors/vnd_plumb_01/dispatches", params={"status": "dispatched"}).json()[
            "total"
        ]
        == 0
    )
    assert client.get("/vendors/missing/dispatches").status_code == HTTP_NOT_FOUND

    metrics = client.get("/vendors/metrics").json()
    assert metrics["completed_dispatches"] == 1
    assert metrics["total_spend"] == 120.5  # noqa: PLR2004


def test_complete_dispatch_route_errors(vendor_api):
    assert client.post("/vendor-dispatches/nope/complete", json={}).status_code == HTTP_NOT_FOUND
    dispatch = client.post(
        "/work-orders/wo_101/dispatch-vendor", json={"vendor_id": "vnd_plumb_01"}
    ).json()["dispatch"]
    bad_rating = client.post(f"/vendor-dispatches/{dispatch['id']}/complete", json={"rating": 9})
    assert bad_rating.status_code == HTTP_UNPROCESSABLE_ENTITY
    ok = client.post(f"/vendor-dispatches/{dispatch['id']}/complete", json={})
    assert ok.status_code == HTTP_OK
    again = client.post(f"/vendor-dispatches/{dispatch['id']}/complete", json={})
    assert again.status_code == HTTP_CONFLICT
