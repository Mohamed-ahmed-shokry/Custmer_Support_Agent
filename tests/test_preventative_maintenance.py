"""Unit tests for preventative maintenance schedules, tasks, entry notices, and compliance KPIs."""

import sqlite3

import pytest
from api import preventative_maintenance as pm
from api.preventative_maintenance import ConsentStatus, PMCategory, PMFrequency, PMTaskStatus

MIN_SEED_SCHEDULES = 2


@pytest.fixture
def memory_db():
    """In-memory SQLite database with units, tenants, work_orders, and PM schema."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS units (
            id TEXT PRIMARY KEY,
            unit_number TEXT NOT NULL,
            building_name TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            FOREIGN KEY (unit_id) REFERENCES units(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS work_orders (
            id TEXT PRIMARY KEY,
            unit_id TEXT NOT NULL,
            tenant_id TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            entry_permission TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        "INSERT INTO units (id, unit_number, building_name) "
        "VALUES ('unit_101', '101', 'Main Tower')"
    )
    cursor.execute(
        "INSERT INTO units (id, unit_number, building_name) "
        "VALUES ('unit_202', '202', 'Main Tower')"
    )
    cursor.execute(
        "INSERT INTO tenants (id, first_name, last_name, email, unit_id) VALUES "
        "('tenant_1', 'Marcus', 'Vance', 'marcus@example.com', 'unit_101')"
    )
    cursor.execute(
        "INSERT INTO tenants (id, first_name, last_name, email, unit_id) VALUES "
        "('tenant_2', 'Clara', 'Oswald', 'clara@example.com', 'unit_202')"
    )
    conn.commit()
    pm.init_preventative_maintenance_db(conn)
    yield conn
    conn.close()


def test_pm_seed_data(memory_db):
    """Verify initial seeded schedules and tasks are created."""
    schedules = pm.list_pm_schedules(conn=memory_db)
    assert len(schedules) >= MIN_SEED_SCHEDULES
    tasks = pm.list_pm_tasks(conn=memory_db)
    assert len(tasks) >= MIN_SEED_SCHEDULES


def test_pm_schedule_crud(memory_db):
    """Verify creating, fetching, filtering, and updating PM schedules."""
    created = pm.create_pm_schedule(
        title="Semi-Annual Water Heater Flush",
        category=PMCategory.PLUMBING_FLUSH.value,
        frequency=PMFrequency.SEMI_ANNUAL.value,
        next_run_date="2027-01-15",
        building_name="West Wing",
        assigned_vendor="FlowPro Plumbing",
        conn=memory_db,
    )
    assert created["id"].startswith("pms_")
    assert created["category"] == PMCategory.PLUMBING_FLUSH.value
    assert created["is_active"] is True

    fetched = pm.get_pm_schedule(created["id"], conn=memory_db)
    assert fetched is not None
    assert fetched["title"] == "Semi-Annual Water Heater Flush"

    filtered = pm.list_pm_schedules(category=PMCategory.PLUMBING_FLUSH.value, conn=memory_db)
    assert len(filtered) == 1

    updated = pm.update_pm_schedule(created["id"], {"is_active": False}, conn=memory_db)
    assert updated is not None
    assert updated["is_active"] is False


def test_pm_task_lifecycle_and_entry_notice(memory_db):
    """Verify task creation, entry notice dispatch, and task pass completion."""
    task = pm.create_pm_task(
        schedule_id="pms_seed_hvac",
        unit_id="unit_101",
        tenant_id="tenant_1",
        scheduled_date="2027-02-01",
        assigned_technician="Alex Tech",
        conn=memory_db,
    )
    assert task["id"].startswith("pmt_")
    assert task["status"] == PMTaskStatus.SCHEDULED.value
    assert task["entry_notice_sent"] is False

    noticed = pm.send_pm_entry_notice(
        task["id"],
        notice_notes="24h door hanger placed",
        consent_status=ConsentStatus.GRANTED.value,
        conn=memory_db,
    )
    assert noticed is not None
    assert noticed["entry_notice_sent"] is True
    assert noticed["status"] == PMTaskStatus.NOTICE_SENT.value
    assert noticed["resident_consent_status"] == ConsentStatus.GRANTED.value

    passed = pm.complete_pm_task(
        task["id"],
        passed=True,
        inspection_notes="MERV-13 filter replaced; drain line clear.",
        conn=memory_db,
    )
    assert passed is not None
    assert passed["status"] == PMTaskStatus.PASSED.value
    assert passed["checklist_passed"] is True
    assert passed["work_order_id"] is None


def test_pm_failed_task_escalates_to_work_order(memory_db):
    """Verify failed inspection auto-creates a linked work order."""
    task = pm.create_pm_task(
        schedule_id="pms_seed_smoke",
        unit_id="unit_202",
        tenant_id="tenant_2",
        scheduled_date="2027-02-10",
        conn=memory_db,
    )
    failed = pm.complete_pm_task(
        task["id"],
        passed=False,
        inspection_notes="Hallway smoke detector chirping and unresponsive to test button.",
        auto_create_work_order=True,
        conn=memory_db,
    )
    assert failed is not None
    assert failed["status"] == PMTaskStatus.FAILED.value
    assert failed["checklist_passed"] is False
    assert failed["work_order_id"] is not None
    assert failed["work_order_id"].startswith("wo_")


def test_pm_summaries_and_metrics(memory_db):
    """Verify unit summary, tenant summary, and portfolio metrics."""
    unit_summary = pm.get_unit_pm_summary("unit_101", conn=memory_db)
    assert unit_summary["unit_id"] == "unit_101"
    assert unit_summary["total_tasks"] >= 1

    tenant_summary = pm.get_tenant_pm_summary("tenant_1", conn=memory_db)
    assert tenant_summary["tenant_id"] == "tenant_1"
    assert tenant_summary["total_tasks"] >= 1

    metrics = pm.get_pm_metrics_summary(conn=memory_db)
    assert metrics["total_schedules"] >= MIN_SEED_SCHEDULES
    assert metrics["total_tasks"] >= MIN_SEED_SCHEDULES
    assert "pass_rate_pct" in metrics
