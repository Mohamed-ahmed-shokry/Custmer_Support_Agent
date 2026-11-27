"""Eviction compliance, statutory legal notices, court filings, and payment plan workouts engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum

from api import db_utils


class NoticeType(StrEnum):
    PAY_OR_QUIT = "pay_or_quit"
    CURE_OR_QUIT = "cure_or_quit"
    UNCONDITIONAL_QUIT = "unconditional_quit"
    NON_RENEWAL = "non_renewal"


class CaseStatus(StrEnum):
    NOTICE_SERVED = "notice_served"
    CURE_WINDOW_ACTIVE = "cure_window_active"
    PAYMENT_PLAN_ACTIVE = "payment_plan_active"
    FILED_IN_COURT = "filed_in_court"
    HEARING_SCHEDULED = "hearing_scheduled"
    JUDGMENT_GRANTED = "judgment_granted"
    CURED_DISMISSED = "cured_dismissed"
    EVICTED_CLOSED = "evicted_closed"


class PaymentPlanStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DEFAULTED = "defaulted"
    CANCELLED = "cancelled"


class DeliveryMethod(StrEnum):
    CERTIFIED_MAIL = "certified_mail"
    PERSONAL_SERVICE = "personal_service"
    POSTED_AND_MAILED = "posted_and_mailed"
    PORTAL_AND_MAIL = "portal_and_mail"


DEFAULT_CURE_DAYS = 5
MIN_SEEDED_CASES = 2


def _generate_case_id() -> str:
    return f"evc_{secrets.token_hex(4)}"


def _generate_plan_id() -> str:
    return f"ppl_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _today_str() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m-%d")


def _compute_cure_deadline(served_date: str, cure_days: int = DEFAULT_CURE_DAYS) -> str:
    try:
        dt = datetime.date.fromisoformat(served_date[:10])
    except ValueError:
        dt = datetime.datetime.now(UTC).date()
    return (dt + datetime.timedelta(days=max(1, cure_days))).isoformat()


def init_evictions_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize SQLite tables, indexes, and deterministic seed data for evictions."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS eviction_cases (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                notice_type TEXT NOT NULL DEFAULT 'pay_or_quit',
                delivery_method TEXT NOT NULL DEFAULT 'certified_mail',
                reason TEXT NOT NULL,
                arrears_amount REAL NOT NULL DEFAULT 0.0,
                notice_served_date TEXT NOT NULL,
                cure_deadline_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'cure_window_active',
                court_case_number TEXT NOT NULL DEFAULT '',
                court_name TEXT NOT NULL DEFAULT '',
                filing_date TEXT,
                hearing_date TEXT,
                attorney_name TEXT NOT NULL DEFAULT '',
                resolution_notes TEXT NOT NULL DEFAULT '',
                closed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_plans (
                id TEXT PRIMARY KEY,
                case_id TEXT REFERENCES eviction_cases(id) ON DELETE SET NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                total_arrears REAL NOT NULL,
                installment_amount REAL NOT NULL,
                installment_count INTEGER NOT NULL,
                installments_paid INTEGER NOT NULL DEFAULT 0,
                amount_paid REAL NOT NULL DEFAULT 0.0,
                next_due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_evictions_tenant_status "
            "ON eviction_cases(tenant_id, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_evictions_unit ON eviction_cases(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_payment_plans_tenant "
            "ON payment_plans(tenant_id, status)"
        )

        _seed_evictions_data(cursor)
        conn.commit()
    finally:
        if close_conn:
            conn.close()


def _seed_evictions_data(cursor: sqlite3.Cursor) -> None:
    """Seed initial delinquency/eviction cases and a payment plan workout if empty."""
    cursor.execute("SELECT COUNT(*) FROM eviction_cases")
    if cursor.fetchone()[0] >= MIN_SEEDED_CASES:
        return

    cursor.execute("SELECT id, unit_id FROM tenants LIMIT 2")
    tenants = cursor.fetchall()
    if not tenants:
        return

    now_iso = _now_iso()
    served_str = _today_str()
    cure_str = (datetime.datetime.now(UTC) + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    due_str = (datetime.datetime.now(UTC) + datetime.timedelta(days=10)).strftime("%Y-%m-%d")

    t1_id, u1_id = str(tenants[0][0]), str(tenants[0][1])
    cursor.execute(
        """
        INSERT OR IGNORE INTO eviction_cases (
            id, unit_id, tenant_id, notice_type, delivery_method, reason,
            arrears_amount, notice_served_date, cure_deadline_date, status,
            resolution_notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "evc_seed_01",
            u1_id,
            t1_id,
            NoticeType.PAY_OR_QUIT.value,
            DeliveryMethod.CERTIFIED_MAIL.value,
            "Past-due rent balance under structured 3-month repayment workout.",
            1800.0,
            served_str,
            cure_str,
            CaseStatus.PAYMENT_PLAN_ACTIVE.value,
            "Resident entered approved 3-installment payment plan.",
            now_iso,
            now_iso,
        ),
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO payment_plans (
            id, case_id, tenant_id, unit_id, total_arrears, installment_amount,
            installment_count, installments_paid, amount_paid, next_due_date,
            status, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ppl_seed_01",
            "evc_seed_01",
            t1_id,
            u1_id,
            1800.0,
            600.0,
            3,
            1,
            600.0,
            due_str,
            PaymentPlanStatus.ACTIVE.value,
            "First installment received on time.",
            now_iso,
            now_iso,
        ),
    )

    if len(tenants) > 1:
        t2_id, u2_id = str(tenants[1][0]), str(tenants[1][1])
        cursor.execute(
            """
            INSERT OR IGNORE INTO eviction_cases (
                id, unit_id, tenant_id, notice_type, delivery_method, reason,
                arrears_amount, notice_served_date, cure_deadline_date, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evc_seed_02",
                u2_id,
                t2_id,
                NoticeType.CURE_OR_QUIT.value,
                DeliveryMethod.POSTED_AND_MAILED.value,
                "5-day statutory cure notice for unauthorized patio storage.",
                0.0,
                served_str,
                cure_str,
                CaseStatus.CURE_WINDOW_ACTIVE.value,
                now_iso,
                now_iso,
            ),
        )
