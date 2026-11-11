"""Tests for Community Incidents, Violation Notices & Appeals FastAPI Routes."""

from __future__ import annotations

import pytest
from api import db_utils, incidents
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_INCIDENTS_COUNT = 1
MIN_VIOLATIONS_COUNT = 1
MIN_APPEALS_COUNT = 1
TEST_FINE = 50.0
TEST_FINE_100 = 100.0
TEST_REDUCED_FINE = 25.0


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_incident_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    incidents.init_incidents_db()
    return TestClient(app)


def test_incident_metrics_route(client_with_db):
    """Verify GET /incidents/metrics returns populated portfolio KPIs."""
    response = client_with_db.get("/incidents/metrics")
    assert response.status_code == HTTP_200
    data = response.json()
    assert data["total_incidents"] >= MIN_INCIDENTS_COUNT
    assert data["total_violations"] >= MIN_VIOLATIONS_COUNT
    assert data["total_appeals"] >= MIN_APPEALS_COUNT


def test_incidents_crud_routes(client_with_db):
    """Verify incident creation, retrieval, filtering, updating, and deletion."""
    # 1. Create incident
    payload = {
        "incident_type": "smoking_prohibited",
        "description": "Cigarette smoke odor detected near hallway elevator.",
        "severity": "medium",
        "unit_id": "unit_101",
        "tenant_id": "tenant_1",
        "reported_by": "staff",
        "location": "Level 1 Elevator Lobby",
    }
    create_resp = client_with_db.post("/incidents", json=payload)
    assert create_resp.status_code == HTTP_201
    inc_data = create_resp.json()["incident"]
    inc_id = inc_data["id"]
    assert inc_data["incident_type"] == "smoking_prohibited"

    # 2. Get incident by id
    get_resp = client_with_db.get(f"/incidents/{inc_id}")
    assert get_resp.status_code == HTTP_200
    assert get_resp.json()["incident"]["id"] == inc_id

    # 3. List incidents with filters
    list_resp = client_with_db.get("/incidents?severity=medium")
    assert list_resp.status_code == HTTP_200
    assert list_resp.json()["total"] >= 1

    # 4. Update incident
    patch_resp = client_with_db.patch(
        f"/incidents/{inc_id}",
        json={
            "status": "resolved",
            "resolution_notes": "Resident advised of no-smoking building policy.",
        },
    )
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["incident"]["status"] == "resolved"

    # 5. Get tenant incidents
    tenant_resp = client_with_db.get("/tenants/tenant_1/incidents")
    assert tenant_resp.status_code == HTTP_200
    assert len(tenant_resp.json()["items"]) >= 1

    # 6. Delete incident
    del_resp = client_with_db.delete(f"/incidents/{inc_id}")
    assert del_resp.status_code == HTTP_200
    assert del_resp.json()["status"] == "deleted"

    # 7. Verify 404
    assert client_with_db.get(f"/incidents/{inc_id}").status_code == HTTP_404


def test_violations_crud_routes(client_with_db):
    """Verify violation notice creation, retrieval, updating, and deletion."""
    # 1. Create notice
    payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "violation_type": "pet_waste_violation",
        "notice_type": "first_notice_to_cure",
        "remedy_instructions": "Clean and dispose of pet waste in courtyard bins immediately.",
        "cure_days": 3,
        "fine_amount": TEST_FINE,
        "charge_to_ledger": True,
    }
    create_resp = client_with_db.post("/violations", json=payload)
    assert create_resp.status_code == HTTP_201
    vn_data = create_resp.json()["notice"]
    vn_id = vn_data["id"]
    assert vn_data["fine_amount"] == TEST_FINE
    assert vn_data["status"] == "issued"

    # 2. Get notice
    get_resp = client_with_db.get(f"/violations/{vn_id}")
    assert get_resp.status_code == HTTP_200
    assert get_resp.json()["notice"]["id"] == vn_id

    # 3. List notices
    list_resp = client_with_db.get("/violations?tenant_id=tenant_1")
    assert list_resp.status_code == HTTP_200
    assert list_resp.json()["total"] >= 1

    # 4. Patch notice
    patch_resp = client_with_db.patch(
        f"/violations/{vn_id}",
        json={"status": "cured", "notes": "Courtyard verified clean by custodial staff."},
    )
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["notice"]["status"] == "cured"

    # 5. Get tenant violations
    tenant_resp = client_with_db.get("/tenants/tenant_1/violations")
    assert tenant_resp.status_code == HTTP_200
    assert len(tenant_resp.json()["items"]) >= 1

    # 6. Delete notice
    del_resp = client_with_db.delete(f"/violations/{vn_id}")
    assert del_resp.status_code == HTTP_200
    assert client_with_db.get(f"/violations/{vn_id}").status_code == HTTP_404


