"""Security deposit escrow, itemized deductions, statutory disposition, and dispute engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils, webhooks


class DepositStatus(StrEnum):
    HELD = "held"
    ITEMIZED_PENDING = "itemized_pending"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"
    FORFEITED = "forfeited"
    DISPUTED = "disputed"


class DepositType(StrEnum):
    STANDARD_SECURITY = "standard_security"
    PET_DEPOSIT = "pet_deposit"
    KEY_DEPOSIT = "key_deposit"
    LAST_MONTH_RENT = "last_month_rent"


class DeductionCategory(StrEnum):
    CLEANING = "cleaning"
    DAMAGE_REPAIR = "damage_repair"
    UNPAID_RENT = "unpaid_rent"
    KEY_REPLACEMENT = "key_replacement"
    UTILITY_BALANCE = "utility_balance"
    LEASE_BREAK_FEE = "lease_break_fee"
    OTHER = "other"


class RefundMethod(StrEnum):
    CHECK = "check"
    ACH = "ach"
    DIRECT_DEPOSIT = "direct_deposit"
    APPLIED_TO_BALANCE = "applied_to_balance"


class DisputeStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED_ADJUSTED = "resolved_adjusted"
    RESOLVED_UPHELD = "resolved_upheld"


DEFAULT_STATUTORY_DAYS = 21
MIN_SEEDED_DEPOSITS = 2


def _generate_deposit_id() -> str:
    return f"dep_{secrets.token_hex(4)}"


def _generate_deduction_id() -> str:
    return f"ded_{secrets.token_hex(4)}"


def _generate_dispute_id() -> str:
    return f"dsp_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _today_str() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m-%d")


def _compute_deadline(move_out_date: str | None, days: int = DEFAULT_STATUTORY_DAYS) -> str | None:
    if not move_out_date:
        return None
    try:
        dt = datetime.date.fromisoformat(move_out_date[:10])
    except ValueError:
        return None
    return (dt + datetime.timedelta(days=days)).isoformat()


def init_security_deposits_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize SQLite tables, indexes, and initial seed data for security deposits."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS security_deposits (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                tenant_id TEXT REFERENCES tenants(id) ON DELETE SET NULL,
                deposit_type TEXT NOT NULL DEFAULT 'standard_security',
                principal_amount REAL NOT NULL,
                accrued_interest REAL NOT NULL DEFAULT 0.0,
                escrow_account_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'held',
                received_date TEXT NOT NULL,
                move_out_date TEXT,
                statutory_deadline_date TEXT,
                statement_issued_at TEXT,
                refund_amount REAL,
                refund_method TEXT,
                refund_issued_at TEXT,
                forwarding_address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS deposit_deductions (
                id TEXT PRIMARY KEY,
                deposit_id TEXT NOT NULL REFERENCES security_deposits(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                evidence_ref TEXT NOT NULL DEFAULT '',
                approved INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS deposit_disputes (
                id TEXT PRIMARY KEY,
                deposit_id TEXT NOT NULL REFERENCES security_deposits(id) ON DELETE CASCADE,
                tenant_id TEXT REFERENCES tenants(id) ON DELETE SET NULL,
                disputed_amount REAL NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                resolution_notes TEXT NOT NULL DEFAULT '',
                adjusted_refund_amount REAL,
                opened_at TEXT NOT NULL,
                resolved_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sec_dep_unit_status "
            "ON security_deposits(unit_id, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sec_dep_tenant ON security_deposits(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dep_deductions_dep ON deposit_deductions(deposit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dep_disputes_dep ON deposit_disputes(deposit_id)"
        )

        _seed_deposits_data(cursor)
        conn.commit()
    finally:
        if close_conn:
            conn.close()


def _seed_deposits_data(cursor: sqlite3.Cursor) -> None:
    """Seed initial security deposits, deductions, and disputes if empty."""
    cursor.execute("SELECT COUNT(*) FROM security_deposits")
    if cursor.fetchone()[0] >= MIN_SEEDED_DEPOSITS:
        return

    cursor.execute("SELECT id, unit_id FROM tenants LIMIT 2")
    tenants = cursor.fetchall()
    if not tenants:
        return

    now_iso = _now_iso()
    received_str = (datetime.datetime.now(UTC) - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    move_out_str = (datetime.datetime.now(UTC) - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    deadline_str = (datetime.datetime.now(UTC) + datetime.timedelta(days=16)).strftime("%Y-%m-%d")

    t1_id, u1_id = tenants[0][0], tenants[0][1]
    cursor.execute(
        """
        INSERT OR IGNORE INTO security_deposits (
            id, unit_id, tenant_id, deposit_type, principal_amount, accrued_interest,
            escrow_account_ref, status, received_date, move_out_date,
            statutory_deadline_date, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "dep_seed_101",
            u1_id,
            t1_id,
            DepositType.STANDARD_SECURITY.value,
            2400.0,
            18.50,
            "ESC-2026-0101",
            DepositStatus.HELD.value,
            received_str,
            None,
            None,
            "Standard 1-month security deposit held in interest-bearing escrow.",
            now_iso,
            now_iso,
        ),
    )

    if len(tenants) > 1:
        t2_id, u2_id = tenants[1][0], tenants[1][1]
        cursor.execute(
            """
            INSERT OR IGNORE INTO security_deposits (
                id, unit_id, tenant_id, deposit_type, principal_amount, accrued_interest,
                escrow_account_ref, status, received_date, move_out_date,
                statutory_deadline_date, statement_issued_at, forwarding_address,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dep_seed_102",
                u2_id,
                t2_id,
                DepositType.STANDARD_SECURITY.value,
                1800.0,
                12.00,
                "ESC-2026-0102",
                DepositStatus.ITEMIZED_PENDING.value,
                received_str,
                move_out_str,
                deadline_str,
                now_iso,
                "420 Maple Ave, Apt 5B, Austin, TX 78701",
                "Move-out inspection completed; itemized statement issued pending refund.",
                now_iso,
                now_iso,
            ),
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO deposit_deductions (
                id, deposit_id, category, description, amount, evidence_ref, approved, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ded_seed_01",
                "dep_seed_102",
                DeductionCategory.CLEANING.value,
                "Deep oven and carpet steam cleaning beyond normal wear and tear.",
                185.00,
                "INSP-MOVE-OUT-102",
                1,
                now_iso,
            ),
        )


def _row_to_deduction(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "deposit_id": row["deposit_id"],
        "category": row["category"],
        "description": row["description"],
        "amount": round(float(row["amount"]), 2),
        "evidence_ref": row["evidence_ref"] or "",
        "approved": bool(row["approved"]),
        "created_at": row["created_at"],
    }


def _row_to_dispute(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "deposit_id": row["deposit_id"],
        "tenant_id": row["tenant_id"],
        "disputed_amount": round(float(row["disputed_amount"]), 2),
        "reason": row["reason"],
        "status": row["status"],
        "resolution_notes": row["resolution_notes"] or "",
        "adjusted_refund_amount": (
            round(float(row["adjusted_refund_amount"]), 2)
            if row["adjusted_refund_amount"] is not None
            else None
        ),
        "opened_at": row["opened_at"],
        "resolved_at": row["resolved_at"],
        "updated_at": row["updated_at"],
    }


def _hydrate_deposit(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    dep_id = row["id"]
    cursor.execute(
        "SELECT * FROM deposit_deductions WHERE deposit_id = ? ORDER BY created_at ASC",
        (dep_id,),
    )
    deductions = [_row_to_deduction(r) for r in cursor.fetchall()]

    cursor.execute(
        "SELECT * FROM deposit_disputes WHERE deposit_id = ? ORDER BY opened_at DESC",
        (dep_id,),
    )
    disputes = [_row_to_dispute(r) for r in cursor.fetchall()]

    principal = round(float(row["principal_amount"]), 2)
    interest = round(float(row["accrued_interest"]), 2)
    total_deductions = round(sum(d["amount"] for d in deductions if d["approved"]), 2)
    net_refundable = max(0.0, round(principal + interest - total_deductions, 2))

    deadline = row["statutory_deadline_date"]
    status = row["status"]
    is_overdue = bool(
        deadline
        and status in (DepositStatus.HELD.value, DepositStatus.ITEMIZED_PENDING.value)
        and deadline < _today_str()
    )

    return {
        "id": dep_id,
        "unit_id": row["unit_id"],
        "tenant_id": row["tenant_id"],
        "deposit_type": row["deposit_type"],
        "principal_amount": principal,
        "accrued_interest": interest,
        "total_deductions": total_deductions,
        "net_refundable": net_refundable,
        "escrow_account_ref": row["escrow_account_ref"] or "",
        "status": status,
        "received_date": row["received_date"],
        "move_out_date": row["move_out_date"],
        "statutory_deadline_date": deadline,
        "is_overdue": is_overdue,
        "statement_issued_at": row["statement_issued_at"],
        "refund_amount": (
            round(float(row["refund_amount"]), 2) if row["refund_amount"] is not None else None
        ),
        "refund_method": row["refund_method"],
        "refund_issued_at": row["refund_issued_at"],
        "forwarding_address": row["forwarding_address"] or "",
        "notes": row["notes"] or "",
        "deductions": deductions,
        "disputes": disputes,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_deposit(  # noqa: PLR0913
    unit_id: str,
    principal_amount: float,
    *,
    tenant_id: str | None = None,
    deposit_type: str = DepositType.STANDARD_SECURITY.value,
    accrued_interest: float = 0.0,
    escrow_account_ref: str = "",
    received_date: str | None = None,
    move_out_date: str | None = None,
    statutory_deadline_date: str | None = None,
    forwarding_address: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Create a new security deposit escrow record."""
    if principal_amount <= 0:
        raise ValueError("principal_amount must be greater than 0")
    if accrued_interest < 0:
        raise ValueError("accrued_interest cannot be negative")

    valid_types = {t.value for t in DepositType}
    if deposit_type not in valid_types:
        raise ValueError(f"Invalid deposit_type '{deposit_type}'")

    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM units WHERE id = ?", (unit_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Unit '{unit_id}' not found")

        if tenant_id:
            cursor.execute("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Tenant '{tenant_id}' not found")

        dep_id = _generate_deposit_id()
        now_iso = _now_iso()
        rec_date = received_date or _today_str()
        deadline = statutory_deadline_date or _compute_deadline(move_out_date)

        cursor.execute(
            """
            INSERT INTO security_deposits (
                id, unit_id, tenant_id, deposit_type, principal_amount, accrued_interest,
                escrow_account_ref, status, received_date, move_out_date,
                statutory_deadline_date, forwarding_address, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dep_id,
                unit_id,
                tenant_id,
                deposit_type,
                round(float(principal_amount), 2),
                round(float(accrued_interest), 2),
                escrow_account_ref.strip(),
                DepositStatus.HELD.value,
                rec_date,
                move_out_date,
                deadline,
                forwarding_address.strip(),
                notes.strip(),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (dep_id,))
        record = _hydrate_deposit(cursor, cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("deposit.created", record)
    return record


def get_deposit(deposit_id: str) -> dict[str, Any] | None:
    """Fetch a single security deposit with its deductions and disputes."""
    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _hydrate_deposit(cursor, row)
    finally:
        conn.close()


def list_deposits(
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    deposit_type: str | None = None,
) -> list[dict[str, Any]]:
    """List security deposits with optional filters."""
    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM security_deposits WHERE 1=1"
        params: list[Any] = []
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if deposit_type:
            query += " AND deposit_type = ?"
            params.append(deposit_type)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [_hydrate_deposit(cursor, r) for r in rows]
    finally:
        conn.close()


def update_deposit(deposit_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update mutable metadata fields on a security deposit."""
    allowed_fields = {
        "accrued_interest",
        "escrow_account_ref",
        "status",
        "move_out_date",
        "statutory_deadline_date",
        "forwarding_address",
        "notes",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}
    if "status" in filtered:
        valid_statuses = {s.value for s in DepositStatus}
        if filtered["status"] not in valid_statuses:
            raise ValueError(f"Invalid status '{filtered['status']}'")
    if "accrued_interest" in filtered and float(filtered["accrued_interest"]) < 0:
        raise ValueError("accrued_interest cannot be negative")

    if "move_out_date" in filtered and "statutory_deadline_date" not in filtered:
        computed = _compute_deadline(str(filtered["move_out_date"]))
        if computed:
            filtered["statutory_deadline_date"] = computed

    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        existing = cursor.fetchone()
        if existing is None:
            return None

        if not filtered:
            return _hydrate_deposit(cursor, existing)

        filtered["updated_at"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        params = list(filtered.values()) + [deposit_id]
        cursor.execute(f"UPDATE security_deposits SET {set_clause} WHERE id = ?", params)
        conn.commit()

        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        return _hydrate_deposit(cursor, cursor.fetchone())
    finally:
        conn.close()

