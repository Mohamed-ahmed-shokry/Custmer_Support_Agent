"""Tests for Smart Access Control, Key Fobs, and Guest Passes FastAPI Routes."""

from __future__ import annotations

import pytest
from api import access_control, db_utils
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_CREDS_COUNT = 2
MIN_PASSES_COUNT = 1
MIN_INTERCOM_COUNT = 1
TEST_FEE = 50.0
TEST_UPDATED_FEE = 75.0
EXPECTED_CODE_LEN = 6


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_access_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    access_control.init_access_control_db()
    return TestClient(app)


def test_access_metrics_route(client_with_db):
    """Verify GET /access/metrics returns populated portfolio KPIs."""
    response = client_with_db.get("/access/metrics")
    assert response.status_code == HTTP_200
    data = response.json()
    assert data["total_credentials"] >= MIN_CREDS_COUNT
    assert data["active_credentials"] >= 1
    assert data["total_guest_passes"] >= MIN_PASSES_COUNT
    assert data["intercom_directory_count"] >= MIN_INTERCOM_COUNT


def test_access_credentials_crud_routes(client_with_db):
    """Verify full CRUD lifecycle for access credentials via REST API."""
    # 1. Create
    payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "credential_type": "key_fob",
        "credential_number": "FOB-9911",
        "access_level": "all_access",
        "assigned_to_name": "Sarah Chen",
    }
    post_resp = client_with_db.post("/access/credentials", json=payload)
    assert post_resp.status_code == HTTP_201
    created_id = post_resp.json()["credential"]["id"]

    # 2. List
    list_resp = client_with_db.get("/access/credentials?tenant_id=tenant_1")
    assert list_resp.status_code == HTTP_200
    assert any(c["id"] == created_id for c in list_resp.json()["items"])

    # 3. Get single
    get_resp = client_with_db.get(f"/access/credentials/{created_id}")
    assert get_resp.status_code == HTTP_200
    assert get_resp.json()["credential"]["credential_number"] == "FOB-9911"

    # 4. Patch
    patch_resp = client_with_db.patch(
        f"/access/credentials/{created_id}",
        json={"status": "lost", "deactivation_reason": "Lost at gym"},
    )
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["credential"]["status"] == "lost"

    # 5. List tenant credentials
    tenant_creds = client_with_db.get("/tenants/tenant_1/credentials")
    assert tenant_creds.status_code == HTTP_200
    assert len(tenant_creds.json()["items"]) >= 1

    # 6. Delete
    del_resp = client_with_db.delete(f"/access/credentials/{created_id}")
    assert del_resp.status_code == HTTP_200
    assert del_resp.json()["deleted"] is True

    # 7. Get 404
    assert client_with_db.get(f"/access/credentials/{created_id}").status_code == HTTP_404


def test_guest_passes_crud_routes(client_with_db):
    """Verify full CRUD lifecycle for temporary visitor guest passes."""
    # 1. Create
    payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "guest_name": "Instacart Shopper",
        "pass_type": "delivery",
        "max_uses": 1,
        "allowed_zones": ["main_lobby", "elevator", "unit_door"],
    }
    create_resp = client_with_db.post("/access/guest-passes", json=payload)
    assert create_resp.status_code == HTTP_201
    pass_id = create_resp.json()["guest_pass"]["id"]
    assert len(create_resp.json()["guest_pass"]["access_code"]) == EXPECTED_CODE_LEN

    # 2. List
    list_resp = client_with_db.get("/access/guest-passes?tenant_id=tenant_1")
    assert list_resp.status_code == HTTP_200
    assert any(p["id"] == pass_id for p in list_resp.json()["items"])

    # 3. Patch use increment
    patch_resp = client_with_db.patch(
        f"/access/guest-passes/{pass_id}",
        json={"increment_use": True},
    )
    assert patch_resp.status_code == HTTP_200
    # Reached max_uses=1 -> should be used
    assert patch_resp.json()["guest_pass"]["status"] == "used"

    # 4. List tenant passes
    tenant_passes = client_with_db.get("/tenants/tenant_1/guest-passes")
    assert tenant_passes.status_code == HTTP_200
    assert any(p["id"] == pass_id for p in tenant_passes.json()["items"])

    # 5. Delete
    del_resp = client_with_db.delete(f"/access/guest-passes/{pass_id}")
    assert del_resp.status_code == HTTP_200
    assert del_resp.json()["deleted"] is True


