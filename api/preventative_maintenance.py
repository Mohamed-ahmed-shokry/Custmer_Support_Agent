"""Preventative maintenance schedules, safety inspections, entry notices, and compliance engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils, webhooks


class PMCategory(StrEnum):
    HVAC_FILTER = "hvac_filter"
    SMOKE_CO_DETECTOR = "smoke_co_detector"
    FIRE_SAFETY = "fire_safety"
    PLUMBING_FLUSH = "plumbing_flush"
    WINTERIZATION = "winterization"
    PEST_PREVENTION = "pest_prevention"
    APPLIANCE_CHECK = "appliance_check"


class PMFrequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"


class PMTaskStatus(StrEnum):
    SCHEDULED = "scheduled"
    NOTICE_SENT = "notice_sent"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class ConsentStatus(StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    RESCHEDULE_REQUESTED = "reschedule_requested"
    DENIED = "denied"


MIN_SEEDED_SCHEDULES = 2


def _generate_schedule_id() -> str:
    return f"pms_{secrets.token_hex(4)}"


def _generate_task_id() -> str:
    return f"pmt_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def init_preventative_maintenance_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize SQLite tables, indexes, and initial seed data for preventative maintenance."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pm_schedules (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                frequency TEXT NOT NULL,
                building_name TEXT,
                description TEXT NOT NULL DEFAULT '',
                assigned_vendor TEXT,
                estimated_duration_minutes INTEGER NOT NULL DEFAULT 30,
                notice_hours_required INTEGER NOT NULL DEFAULT 24,
                is_active INTEGER NOT NULL DEFAULT 1,
                next_run_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pm_tasks (
                id TEXT PRIMARY KEY,
                schedule_id TEXT NOT NULL REFERENCES pm_schedules(id) ON DELETE CASCADE,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                tenant_id TEXT REFERENCES tenants(id) ON DELETE SET NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                scheduled_date TEXT NOT NULL,
                assigned_technician TEXT,
                entry_notice_sent INTEGER NOT NULL DEFAULT 0,
                entry_notice_at TEXT,
                resident_consent_status TEXT NOT NULL DEFAULT 'pending',
                completed_at TEXT,
                inspection_notes TEXT DEFAULT '',
                checklist_passed INTEGER,
                work_order_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pm_schedules_category ON pm_schedules(category)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pm_tasks_unit_status ON pm_tasks(unit_id, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pm_tasks_tenant ON pm_tasks(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pm_tasks_scheduled_date ON pm_tasks(scheduled_date)"
        )

        _seed_pm_data(cursor)
        conn.commit()
    finally:
        if close_conn:
            conn.close()


def _seed_pm_data(cursor: sqlite3.Cursor) -> None:
    """Seed initial preventative maintenance schedules and tasks if empty."""
    cursor.execute("SELECT COUNT(*) FROM pm_schedules")
    if cursor.fetchone()[0] >= MIN_SEEDED_SCHEDULES:
        return

    now_iso = _now_iso()
    upcoming = (datetime.datetime.now(UTC) + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    past_due = (datetime.datetime.now(UTC) - datetime.timedelta(days=5)).strftime("%Y-%m-%d")

    cursor.execute(
        """
        INSERT OR IGNORE INTO pm_schedules (
            id, title, category, frequency, building_name, description,
            assigned_vendor, estimated_duration_minutes, notice_hours_required,
            is_active, next_run_date, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "pms_seed_hvac",
            "Quarterly MERV-13 HVAC Filter Replacement",
            PMCategory.HVAC_FILTER.value,
            PMFrequency.QUARTERLY.value,
            "Main Tower",
            "Replace air filters and inspect condensate drain lines in all residential units.",
            "Apex HVAC Solutions",
            25,
            24,
            1,
            upcoming,
            now_iso,
            now_iso,
        ),
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO pm_schedules (
            id, title, category, frequency, building_name, description,
            assigned_vendor, estimated_duration_minutes, notice_hours_required,
            is_active, next_run_date, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "pms_seed_smoke",
            "Annual Smoke & CO Detector Compliance Test",
            PMCategory.SMOKE_CO_DETECTOR.value,
            PMFrequency.ANNUAL.value,
            "All Buildings",
            "Test photoelectric smoke alarms, replace backup batteries, and verify CO sensors.",
            "SafeGuard Fire & Life Safety",
            20,
            48,
            1,
            upcoming,
            now_iso,
            now_iso,
        ),
    )

    cursor.execute("SELECT id, unit_id FROM tenants LIMIT 2")
    tenants = cursor.fetchall()
    if tenants:
        t1_id, u1_id = tenants[0][0], tenants[0][1]
        cursor.execute(
            """
            INSERT OR IGNORE INTO pm_tasks (
                id, schedule_id, unit_id, tenant_id, category, status,
                scheduled_date, assigned_technician, entry_notice_sent,
                entry_notice_at, resident_consent_status, inspection_notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pmt_seed_101",
                "pms_seed_hvac",
                u1_id,
                t1_id,
                PMCategory.HVAC_FILTER.value,
                PMTaskStatus.NOTICE_SENT.value,
                upcoming,
                "Carlos Mendez",
                1,
                now_iso,
                ConsentStatus.GRANTED.value,
                "24-hour entry notice delivered via resident portal.",
                now_iso,
                now_iso,
            ),
        )
        if len(tenants) > 1:
            t2_id, u2_id = tenants[1][0], tenants[1][1]
            cursor.execute(
                """
                INSERT OR IGNORE INTO pm_tasks (
                    id, schedule_id, unit_id, tenant_id, category, status,
                    scheduled_date, assigned_technician, entry_notice_sent,
                    resident_consent_status, inspection_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "pmt_seed_102",
                    "pms_seed_smoke",
                    u2_id,
                    t2_id,
                    PMCategory.SMOKE_CO_DETECTOR.value,
                    PMTaskStatus.SCHEDULED.value,
                    past_due,
                    "Elena Vance (Fire Safety)",
                    0,
                    ConsentStatus.PENDING.value,
                    "Awaiting 48h legal entry notice delivery.",
                    now_iso,
                    now_iso,
                ),
            )


