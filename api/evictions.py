"""Eviction compliance, statutory legal notices, court filings, and payment plan workouts engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils, webhooks


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


def _row_to_plan(row: sqlite3.Row) -> dict[str, Any]:
    total = round(float(row["total_arrears"]), 2)
    paid = round(float(row["amount_paid"]), 2)
    remaining = max(0.0, round(total - paid, 2))
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "tenant_id": row["tenant_id"],
        "unit_id": row["unit_id"],
        "total_arrears": total,
        "installment_amount": round(float(row["installment_amount"]), 2),
        "installment_count": int(row["installment_count"]),
        "installments_paid": int(row["installments_paid"]),
        "amount_paid": paid,
        "remaining_balance": remaining,
        "next_due_date": row["next_due_date"],
        "status": row["status"],
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_case(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    cid = row["id"]
    cursor.execute(
        "SELECT * FROM payment_plans WHERE case_id = ? ORDER BY created_at DESC",
        (cid,),
    )
    plans = [_row_to_plan(r) for r in cursor.fetchall()]
    status = row["status"]
    deadline = row["cure_deadline_date"]
    is_cure_expired = bool(
        deadline
        and status in (CaseStatus.NOTICE_SERVED.value, CaseStatus.CURE_WINDOW_ACTIVE.value)
        and deadline < _today_str()
    )
    return {
        "id": cid,
        "unit_id": row["unit_id"],
        "tenant_id": row["tenant_id"],
        "notice_type": row["notice_type"],
        "delivery_method": row["delivery_method"],
        "reason": row["reason"],
        "arrears_amount": round(float(row["arrears_amount"]), 2),
        "notice_served_date": row["notice_served_date"],
        "cure_deadline_date": deadline,
        "is_cure_expired": is_cure_expired,
        "status": status,
        "court_case_number": row["court_case_number"] or "",
        "court_name": row["court_name"] or "",
        "filing_date": row["filing_date"],
        "hearing_date": row["hearing_date"],
        "attorney_name": row["attorney_name"] or "",
        "resolution_notes": row["resolution_notes"] or "",
        "closed_at": row["closed_at"],
        "payment_plans": plans,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_eviction_case(  # noqa: PLR0913
    unit_id: str,
    tenant_id: str,
    reason: str,
    *,
    notice_type: str = NoticeType.PAY_OR_QUIT.value,
    delivery_method: str = DeliveryMethod.CERTIFIED_MAIL.value,
    arrears_amount: float = 0.0,
    notice_served_date: str | None = None,
    cure_deadline_date: str | None = None,
    cure_days: int = DEFAULT_CURE_DAYS,
) -> dict[str, Any]:
    """Serve a statutory notice and open an eviction compliance case."""
    if not reason or not reason.strip():
        raise ValueError("reason is required")
    if arrears_amount < 0:
        raise ValueError("arrears_amount cannot be negative")
    if notice_type not in {n.value for n in NoticeType}:
        raise ValueError(f"Invalid notice_type '{notice_type}'")
    if delivery_method not in {d.value for d in DeliveryMethod}:
        raise ValueError(f"Invalid delivery_method '{delivery_method}'")

    conn = db_utils.get_db_connection()
    try:
        init_evictions_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM units WHERE id = ?", (unit_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Unit '{unit_id}' not found")
        cursor.execute("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        cid = _generate_case_id()
        now_iso = _now_iso()
        served = notice_served_date or _today_str()
        deadline = cure_deadline_date or _compute_cure_deadline(served, cure_days)
        cursor.execute(
            """
            INSERT INTO eviction_cases (
                id, unit_id, tenant_id, notice_type, delivery_method, reason,
                arrears_amount, notice_served_date, cure_deadline_date, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                unit_id,
                tenant_id,
                notice_type,
                delivery_method,
                reason.strip(),
                round(float(arrears_amount), 2),
                served,
                deadline,
                CaseStatus.CURE_WINDOW_ACTIVE.value,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (cid,))
        record = _row_to_case(cursor, cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("eviction.notice_served", record)
    return record


def get_eviction_case(case_id: str) -> dict[str, Any] | None:
    """Retrieve a single eviction compliance case by ID."""
    conn = db_utils.get_db_connection()
    try:
        init_evictions_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (case_id,))
        row = cursor.fetchone()
        return _row_to_case(cursor, row) if row else None
    finally:
        conn.close()


