"""Integration tests for Utility Submetering, Readings & Invoices FastAPI Routes."""

# ruff: noqa: PLR2004, E501

from __future__ import annotations

import pytest
from api import db_utils, utilities
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_METERS_COUNT = 3


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_utility_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_billing_transactions()
    db_utils.create_work_orders()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    utilities.init_utilities_db()

    # Link test session to tenant_3
    db_utils.link_session_tenant("sess_util_1", "tenant_3")
    return TestClient(app)


def test_get_utility_metrics_route(client_with_db):
    """Test GET /utilities/metrics."""
    res = client_with_db.get("/utilities/metrics")
    assert res.status_code == HTTP_200
    data = res.json()
    assert data["total_meters"] >= MIN_METERS_COUNT
    assert "total_kwh" in data
    assert "total_gallons" in data
    assert "total_anomalies" in data


def test_meter_crud_routes(client_with_db):
    """Test POST, GET, and PATCH on /utilities/meters."""
    # List meters
    list_res = client_with_db.get("/utilities/meters?unit_id=unit_PH1")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1

    # Create meter
    create_payload = {
        "unit_id": "unit_101",
        "meter_type": "water",
        "rate_per_unit": 0.01,
        "serial_number": "WTR-101-AUTO",
        "notes": "Automated submeter for unit 101",
    }
    create_res = client_with_db.post("/utilities/meters", json=create_payload)
    assert create_res.status_code == HTTP_201
    created_id = create_res.json()["meter"]["id"]

    # Get meter
    get_res = client_with_db.get(f"/utilities/meters/{created_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["meter"]["serial_number"] == "WTR-101-AUTO"

    # Patch meter
    patch_res = client_with_db.patch(
        f"/utilities/meters/{created_id}", json={"rate_per_unit": 0.015, "status": "inactive"}
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["meter"]["rate_per_unit"] == 0.015
    assert patch_res.json()["meter"]["status"] == "inactive"


def test_meter_reading_and_anomaly_routes(client_with_db):
    """Test POST and GET on /utilities/readings."""
    payload = {
        "meter_id": "mtr_ph1_elec",
        "reading_value": 520.0,
        "previous_reading_value": 480.0,
        "reading_date": "2026-11-15",
    }
    res = client_with_db.post("/utilities/readings", json=payload)
    assert res.status_code == HTTP_201
    rdg = res.json()["reading"]
    assert rdg["consumption"] == 40.0
    assert rdg["cost"] == round(40.0 * 0.15, 2)

    # Get reading by ID
    get_res = client_with_db.get(f"/utilities/readings/{rdg['id']}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["reading"]["id"] == rdg["id"]

    # List readings
    list_res = client_with_db.get("/utilities/readings?unit_id=unit_PH1")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1


def test_utility_invoice_and_ledger_routes(client_with_db):
    """Test POST /utilities/invoices and posting to ledger."""
    inv_payload = {
        "unit_id": "unit_PH1",
        "tenant_id": "tenant_3",
        "billing_month": "2026-12",
        "electricity_amount": 80.0,
        "water_amount": 25.0,
        "gas_amount": 40.0,
        "sewer_trash_amount": 45.0,
    }
    create_res = client_with_db.post("/utilities/invoices", json=inv_payload)
    assert create_res.status_code == HTTP_201
    inv = create_res.json()["invoice"]
    assert inv["total_amount"] == 190.0

    # Post to ledger
    post_res = client_with_db.post(f"/utilities/invoices/{inv['id']}/post-to-ledger")
    assert post_res.status_code == HTTP_200
    assert post_res.json()["invoice"]["status"] == "posted_to_ledger"
    assert post_res.json()["invoice"]["ledger_transaction_id"] is not None

    # Get unit summary
    summary_res = client_with_db.get("/units/unit_PH1/utilities/summary")
    assert summary_res.status_code == HTTP_200
    assert summary_res.json()["unit_id"] == "unit_PH1"

    # Get tenant summary
    tenant_summary_res = client_with_db.get("/tenants/tenant_3/utilities/summary")
    assert tenant_summary_res.status_code == HTTP_200
    assert tenant_summary_res.json()["tenant_id"] == "tenant_3"


def test_session_meter_and_leak_routes(client_with_db):
    """Test 1-click resident session actions for meter readings and leak alerts."""
    # Record reading from session
    reading_payload = {
        "meter_id": "mtr_ph1_elec",
        "reading_value": 560.0,
        "notes": "Verified by resident",
    }
    rdg_res = client_with_db.post("/sessions/sess_util_1/record-meter-reading", json=reading_payload)
    assert rdg_res.status_code == HTTP_201
    assert rdg_res.json()["reading"]["reading_value"] == 560.0

    # Report leak from session
    leak_payload = {
        "utility_type": "water",
        "severity": "urgent",
        "location_description": "Under kitchen sink valve dripping",
        "estimated_duration": "Started 2 hours ago",
    }
    leak_res = client_with_db.post("/sessions/sess_util_1/report-utility-leak", json=leak_payload)
    assert leak_res.status_code == HTTP_201
    data = leak_res.json()
    assert data["status"] == "reported"
    assert "work_order" in data
    assert data["work_order"]["priority"] == "emergency"