def test_appeals_crud_routes(client_with_db):
    """Verify violation appeal submission, review, and resolution."""
    # Create notice to appeal against
    notice_resp = client_with_db.post(
        "/violations",
        json={
            "tenant_id": "tenant_1",
            "unit_id": "unit_101",
            "violation_type": "unauthorized_occupant",
            "remedy_instructions": "Submit registration application for long-term guest.",
            "fine_amount": TEST_FINE,
        },
    )
    assert notice_resp.status_code == HTTP_201
    vn_id = notice_resp.json()["notice"]["id"]

    # 1. Submit appeal
    appeal_payload = {
        "notice_id": vn_id,
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "reason": "Guest was visiting for 3 days only during graduation weekend.",
    }
    appeal_resp = client_with_db.post("/appeals", json=appeal_payload)
    assert appeal_resp.status_code == HTTP_201
    apl_data = appeal_resp.json()["appeal"]
    apl_id = apl_data["id"]
    assert apl_data["status"] == "submitted"

    # 2. Get appeal
    get_resp = client_with_db.get(f"/appeals/{apl_id}")
    assert get_resp.status_code == HTTP_200
    assert get_resp.json()["appeal"]["id"] == apl_id

    # 3. List appeals
    list_resp = client_with_db.get(f"/appeals?notice_id={vn_id}")
    assert list_resp.status_code == HTTP_200
    assert list_resp.json()["total"] == 1

    # 4. Review appeal (waived)
    patch_resp = client_with_db.patch(
        f"/appeals/{apl_id}",
        json={
            "status": "waived",
            "reviewed_by": "Property Manager",
            "decision_notes": "Itinerary confirmed 3-day stay; fine waived.",
        },
    )
    assert patch_resp.status_code == HTTP_200
    assert patch_resp.json()["appeal"]["status"] == "waived"

    # Verify notice was marked closed
    re_notice = client_with_db.get(f"/violations/{vn_id}").json()["notice"]
    assert re_notice["status"] == "closed"
    assert re_notice["fine_amount"] == 0.0

    # 5. Delete appeal
    del_resp = client_with_db.delete(f"/appeals/{apl_id}")
    assert del_resp.status_code == HTTP_200
    assert client_with_db.get(f"/appeals/{apl_id}").status_code == HTTP_404


def test_session_issue_violation_notice_route(client_with_db):
    """Verify 1-click violation notice issuance grounded in resident support session."""
    session_id = "sess_violation_test_01"
    link_res = client_with_db.post(
        f"/sessions/{session_id}/link-tenant",
        json={"tenant_id": "tenant_3"},
    )
    assert link_res.status_code == HTTP_200

    payload = {
        "violation_type": "common_area_damage",
        "notice_type": "fine_assessment",
        "remedy_instructions": "Restitution for damaged elevator threshold plate.",
        "fine_amount": TEST_FINE_100,
        "cure_days": 14,
        "charge_to_ledger": True,
        "notes": "Assessed following move-in inspection review.",
    }
    response = client_with_db.post(
        f"/sessions/{session_id}/issue-violation-notice",
        json=payload,
    )
    assert response.status_code == HTTP_201
    vn = response.json()["notice"]
    assert vn["tenant_id"] == "tenant_3"
    assert vn["unit_id"] == "unit_PH1"
    assert vn["fine_amount"] == TEST_FINE_100


def test_session_submit_violation_appeal_route(client_with_db):
    """Verify 1-click violation appeal submission grounded in resident support session."""
    session_id = "sess_appeal_test_01"
    link_res = client_with_db.post(
        f"/sessions/{session_id}/link-tenant",
        json={"tenant_id": "tenant_3"},
    )
    assert link_res.status_code == HTTP_200

    # Elena's seeded notice is viol_elena_01
    payload = {
        "notice_id": "viol_elena_01",
        "reason": "Terrace door was closed; sound originated from adjoining building courtyard.",
    }
    response = client_with_db.post(
        f"/sessions/{session_id}/submit-violation-appeal",
        json=payload,
    )
    assert response.status_code == HTTP_201
    appeal = response.json()["appeal"]
    assert appeal["notice_id"] == "viol_elena_01"
    assert appeal["tenant_id"] == "tenant_3"
    assert appeal["status"] == "submitted"

    # Reject non-existent notice
    bad_resp = client_with_db.post(
        f"/sessions/{session_id}/submit-violation-appeal",
        json={"notice_id": "viol_nonexistent_999", "reason": "Test"},
    )
    assert bad_resp.status_code == HTTP_404
