"""Security deposit escrow, itemized deductions, statutory disposition, and dispute engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum

from api import db_utils


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