def list_eviction_cases(
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    notice_type: str | None = None,
) -> list[dict[str, Any]]:
    """List eviction compliance cases with optional filters."""
    conn = db_utils.get_db_connection()
    try:
        init_evictions_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM eviction_cases WHERE 1=1"
        params: list[Any] = []
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if notice_type:
            query += " AND notice_type = ?"
            params.append(notice_type)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [_row_to_case(cursor, r) for r in rows]
    finally:
        conn.close()


def update_eviction_case(case_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update mutable metadata on an eviction case."""
    allowed = {
        "arrears_amount",
        "cure_deadline_date",
        "status",
        "hearing_date",
        "attorney_name",
        "resolution_notes",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if "status" in filtered and filtered["status"] not in {s.value for s in CaseStatus}:
        raise ValueError(f"Invalid case status '{filtered['status']}'")
    if "arrears_amount" in filtered and float(filtered["arrears_amount"]) < 0:
        raise ValueError("arrears_amount cannot be negative")

    conn = db_utils.get_db_connection()
    try:
        init_evictions_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (case_id,))
        existing = cursor.fetchone()
        if existing is None:
            return None
        if not filtered:
            return _row_to_case(cursor, existing)

        filtered["updated_at"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        params = list(filtered.values()) + [case_id]
        cursor.execute(f"UPDATE eviction_cases SET {set_clause} WHERE id = ?", params)
        conn.commit()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (case_id,))
        return _row_to_case(cursor, cursor.fetchone())
    finally:
        conn.close()


def record_court_filing(  # noqa: PLR0913
    case_id: str,
    court_case_number: str,
    court_name: str,
    *,
    filing_date: str | None = None,
    hearing_date: str | None = None,
    attorney_name: str = "",
) -> dict[str, Any] | None:
    """Record formal court filing details and advance eviction case status."""
    if not court_case_number or not court_case_number.strip():
        raise ValueError("court_case_number is required")
    if not court_name or not court_name.strip():
        raise ValueError("court_name is required")

    conn = db_utils.get_db_connection()
    try:
        init_evictions_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (case_id,))
        if cursor.fetchone() is None:
            return None

        now_iso = _now_iso()
        next_status = (
            CaseStatus.HEARING_SCHEDULED.value if hearing_date else CaseStatus.FILED_IN_COURT.value
        )
        cursor.execute(
            """
            UPDATE eviction_cases
            SET court_case_number = ?, court_name = ?, filing_date = ?,
                hearing_date = ?, attorney_name = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                court_case_number.strip(),
                court_name.strip(),
                filing_date or _today_str(),
                hearing_date,
                attorney_name.strip(),
                next_status,
                now_iso,
                case_id,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (case_id,))
        updated = _row_to_case(cursor, cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("eviction.court_filed", updated)
    return updated


def close_eviction_case(
    case_id: str,
    status: str = CaseStatus.CURED_DISMISSED.value,
    resolution_notes: str = "",
) -> dict[str, Any] | None:
    """Close an eviction compliance case as cured/dismissed or evicted/closed."""
    valid_close = {
        CaseStatus.CURED_DISMISSED.value,
        CaseStatus.EVICTED_CLOSED.value,
        CaseStatus.JUDGMENT_GRANTED.value,
    }
    if status not in valid_close:
        raise ValueError(f"Invalid closing status '{status}'")

    conn = db_utils.get_db_connection()
    try:
        init_evictions_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (case_id,))
        if cursor.fetchone() is None:
            return None

        now_iso = _now_iso()
        cursor.execute(
            """
            UPDATE eviction_cases
            SET status = ?, resolution_notes = ?, closed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, resolution_notes.strip(), now_iso, now_iso, case_id),
        )
        conn.commit()
        cursor.execute("SELECT * FROM eviction_cases WHERE id = ?", (case_id,))
        updated = _row_to_case(cursor, cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("eviction.case_closed", updated)
    return updated
