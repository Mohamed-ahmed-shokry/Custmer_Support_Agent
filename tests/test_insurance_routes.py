"""Integration tests for Renters Insurance Compliance & Claims FastAPI Routes."""

# ruff: noqa: PLR2004, E501

from __future__ import annotations

import pytest
from api import db_utils, insurance
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_insurance_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_billing_transactions()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    insurance.init_insurance_db()

    # Link test session to tenant_1
    db_utils.link_session_tenant("sess_ins_1", "tenant_1")
    return TestClient(app)


def test_get_insurance_metrics_route(client_with_db):
    """Test GET /insurance/metrics."""
    res = client_with_db.get("/insurance/metrics")
    assert res.status_code == HTTP_200
    data = res.json()
    assert "total_policies" in data
    assert "active_policies" in data
    assert "compliance_rate_pct" in data
    assert "total_claims" in data


def test_insurance_policy_crud_and_verification_routes(client_with_db):
    """Test POST, GET, and verification routes for insurance policies."""
    create_payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "carrier_name": "State Farm",
        "policy_number": "POL-API-101",
        "liability_coverage_amount": 100000.0,
        "expiration_date": "2027-12-31",
        "document_url": "https://example.com/coi_101.pdf",
    }
    create_res = client_with_db.post("/insurance/policies", json=create_payload)
    assert create_res.status_code == HTTP_201
    created = create_res.json()["policy"]
    policy_id = created["id"]
    assert created["policy_number"] == "POL-API-101"
    assert created["status"] == "pending_verification"

    # Get single policy
    get_res = client_with_db.get(f"/insurance/policies/{policy_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["policy"]["id"] == policy_id

    # List policies with filters
    list_res = client_with_db.get("/insurance/policies?tenant_id=tenant_1&status=pending_verification")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1

    # Verify policy - approve
    verify_res = client_with_db.post(
        f"/insurance/policies/{policy_id}/verify",
        json={"is_approved": True, "verified_by": "Agent Miller", "verification_notes": "All verified"},
    )
    assert verify_res.status_code == HTTP_200
    assert verify_res.json()["policy"]["status"] == "active"
    assert verify_res.json()["policy"]["verified_by"] == "Agent Miller"

    # 404 for unknown policy
    not_found = client_with_db.get("/insurance/policies/unknown_pol")
    assert not_found.status_code == HTTP_404


def test_insurance_policy_fee_assessment_route(client_with_db):
    """Test POST /insurance/policies/{id}/assess-fee."""
    policy = insurance.create_insurance_policy({
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "carrier_name": "Unknown",
        "policy_number": "POL-FEE-99",
        "liability_coverage_amount": 50000.0,
        "expiration_date": "2024-01-01",
    })
    policy_id = policy["id"]

    res = client_with_db.post(
        f"/insurance/policies/{policy_id}/assess-fee",
        json={"fee_amount": 35.0},
    )
    assert res.status_code == HTTP_200
    data = res.json()
    assert data["policy"]["id"] == policy_id
    assert data["fee_amount"] == 35.0
    assert "transaction_id" in data

    # 404 for unknown
    res_404 = client_with_db.post("/insurance/policies/unknown_pol/assess-fee", json={"fee_amount": 25.0})
    assert res_404.status_code == HTTP_404


def test_insurance_claims_crud_and_update_routes(client_with_db):
    """Test POST, GET, and PATCH routes for resident claims."""
    claim_payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "claim_type": "water_damage",
        "incident_date": "2026-11-15",
        "description": "Pipe leaked under bathroom sink causing carpet damage.",
        "estimated_loss": 850.0,
    }
    create_res = client_with_db.post("/insurance/claims", json=claim_payload)
    assert create_res.status_code == HTTP_201
    claim = create_res.json()["claim"]
    claim_id = claim["id"]
    assert claim["claim_type"] == "water_damage"
    assert claim["status"] == "submitted"

    # Get claim
    get_res = client_with_db.get(f"/insurance/claims/{claim_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["claim"]["id"] == claim_id

    # List claims
    list_res = client_with_db.get("/insurance/claims?tenant_id=tenant_1")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1

    # Update claim
    patch_res = client_with_db.patch(
        f"/insurance/claims/{claim_id}",
        json={"status": "approved", "settled_amount": 800.0, "resolution_notes": "Approved after inspection"},
    )
    assert patch_res.status_code == HTTP_200
    updated = patch_res.json()["claim"]
    assert updated["status"] == "approved"
    assert updated["settled_amount"] == 800.0

    # 404 for unknown claim
    assert client_with_db.get("/insurance/claims/unknown_claim").status_code == HTTP_404
    assert client_with_db.patch("/insurance/claims/unknown_claim", json={"status": "closed"}).status_code == HTTP_404


def test_insurance_summaries_routes(client_with_db):
    """Test GET /units/{id}/insurance/summary and GET /tenants/{id}/insurance/summary."""
    insurance.create_insurance_policy({
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "carrier_name": "Lemonade",
        "policy_number": "LEM-101",
        "liability_coverage_amount": 100000.0,
        "expiration_date": "2027-12-31",
    })
    unit_res = client_with_db.get("/units/unit_101/insurance/summary")
    assert unit_res.status_code == HTTP_200
    unit_data = unit_res.json()
    assert unit_data["unit_id"] == "unit_101"
    assert unit_data["policies_count"] >= 1

    tenant_res = client_with_db.get("/tenants/tenant_1/insurance/summary")
    assert tenant_res.status_code == HTTP_200
    tenant_data = tenant_res.json()
    assert tenant_data["tenant_id"] == "tenant_1"
    assert tenant_data["policies_count"] >= 1


def test_session_1click_insurance_actions(client_with_db):
    """Test 1-click insurance submission and claim filing from active session."""
    # Submit insurance via session
    submit_res = client_with_db.post(
        "/sessions/sess_ins_1/submit-insurance",
        json={
            "carrier_name": "Geico",
            "policy_number": "GEC-777",
            "liability_coverage_amount": 100000.0,
            "expiration_date": "2027-10-15",
            "document_url": "https://example.com/geico_coi.pdf",
        },
    )
    assert submit_res.status_code == HTTP_201
    assert submit_res.json()["status"] == "submitted"
    assert submit_res.json()["policy"]["policy_number"] == "GEC-777"

    # File claim via session
    claim_res = client_with_db.post(
        "/sessions/sess_ins_1/file-insurance-claim",
        json={
            "claim_type": "theft",
            "incident_date": "2026-11-16",
            "description": "Bicycle stolen from storage locker.",
            "estimated_loss": 500.0,
        },
    )
    assert claim_res.status_code == HTTP_201
    assert claim_res.json()["status"] == "filed"
    assert claim_res.json()["claim"]["claim_type"] == "theft"

    # Unlinked session returns 400
    err_submit = client_with_db.post(
        "/sessions/unlinked_sess/submit-insurance",
        json={
            "carrier_name": "Geico",
            "policy_number": "GEC-999",
            "liability_coverage_amount": 100000.0,
            "expiration_date": "2027-10-15",
        },
    )
    assert err_submit.status_code == HTTP_400

    err_claim = client_with_db.post(
        "/sessions/unlinked_sess/file-insurance-claim",
        json={
            "claim_type": "fire",
            "incident_date": "2026-11-16",
            "description": "Smoke damage in kitchen.",
        },
    )
    assert err_claim.status_code == HTTP_400
