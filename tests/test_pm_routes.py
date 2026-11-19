"""Integration tests for preventative maintenance & compliance FastAPI routes."""

from __future__ import annotations

import pytest
from api import db_utils, preventative_maintenance
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
MIN_SCHEDULES = 2


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a TestClient against an isolated SQLite database."""
    test_db = tmp_path / "test_pm_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_work_orders()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    preventative_maintenance.init_preventative_maintenance_db()

    db_utils.link_session_tenant("sess_pm_1", "tenant_1")
    return TestClient(app)


def test_get_pm_metrics_route(client_with_db):
    """Test GET /pm/metrics."""
    res = client_with_db.get("/pm/metrics")
    assert res.status_code == HTTP_200
    data = res.json()
    assert data["total_schedules"] >= MIN_SCHEDULES
    assert "pass_rate_pct" in data


def test_pm_schedules_crud_routes(client_with_db):
    """Test POST, GET, and PATCH /pm/schedules endpoints."""
    create_res = client_with_db.post(
        "/pm/schedules",
        json={
            "title": "Annual Sprinkler Inspection",
            "category": "fire_safety",
            "frequency": "annual",
            "next_run_date": "2027-03-01",
            "building_name": "East Tower",
        },
    )
    assert create_res.status_code == HTTP_201
    sched = create_res.json()["schedule"]
    sched_id = sched["id"]

    list_res = client_with_db.get("/pm/schedules?category=fire_safety")
    assert list_res.status_code == HTTP_200
    assert list_res.json()["total"] >= 1

    get_res = client_with_db.get(f"/pm/schedules/{sched_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["schedule"]["title"] == "Annual Sprinkler Inspection"

    patch_res = client_with_db.patch(
        f"/pm/schedules/{sched_id}",
        json={"is_active": False},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["schedule"]["is_active"] is False

    missing_res = client_with_db.get("/pm/schedules/pms_does_not_exist")
    assert missing_res.status_code == HTTP_404


def test_pm_tasks_and_entry_notice_and_completion_routes(client_with_db):
    """Test POST /pm/tasks, entry notice, and pass/fail completion."""
    create_res = client_with_db.post(
        "/pm/tasks",
        json={
            "schedule_id": "pms_seed_hvac",
            "unit_id": "unit_101",
            "tenant_id": "tenant_1",
            "scheduled_date": "2027-04-15",
        },
    )
    assert create_res.status_code == HTTP_201
    task_id = create_res.json()["task"]["id"]

    notice_res = client_with_db.post(
        f"/pm/tasks/{task_id}/entry-notice",
        json={"notice_notes": "Sent 24h email notice", "consent_status": "granted"},
    )
    assert notice_res.status_code == HTTP_200
    assert notice_res.json()["task"]["entry_notice_sent"] is True
    assert notice_res.json()["task"]["status"] == "notice_sent"

    complete_res = client_with_db.post(
        f"/pm/tasks/{task_id}/complete",
        json={
            "passed": False,
            "inspection_notes": "Blower motor noisy",
            "auto_create_work_order": True,
        },
    )
    assert complete_res.status_code == HTTP_200
    completed = complete_res.json()["task"]
    assert completed["status"] == "failed"
    assert completed["work_order_id"] is not None


def test_pm_unit_tenant_summaries_and_session_actions(client_with_db):
    """Test unit/tenant PM summary endpoints and 1-click session actions."""
    unit_res = client_with_db.get("/units/unit_101/pm/summary")
    assert unit_res.status_code == HTTP_200
    assert unit_res.json()["unit_id"] == "unit_101"

    tenant_res = client_with_db.get("/tenants/tenant_1/pm/summary")
    assert tenant_res.status_code == HTTP_200
    assert tenant_res.json()["tenant_id"] == "tenant_1"

    sched_res = client_with_db.post(
        "/sessions/sess_pm_1/schedule-pm-task",
        json={
            "schedule_id": "pms_seed_smoke",
            "scheduled_date": "2027-05-01",
            "assigned_technician": "Sam FireTech",
        },
    )
    assert sched_res.status_code == HTTP_201
    new_task_id = sched_res.json()["task"]["id"]

    notice_res = client_with_db.post(
        "/sessions/sess_pm_1/send-pm-entry-notice",
        json={"task_id": new_task_id, "consent_status": "granted"},
    )
    assert notice_res.status_code == HTTP_200
    assert notice_res.json()["task"]["entry_notice_sent"] is True

    unlinked_res = client_with_db.post(
        "/sessions/sess_unknown/schedule-pm-task",
        json={"schedule_id": "pms_seed_smoke", "scheduled_date": "2027-05-01"},
    )
    assert unlinked_res.status_code == HTTP_400