def _row_to_schedule(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "title": row[1],
        "category": row[2],
        "frequency": row[3],
        "building_name": row[4],
        "description": row[5],
        "assigned_vendor": row[6],
        "estimated_duration_minutes": row[7],
        "notice_hours_required": row[8],
        "is_active": bool(row[9]),
        "next_run_date": row[10],
        "created_at": row[11],
        "updated_at": row[12],
    }


def create_pm_schedule(  # noqa: PLR0913, PLR0917
    title: str,
    category: str,
    frequency: str,
    next_run_date: str,
    building_name: str | None = None,
    description: str = "",
    assigned_vendor: str | None = None,
    estimated_duration_minutes: int = 30,
    notice_hours_required: int = 24,
    is_active: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a recurring preventative maintenance program schedule."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        schedule_id = _generate_schedule_id()
        now_iso = _now_iso()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pm_schedules (
                id, title, category, frequency, building_name, description,
                assigned_vendor, estimated_duration_minutes, notice_hours_required,
                is_active, next_run_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                schedule_id,
                title,
                category,
                frequency,
                building_name,
                description,
                assigned_vendor,
                estimated_duration_minutes,
                notice_hours_required,
                1 if is_active else 0,
                next_run_date,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        created = get_pm_schedule(schedule_id, conn=conn)
        assert created is not None
        webhooks.dispatch_event(
            "pm.schedule_created",
            {
                "schedule_id": schedule_id,
                "title": title,
                "category": category,
                "frequency": frequency,
                "next_run_date": next_run_date,
            },
        )
        return created
    finally:
        if close_conn:
            conn.close()


def list_pm_schedules(
    category: str | None = None,
    frequency: str | None = None,
    is_active: bool | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List preventative maintenance schedules with optional filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        query = (
            "SELECT id, title, category, frequency, building_name, description, "
            "assigned_vendor, estimated_duration_minutes, notice_hours_required, "
            "is_active, next_run_date, created_at, updated_at "
            "FROM pm_schedules WHERE 1=1"
        )
        params: list[Any] = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if frequency:
            query += " AND frequency = ?"
            params.append(frequency)
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(1 if is_active else 0)
        query += " ORDER BY next_run_date ASC, created_at DESC"

        cursor = conn.cursor()
        cursor.execute(query, params)
        return [_row_to_schedule(r) for r in cursor.fetchall()]
    finally:
        if close_conn:
            conn.close()


def get_pm_schedule(
    schedule_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Retrieve a preventative maintenance schedule by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, category, frequency, building_name, description,
                   assigned_vendor, estimated_duration_minutes, notice_hours_required,
                   is_active, next_run_date, created_at, updated_at
            FROM pm_schedules WHERE id = ?
            """,
            (schedule_id,),
        )
        row = cursor.fetchone()
        return _row_to_schedule(row) if row else None
    finally:
        if close_conn:
            conn.close()


def update_pm_schedule(
    schedule_id: str,
    updates: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update fields on an existing preventative maintenance schedule."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        existing = get_pm_schedule(schedule_id, conn=conn)
        if not existing:
            return None

        allowed = {
            "title",
            "category",
            "frequency",
            "building_name",
            "description",
            "assigned_vendor",
            "estimated_duration_minutes",
            "notice_hours_required",
            "is_active",
            "next_run_date",
        }
        set_clauses: list[str] = []
        params: list[Any] = []
        for k, v in updates.items():
            if k in allowed:
                set_clauses.append(f"{k} = ?")
                params.append((1 if v else 0) if k == "is_active" else v)

        if not set_clauses:
            return existing

        set_clauses.append("updated_at = ?")
        params.append(_now_iso())
        params.append(schedule_id)

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE pm_schedules SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()
        return get_pm_schedule(schedule_id, conn=conn)
    finally:
        if close_conn:
            conn.close()


def _row_to_task(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "schedule_id": row[1],
        "unit_id": row[2],
        "tenant_id": row[3],
        "category": row[4],
        "status": row[5],
        "scheduled_date": row[6],
        "assigned_technician": row[7],
        "entry_notice_sent": bool(row[8]),
        "entry_notice_at": row[9],
        "resident_consent_status": row[10],
        "completed_at": row[11],
        "inspection_notes": row[12] or "",
        "checklist_passed": bool(row[13]) if row[13] is not None else None,
        "work_order_id": row[14],
        "created_at": row[15],
        "updated_at": row[16],
        "unit_number": row[17] if len(row) > 17 else None,
        "tenant_name": row[18] if len(row) > 18 else None,
    }


_TASK_SELECT = """
    SELECT t.id, t.schedule_id, t.unit_id, t.tenant_id, t.category, t.status,
           t.scheduled_date, t.assigned_technician, t.entry_notice_sent,
           t.entry_notice_at, t.resident_consent_status, t.completed_at,
           t.inspection_notes, t.checklist_passed, t.work_order_id,
           t.created_at, t.updated_at,
           u.unit_number,
           CASE WHEN tn.id IS NOT NULL THEN tn.first_name || ' ' || tn.last_name ELSE NULL END
    FROM pm_tasks t
    LEFT JOIN units u ON t.unit_id = u.id
    LEFT JOIN tenants tn ON t.tenant_id = tn.id
"""


def create_pm_task(  # noqa: PLR0913, PLR0917
    schedule_id: str,
    unit_id: str,
    scheduled_date: str,
    tenant_id: str | None = None,
    category: str | None = None,
    assigned_technician: str | None = None,
    inspection_notes: str = "",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a preventative maintenance task for a specific unit."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        sched = get_pm_schedule(schedule_id, conn=conn)
        if not sched:
            raise ValueError(f"PM schedule not found: {schedule_id}")

        resolved_category = category or sched["category"]
        resolved_tech = assigned_technician or sched.get("assigned_vendor")
        task_id = _generate_task_id()
        now_iso = _now_iso()

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pm_tasks (
                id, schedule_id, unit_id, tenant_id, category, status,
                scheduled_date, assigned_technician, entry_notice_sent,
                resident_consent_status, inspection_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                task_id,
                schedule_id,
                unit_id,
                tenant_id,
                resolved_category,
                PMTaskStatus.SCHEDULED.value,
                scheduled_date,
                resolved_tech,
                ConsentStatus.PENDING.value,
                inspection_notes,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        created = get_pm_task(task_id, conn=conn)
        assert created is not None
        webhooks.dispatch_event(
            "pm.task_scheduled",
            {
                "task_id": task_id,
                "schedule_id": schedule_id,
                "unit_id": unit_id,
                "tenant_id": tenant_id,
                "category": resolved_category,
                "scheduled_date": scheduled_date,
            },
        )
        return created
    finally:
        if close_conn:
            conn.close()


def list_pm_tasks(  # noqa: PLR0913, PLR0917
    unit_id: str | None = None,
    tenant_id: str | None = None,
    schedule_id: str | None = None,
    status: str | None = None,
    category: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List preventative maintenance tasks with optional filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        query = f"{_TASK_SELECT} WHERE 1=1"
        params: list[Any] = []
        if unit_id:
            query += " AND t.unit_id = ?"
            params.append(unit_id)
        if tenant_id:
            query += " AND t.tenant_id = ?"
            params.append(tenant_id)
        if schedule_id:
            query += " AND t.schedule_id = ?"
            params.append(schedule_id)
        if status:
            query += " AND t.status = ?"
            params.append(status)
        if category:
            query += " AND t.category = ?"
            params.append(category)
        query += " ORDER BY t.scheduled_date ASC, t.created_at DESC"

        cursor = conn.cursor()
        cursor.execute(query, params)
        return [_row_to_task(r) for r in cursor.fetchall()]
    finally:
        if close_conn:
            conn.close()


def get_pm_task(
    task_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Retrieve a preventative maintenance task by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        cursor = conn.cursor()
        cursor.execute(f"{_TASK_SELECT} WHERE t.id = ?", (task_id,))
        row = cursor.fetchone()
        return _row_to_task(row) if row else None
    finally:
        if close_conn:
            conn.close()


def update_pm_task(
    task_id: str,
    updates: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update fields on an existing preventative maintenance task."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_preventative_maintenance_db(conn)
        existing = get_pm_task(task_id, conn=conn)
        if not existing:
            return None

        allowed = {
            "status",
            "scheduled_date",
            "assigned_technician",
            "resident_consent_status",
            "inspection_notes",
        }
        set_clauses: list[str] = []
        params: list[Any] = []
        for k, v in updates.items():
            if k in allowed:
                set_clauses.append(f"{k} = ?")
                params.append(v)

        if not set_clauses:
            return existing

        set_clauses.append("updated_at = ?")
        params.append(_now_iso())
        params.append(task_id)

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE pm_tasks SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()
        return get_pm_task(task_id, conn=conn)
    finally:
        if close_conn:
            conn.close()
