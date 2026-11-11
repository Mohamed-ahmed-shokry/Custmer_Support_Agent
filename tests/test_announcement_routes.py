"""Tests for Community Announcements, Emergency Alerts & Concierge FastAPI Routes."""

from __future__ import annotations

import pytest
from api import announcements, db_utils
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_ANNOUNCEMENTS_COUNT = 2
MIN_CONCIERGE_COUNT = 1
MIN_ACKS_COUNT = 2


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_announcement_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    announcements.init_announcements_db()
    return TestClient(app)


def test_announcements_metrics_route(client_with_db):
    """Verify GET /announcements/metrics returns aggregate portfolio broadcast counts."""
    response = client_with_db.get("/announcements/metrics")
    assert response.status_code == HTTP_200
    data = response.json()
    assert data["total_announcements"] >= MIN_ANNOUNCEMENTS_COUNT
    assert data["active_emergency_alerts"] >= 1
    assert data["total_concierge_requests"] >= MIN_CONCIERGE_COUNT


def test_announcements_crud_routes(client_with_db):
    """Test full CRUD lifecycle for community announcements via REST API."""
    # 1. Create announcement
    payload = {
        "title": "Courtyard BBQ Grill Cleaning",
        "content": "Outdoor community grills will be serviced on Thursday morning.",
        "category": "amenity_update",
        "priority": "normal",
        "scope": "portfolio_wide",
        "author_name": "Property Operations",
        "is_pinned": True,
        "require_acknowledgment": False,
    }
    create_res = client_with_db.post("/announcements", json=payload)
    assert create_res.status_code == HTTP_201
    created = create_res.json()["announcement"]
    ann_id = created["id"]
    assert created["title"] == "Courtyard BBQ Grill Cleaning"
    assert created["is_pinned"] is True

    # 2. Get announcement
    get_res = client_with_db.get(f"/announcements/{ann_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["announcement"]["id"] == ann_id

    # 3. List announcements with filter
    list_res = client_with_db.get("/announcements?category=amenity_update")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1

    # 4. Patch announcement
    patch_res = client_with_db.patch(
        f"/announcements/{ann_id}",
        json={"title": "Courtyard BBQ Grill Cleaning (Completed)", "status": "archived"},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["announcement"]["status"] == "archived"

    # 5. Delete announcement
    del_res = client_with_db.delete(f"/announcements/{ann_id}")
    assert del_res.status_code == HTTP_200

    # 6. Verify 404
    assert client_with_db.get(f"/announcements/{ann_id}").status_code == HTTP_404


def test_announcement_acknowledgments_routes(client_with_db):
    """Test recording and listing resident acknowledgments via API."""
    # Seed emergency alert is EMG-2026-005 (id ann_seed_02)
    ann_id = "ann_seed_02"

    ack_payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "channel": "chat_session",
        "notes": "Confirmed pipes protected.",
    }
    ack_res = client_with_db.post(
        f"/announcements/{ann_id}/acknowledge", json=ack_payload
    )
    assert ack_res.status_code == HTTP_201
    ack = ack_res.json()["acknowledgment"]
    assert ack["announcement_id"] == ann_id
    assert ack["tenant_id"] == "tenant_1"

    # List acknowledgments
    list_res = client_with_db.get(f"/announcements/{ann_id}/acknowledgments")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= MIN_ACKS_COUNT


def test_tenant_announcements_route(client_with_db):
    """Test GET /tenants/{tenant_id}/announcements returns resident-specific notices."""
    res = client_with_db.get("/tenants/tenant_3/announcements")
    assert res.status_code == HTTP_200
    data = res.json()
    assert data["total"] >= MIN_ANNOUNCEMENTS_COUNT
    item_titles = [i["title"] for i in data["items"]]
    assert any("Elevator" in t for t in item_titles)


def test_concierge_crud_routes(client_with_db):
    """Test full CRUD lifecycle for resident concierge requests via REST API."""
    payload = {
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "request_type": "key_checkout",
        "priority": "normal",
        "instructions": "Leave spare fob in lockbox for cleaning crew.",
        "assigned_staff": "Concierge Marcus",
    }
    create_res = client_with_db.post("/concierge", json=payload)
    assert create_res.status_code == HTTP_201
    created = create_res.json()["concierge_request"]
    req_id = created["id"]
    assert created["request_type"] == "key_checkout"

    # Get
    get_res = client_with_db.get(f"/concierge/{req_id}")
    assert get_res.status_code == HTTP_200

    # List
    list_res = client_with_db.get("/concierge?status=submitted")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1

    # Update
    patch_res = client_with_db.patch(
        f"/concierge/{req_id}",
        json={"status": "fulfilled", "fulfillment_notes": "Spare key returned and logged."},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["concierge_request"]["status"] == "fulfilled"

    # List tenant concierge
    tenant_res = client_with_db.get("/tenants/tenant_3/concierge")
    assert tenant_res.status_code == HTTP_200
    assert tenant_res.json()["total"] >= MIN_ACKS_COUNT

    # Delete
    del_res = client_with_db.delete(f"/concierge/{req_id}")
    assert del_res.status_code == HTTP_200


def test_session_1click_alert_and_concierge_actions(client_with_db):
    """Test 1-click alert acknowledgment and concierge request from active chat session."""
    session_id = "sess_ann_test_99"

    # Link session to Elena Rostova (tenant_3, unit_PH1)
    link_res = client_with_db.post(
        f"/sessions/{session_id}/link-tenant",
        json={"tenant_id": "tenant_3"},
    )
    assert link_res.status_code == HTTP_200

    # 1. 1-click Acknowledge Alert
    ack_res = client_with_db.post(
        f"/sessions/{session_id}/acknowledge-alert",
        json={"announcement_id": "ann_seed_01", "notes": "Acknowledged from chat interface"},
    )
    assert ack_res.status_code == HTTP_201
    ack_data = ack_res.json()["acknowledgment"]
    assert ack_data["announcement_id"] == "ann_seed_01"
    assert ack_data["tenant_id"] == "tenant_3"

    # 2. 1-click Request Concierge
    con_res = client_with_db.post(
        f"/sessions/{session_id}/request-concierge",
        json={
            "request_type": "package_hold",
            "priority": "urgent",
            "instructions": "Hold perishable organic produce delivery at reception.",
        },
    )
    assert con_res.status_code == HTTP_201
    con_data = con_res.json()["concierge_request"]
    assert con_data["request_type"] == "package_hold"
    assert con_data["tenant_id"] == "tenant_3"
    assert con_data["unit_id"] == "unit_PH1"