def test_intercom_directory_crud_routes(client_with_db):
    """Verify CRUD operations on callbox and intercom directory."""
    payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "display_name": "Chen, S.",
        "directory_code": "101",
        "forwarding_phone": "+1-555-0101",
        "buzzer_enabled": True,
        "allow_video": False,
    }
    create_resp = client_with_db.post("/access/intercom", json=payload)
    assert create_resp.status_code == HTTP_201
    entry_id = create_resp.json()["entry"]["id"]

    list_resp = client_with_db.get("/access/intercom?unit_id=unit_101")
    assert list_resp.status_code == HTTP_200
    assert any(e["id"] == entry_id for e in list_resp.json()["items"])

    patch_resp = client_with_db.patch(
        f"/access/intercom/{entry_id}",
        json={"allow_video": True},
    )
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["entry"]["allow_video"] is True

    del_resp = client_with_db.delete(f"/access/intercom/{entry_id}")
    assert del_resp.status_code == HTTP_200
    assert del_resp.json()["deleted"] is True


def test_session_generate_guest_pass_route(client_with_db):
    """Verify 1-click visitor pass generation auto-resolving tenant from active session."""
    session_id = "session_test_access_01"
    # Link session to tenant_3 (Elena Rostova, unit_PH1)
    link_res = client_with_db.post(
        f"/sessions/{session_id}/link-tenant",
        json={"tenant_id": "tenant_3"},
    )
    assert link_res.status_code == HTTP_200

    payload = {
        "guest_name": "Elena Private Cleaner",
        "pass_type": "visitor",
        "valid_hours": 8,
        "notes": "Cleaning crew access",
    }
    resp = client_with_db.post(f"/sessions/{session_id}/generate-guest-pass", json=payload)
    assert resp.status_code == HTTP_201
    data = resp.json()["guest_pass"]
    assert data["tenant_id"] == "tenant_3"
    assert data["unit_id"] == "unit_PH1"
    assert data["guest_name"] == "Elena Private Cleaner"
    assert len(data["access_code"]) == EXPECTED_CODE_LEN

    # Test unlinked session rejection
    unlinked_resp = client_with_db.post(
        "/sessions/non_existent_session/generate-guest-pass", json=payload
    )
    assert unlinked_resp.status_code == HTTP_400


def test_session_report_lost_fob_route(client_with_db):
    """Verify 1-click lost fob report via active resident session."""
    session_id = "session_test_access_02"
    # Link session to tenant_3
    link_res = client_with_db.post(
        f"/sessions/{session_id}/link-tenant",
        json={"tenant_id": "tenant_3"},
    )
    assert link_res.status_code == HTTP_200

    payload = {
        "credential_id": "cred_elena_01",
        "deactivation_reason": "Lost at airport terminal",
        "charge_replacement_fee": True,
    }
    resp = client_with_db.post(f"/sessions/{session_id}/report-lost-fob", json=payload)
    assert resp.status_code == HTTP_200
    cred = resp.json()["credential"]
    assert cred["id"] == "cred_elena_01"
    assert cred["status"] == "lost"
    assert cred["replacement_fee"] == TEST_FEE

    # Test non-existent credential
    err_resp = client_with_db.post(
        f"/sessions/{session_id}/report-lost-fob",
        json={"credential_id": "non_existent_cred"},
    )
    assert err_resp.status_code == HTTP_404
