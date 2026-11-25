"""Property owner portals, monthly disbursement statements, CapEx reserves, and approvals engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum

from api import db_utils


class OwnerStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ONBOARDING = "onboarding"


class DisbursementMethod(StrEnum):
    ACH = "ach"
    WIRE = "wire"
    CHECK = "check"


class StatementStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    DISBURSED = "disbursed"
    DISPUTED = "disputed"


class ApprovalCategory(StrEnum):
    CAPEX = "capex"
    MAJOR_REPAIR = "major_repair"
    VENDOR_CONTRACT = "vendor_contract"
    RENT_CONCESSION = "rent_concession"
    EVICTION_LEGAL = "eviction_legal"
    OTHER = "other"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MORE_INFO_REQUESTED = "more_info_requested"


MIN_SEEDED_OWNERS = 2
DEFAULT_MGMT_FEE_PCT = 8.0
MAX_MGMT_FEE_PCT = 50.0


def _generate_owner_id() -> str:
    return f"own_{secrets.token_hex(4)}"


def _generate_statement_id() -> str:
    return f"stm_{secrets.token_hex(4)}"


def _generate_approval_id() -> str:
    return f"apr_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _current_period_month() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m")


def init_owner_portal_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize SQLite tables, indexes, and deterministic seed data for owner portals."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS property_owners (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                entity_name TEXT NOT NULL DEFAULT '',
                management_fee_pct REAL NOT NULL DEFAULT 8.0,
                reserve_balance REAL NOT NULL DEFAULT 0.0,
                reserve_target REAL NOT NULL DEFAULT 5000.0,
                disbursement_method TEXT NOT NULL DEFAULT 'ach',
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS owner_statements (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL REFERENCES property_owners(id) ON DELETE CASCADE,
                period_month TEXT NOT NULL,
                gross_rent_collected REAL NOT NULL DEFAULT 0.0,
                other_income REAL NOT NULL DEFAULT 0.0,
                operating_expenses REAL NOT NULL DEFAULT 0.0,
                management_fee_amount REAL NOT NULL DEFAULT 0.0,
                reserve_contribution REAL NOT NULL DEFAULT 0.0,
                net_disbursement REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'issued',
                disbursed_at TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS owner_approvals (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL REFERENCES property_owners(id) ON DELETE CASCADE,
                unit_id TEXT REFERENCES units(id) ON DELETE SET NULL,
                category TEXT NOT NULL DEFAULT 'capex',
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                estimated_cost REAL NOT NULL,
                vendor_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                owner_decision_notes TEXT NOT NULL DEFAULT '',
                decided_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_owner_statements_owner "
            "ON owner_statements(owner_id, period_month)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_owner_approvals_owner_status "
            "ON owner_approvals(owner_id, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_owner_approvals_unit ON owner_approvals(unit_id)"
        )

        _seed_owner_portal_data(cursor)
        conn.commit()
    finally:
        if close_conn:
            conn.close()


def _seed_owner_portal_data(cursor: sqlite3.Cursor) -> None:
    """Seed initial property owners, monthly statement, and pending CapEx approval if empty."""
    cursor.execute("SELECT COUNT(*) FROM property_owners")
    if cursor.fetchone()[0] >= MIN_SEEDED_OWNERS:
        return

    now_iso = _now_iso()
    period = _current_period_month()

    cursor.execute(
        """
        INSERT OR IGNORE INTO property_owners (
            id, full_name, email, phone, entity_name, management_fee_pct,
            reserve_balance, reserve_target, disbursement_method, status,
            notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "own_seed_01",
            "Elena Rostova",
            "elena.rostova@rostovaholdings.example",
            "555-0301",
            "Rostova Holdings LLC",
            8.0,
            12500.0,
            15000.0,
            DisbursementMethod.ACH.value,
            OwnerStatus.ACTIVE.value,
            "Primary institutional owner for Main Tower residential units.",
            now_iso,
            now_iso,
        ),
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO property_owners (
            id, full_name, email, phone, entity_name, management_fee_pct,
            reserve_balance, reserve_target, disbursement_method, status,
            notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "own_seed_02",
            "Marcus Vance",
            "marcus.vance@vancetrust.example",
            "555-0302",
            "Vance Residential Trust",
            7.5,
            6800.0,
            10000.0,
            DisbursementMethod.WIRE.value,
            OwnerStatus.ACTIVE.value,
            "Prefers monthly wire disbursements on the 5th.",
            now_iso,
            now_iso,
        ),
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO owner_statements (
            id, owner_id, period_month, gross_rent_collected, other_income,
            operating_expenses, management_fee_amount, reserve_contribution,
            net_disbursement, status, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "stm_seed_01",
            "own_seed_01",
            period,
            18500.0,
            450.0,
            2150.0,
            1516.0,
            500.0,
            14784.0,
            StatementStatus.ISSUED.value,
            "Monthly operating statement ready for ACH disbursement.",
            now_iso,
            now_iso,
        ),
    )

    cursor.execute("SELECT id FROM units LIMIT 1")
    unit_row = cursor.fetchone()
    unit_id = str(unit_row[0]) if unit_row else None
    cursor.execute(
        """
        INSERT OR IGNORE INTO owner_approvals (
            id, owner_id, unit_id, category, title, description, estimated_cost,
            vendor_name, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "apr_seed_01",
            "own_seed_01",
            unit_id,
            ApprovalCategory.CAPEX.value,
            "High-Efficiency Heat Pump Condenser Replacement",
            "Replace aging 14-year-old HVAC condenser unit prior to peak summer load.",
            4850.0,
            "Apex HVAC Solutions",
            ApprovalStatus.PENDING.value,
            now_iso,
            now_iso,
        ),
    )
