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
