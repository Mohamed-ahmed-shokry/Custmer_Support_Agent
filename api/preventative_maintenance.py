"""Preventative maintenance schedules, safety inspections, entry notices, and compliance engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum

from api import db_utils


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
