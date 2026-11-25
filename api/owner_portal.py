"""Property owner portals, monthly disbursement statements, CapEx reserves, and approvals engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils, webhooks


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


def _row_to_owner(row: sqlite3.Row) -> dict[str, Any]:
    reserve_balance = round(float(row["reserve_balance"]), 2)
    reserve_target = round(float(row["reserve_target"]), 2)
    reserve_funded_pct = (
        round(min(100.0, (reserve_balance / reserve_target) * 100.0), 2)
        if reserve_target > 0
        else 100.0
    )
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "phone": row["phone"] or "",
        "entity_name": row["entity_name"] or "",
        "management_fee_pct": round(float(row["management_fee_pct"]), 2),
        "reserve_balance": reserve_balance,
        "reserve_target": reserve_target,
        "reserve_funded_pct": reserve_funded_pct,
        "disbursement_method": row["disbursement_method"],
        "status": row["status"],
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_statement(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "period_month": row["period_month"],
        "gross_rent_collected": round(float(row["gross_rent_collected"]), 2),
        "other_income": round(float(row["other_income"]), 2),
        "operating_expenses": round(float(row["operating_expenses"]), 2),
        "management_fee_amount": round(float(row["management_fee_amount"]), 2),
        "reserve_contribution": round(float(row["reserve_contribution"]), 2),
        "net_disbursement": round(float(row["net_disbursement"]), 2),
        "status": row["status"],
        "disbursed_at": row["disbursed_at"],
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_approval(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "unit_id": row["unit_id"],
        "category": row["category"],
        "title": row["title"],
        "description": row["description"] or "",
        "estimated_cost": round(float(row["estimated_cost"]), 2),
        "vendor_name": row["vendor_name"] or "",
        "status": row["status"],
        "owner_decision_notes": row["owner_decision_notes"] or "",
        "decided_at": row["decided_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_owner(  # noqa: PLR0913
    full_name: str,
    email: str,
    *,
    phone: str = "",
    entity_name: str = "",
    management_fee_pct: float = DEFAULT_MGMT_FEE_PCT,
    reserve_balance: float = 0.0,
    reserve_target: float = 5000.0,
    disbursement_method: str = DisbursementMethod.ACH.value,
    notes: str = "",
) -> dict[str, Any]:
    """Create a new property owner / holding entity profile."""
    if not full_name or not full_name.strip():
        raise ValueError("full_name is required")
    if not email or "@" not in email:
        raise ValueError("Valid email is required")
    if not (0.0 <= management_fee_pct <= MAX_MGMT_FEE_PCT):
        raise ValueError(f"management_fee_pct must be between 0 and {MAX_MGMT_FEE_PCT}")
    if reserve_balance < 0 or reserve_target < 0:
        raise ValueError("Reserve amounts cannot be negative")
    if disbursement_method not in {m.value for m in DisbursementMethod}:
        raise ValueError(f"Invalid disbursement_method '{disbursement_method}'")

    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        oid = _generate_owner_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO property_owners (
                id, full_name, email, phone, entity_name, management_fee_pct,
                reserve_balance, reserve_target, disbursement_method, status,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                oid,
                full_name.strip(),
                email.strip().lower(),
                phone.strip(),
                entity_name.strip(),
                round(float(management_fee_pct), 2),
                round(float(reserve_balance), 2),
                round(float(reserve_target), 2),
                disbursement_method,
                OwnerStatus.ACTIVE.value,
                notes.strip(),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM property_owners WHERE id = ?", (oid,))
        record = _row_to_owner(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("owner.created", record)
    return record


def get_owner(owner_id: str) -> dict[str, Any] | None:
    """Retrieve a single property owner by ID."""
    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM property_owners WHERE id = ?", (owner_id,))
        row = cursor.fetchone()
        return _row_to_owner(row) if row else None
    finally:
        conn.close()


def list_owners(status: str | None = None) -> list[dict[str, Any]]:
    """List property owners with optional status filter."""
    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM property_owners WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        return [_row_to_owner(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def update_owner(owner_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update mutable metadata on a property owner profile."""
    allowed = {
        "phone",
        "entity_name",
        "management_fee_pct",
        "reserve_balance",
        "reserve_target",
        "disbursement_method",
        "status",
        "notes",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if "status" in filtered and filtered["status"] not in {s.value for s in OwnerStatus}:
        raise ValueError(f"Invalid owner status '{filtered['status']}'")
    if "disbursement_method" in filtered and filtered["disbursement_method"] not in {
        m.value for m in DisbursementMethod
    }:
        raise ValueError(f"Invalid disbursement_method '{filtered['disbursement_method']}'")
    if "management_fee_pct" in filtered and not (
        0.0 <= float(filtered["management_fee_pct"]) <= MAX_MGMT_FEE_PCT
    ):
        raise ValueError(f"management_fee_pct must be between 0 and {MAX_MGMT_FEE_PCT}")

    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM property_owners WHERE id = ?", (owner_id,))
        existing = cursor.fetchone()
        if existing is None:
            return None
        if not filtered:
            return _row_to_owner(existing)

        filtered["updated_at"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        params = list(filtered.values()) + [owner_id]
        cursor.execute(f"UPDATE property_owners SET {set_clause} WHERE id = ?", params)
        conn.commit()
        cursor.execute("SELECT * FROM property_owners WHERE id = ?", (owner_id,))
        return _row_to_owner(cursor.fetchone())
    finally:
        conn.close()


def render_statement_markdown(owner: dict[str, Any], statement: dict[str, Any]) -> str:
    """Render a formatted monthly owner financial disbursement statement in Markdown."""
    total_income = round(statement["gross_rent_collected"] + statement["other_income"], 2)
    lines = [
        f"# Monthly Owner Financial Statement — {statement['period_month']} ({statement['id']})",
        "",
        f"- **Owner:** {owner['full_name']}"
        + (f" ({owner['entity_name']})" if owner.get("entity_name") else ""),
        f"- **Disbursement Method:** {owner['disbursement_method'].upper()}",
        f"- **Statement Status:** {statement['status'].upper()}",
        "",
        "## Cash Flow Summary",
        f"- Gross Rent Collected: ${statement['gross_rent_collected']:,.2f}",
        f"- Other Income: ${statement['other_income']:,.2f}",
        f"- **Total Gross Income:** ${total_income:,.2f}",
        f"- Operating Expenses: -${statement['operating_expenses']:,.2f}",
        f"- Management Fee ({owner['management_fee_pct']}%): "
        f"-${statement['management_fee_amount']:,.2f}",
        f"- CapEx Reserve Contribution: -${statement['reserve_contribution']:,.2f}",
        f"- **Net Owner Disbursement:** **${statement['net_disbursement']:,.2f}**",
    ]
    if statement.get("notes"):
        lines.extend(["", f"**Notes:** {statement['notes']}"])
    return "\n".join(lines)


def generate_owner_statement(  # noqa: PLR0913
    owner_id: str,
    period_month: str,
    gross_rent_collected: float,
    *,
    other_income: float = 0.0,
    operating_expenses: float = 0.0,
    reserve_contribution: float = 0.0,
    notes: str = "",
) -> dict[str, Any]:
    """Generate a monthly owner disbursement statement with auto-computed management fee."""
    if gross_rent_collected < 0 or other_income < 0 or operating_expenses < 0:
        raise ValueError("Financial amounts cannot be negative")
    if reserve_contribution < 0:
        raise ValueError("reserve_contribution cannot be negative")
    if not period_month or not period_month.strip():
        raise ValueError("period_month is required")

    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM property_owners WHERE id = ?", (owner_id,))
        owner_row = cursor.fetchone()
        if owner_row is None:
            raise ValueError(f"Owner '{owner_id}' not found")
        owner = _row_to_owner(owner_row)

        total_income = float(gross_rent_collected) + float(other_income)
        mgmt_fee = round(total_income * (owner["management_fee_pct"] / 100.0), 2)
        net_payout = round(
            total_income - float(operating_expenses) - mgmt_fee - float(reserve_contribution),
            2,
        )

        sid = _generate_statement_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO owner_statements (
                id, owner_id, period_month, gross_rent_collected, other_income,
                operating_expenses, management_fee_amount, reserve_contribution,
                net_disbursement, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                owner_id,
                period_month.strip(),
                round(float(gross_rent_collected), 2),
                round(float(other_income), 2),
                round(float(operating_expenses), 2),
                mgmt_fee,
                round(float(reserve_contribution), 2),
                net_payout,
                StatementStatus.ISSUED.value,
                notes.strip(),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM owner_statements WHERE id = ?", (sid,))
        stmt = _row_to_statement(cursor.fetchone())
    finally:
        conn.close()

    result = {**stmt, "statement_markdown": render_statement_markdown(owner, stmt)}
    webhooks.dispatch_event("owner.statement_generated", stmt)
    return result


def get_owner_statement(statement_id: str) -> dict[str, Any] | None:
    """Retrieve a single owner statement with rendered Markdown."""
    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM owner_statements WHERE id = ?", (statement_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        stmt = _row_to_statement(row)
        cursor.execute("SELECT * FROM property_owners WHERE id = ?", (stmt["owner_id"],))
        owner = _row_to_owner(cursor.fetchone())
        return {**stmt, "statement_markdown": render_statement_markdown(owner, stmt)}
    finally:
        conn.close()


def list_owner_statements(
    owner_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List owner monthly financial statements with optional filters."""
    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM owner_statements WHERE 1=1"
        params: list[Any] = []
        if owner_id:
            query += " AND owner_id = ?"
            params.append(owner_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY period_month DESC, created_at DESC"
        cursor.execute(query, params)
        return [_row_to_statement(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def disburse_owner_statement(
    statement_id: str,
    *,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Mark an owner statement disbursed and credit reserve_contribution to reserve_balance."""
    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM owner_statements WHERE id = ?", (statement_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        now_iso = _now_iso()
        updated_notes = notes.strip() if notes is not None else (row["notes"] or "")
        was_disbursed = row["status"] == StatementStatus.DISBURSED.value
        cursor.execute(
            """
            UPDATE owner_statements
            SET status = ?, disbursed_at = COALESCE(disbursed_at, ?), notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (StatementStatus.DISBURSED.value, now_iso, updated_notes, now_iso, statement_id),
        )
        if not was_disbursed and float(row["reserve_contribution"] or 0.0) > 0:
            cursor.execute(
                """
                UPDATE property_owners
                SET reserve_balance = ROUND(reserve_balance + ?, 2), updated_at = ?
                WHERE id = ?
                """,
                (float(row["reserve_contribution"]), now_iso, row["owner_id"]),
            )
        conn.commit()
        cursor.execute("SELECT * FROM owner_statements WHERE id = ?", (statement_id,))
        updated = _row_to_statement(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("owner.disbursement_sent", updated)
    return updated


def create_approval_request(  # noqa: PLR0913
    owner_id: str,
    title: str,
    estimated_cost: float,
    *,
    unit_id: str | None = None,
    category: str = ApprovalCategory.CAPEX.value,
    description: str = "",
    vendor_name: str = "",
) -> dict[str, Any]:
    """Submit a CapEx or major repair approval request to a property owner."""
    if not title or not title.strip():
        raise ValueError("title is required")
    if estimated_cost <= 0:
        raise ValueError("estimated_cost must be greater than 0")
    if category not in {c.value for c in ApprovalCategory}:
        raise ValueError(f"Invalid approval category '{category}'")

    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM property_owners WHERE id = ?", (owner_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Owner '{owner_id}' not found")
        if unit_id:
            cursor.execute("SELECT id FROM units WHERE id = ?", (unit_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Unit '{unit_id}' not found")

        aid = _generate_approval_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO owner_approvals (
                id, owner_id, unit_id, category, title, description, estimated_cost,
                vendor_name, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                owner_id,
                unit_id,
                category,
                title.strip(),
                description.strip(),
                round(float(estimated_cost), 2),
                vendor_name.strip(),
                ApprovalStatus.PENDING.value,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM owner_approvals WHERE id = ?", (aid,))
        approval = _row_to_approval(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("owner.approval_requested", approval)
    return approval


def list_approval_requests(
    owner_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List owner CapEx/major repair approval requests with optional filters."""
    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM owner_approvals WHERE 1=1"
        params: list[Any] = []
        if owner_id:
            query += " AND owner_id = ?"
            params.append(owner_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        return [_row_to_approval(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def decide_approval_request(
    approval_id: str,
    decision: str,
    *,
    owner_decision_notes: str = "",
) -> dict[str, Any] | None:
    """Approve, reject, or request more info on an owner CapEx approval request."""
    valid_decisions = {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
        ApprovalStatus.MORE_INFO_REQUESTED.value,
    }
    if decision not in valid_decisions:
        raise ValueError(f"Invalid approval decision '{decision}'")

    conn = db_utils.get_db_connection()
    try:
        init_owner_portal_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM owner_approvals WHERE id = ?", (approval_id,))
        if cursor.fetchone() is None:
            return None

        now_iso = _now_iso()
        decided_at = (
            now_iso
            if decision in (ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value)
            else None
        )
        cursor.execute(
            """
            UPDATE owner_approvals
            SET status = ?, owner_decision_notes = ?, decided_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (decision, owner_decision_notes.strip(), decided_at, now_iso, approval_id),
        )
        conn.commit()
        cursor.execute("SELECT * FROM owner_approvals WHERE id = ?", (approval_id,))
        updated = _row_to_approval(cursor.fetchone())
    finally:
        conn.close()

    if decision == ApprovalStatus.APPROVED.value:
        webhooks.dispatch_event("owner.approval_approved", updated)
    elif decision == ApprovalStatus.REJECTED.value:
        webhooks.dispatch_event("owner.approval_rejected", updated)
    return updated


def get_owner_summary(owner_id: str) -> dict[str, Any] | None:
    """Summarize statements, disbursements, reserves, and approvals for an owner."""
    owner = get_owner(owner_id)
    if owner is None:
        return None
    statements = list_owner_statements(owner_id=owner_id)
    approvals = list_approval_requests(owner_id=owner_id)
    total_disbursed = round(
        sum(
            s["net_disbursement"]
            for s in statements
            if s["status"] == StatementStatus.DISBURSED.value
        ),
        2,
    )
    pending_disbursements = round(
        sum(
            s["net_disbursement"]
            for s in statements
            if s["status"] in (StatementStatus.DRAFT.value, StatementStatus.ISSUED.value)
        ),
        2,
    )
    pending_approvals = [a for a in approvals if a["status"] == ApprovalStatus.PENDING.value]
    return {
        "owner": owner,
        "total_statements": len(statements),
        "total_disbursed": total_disbursed,
        "pending_disbursements": pending_disbursements,
        "pending_approvals_count": len(pending_approvals),
        "pending_capex_exposure": round(sum(a["estimated_cost"] for a in pending_approvals), 2),
        "statements": statements,
        "approvals": approvals,
    }


def get_unit_owner_approvals_summary(unit_id: str) -> dict[str, Any]:
    """Summarize pending and recent owner CapEx/major repair approvals for a unit."""
    approvals = list_approval_requests(unit_id=unit_id)
    pending = [a for a in approvals if a["status"] == ApprovalStatus.PENDING.value]
    latest = approvals[0] if approvals else None
    if pending:
        capex_status = "awaiting_owner_approval"
    elif latest and latest["status"] == ApprovalStatus.APPROVED.value:
        capex_status = "approved"
    elif latest and latest["status"] == ApprovalStatus.REJECTED.value:
        capex_status = "rejected"
    else:
        capex_status = "none"
    return {
        "unit_id": unit_id,
        "total_approvals": len(approvals),
        "pending_count": len(pending),
        "pending_exposure": round(sum(a["estimated_cost"] for a in pending), 2),
        "capex_status": capex_status,
        "latest_approval": latest,
        "approvals": approvals,
    }


def get_owner_portal_metrics_summary() -> dict[str, Any]:
    """Compute portfolio-wide owner portal reserves, disbursements, and CapEx KPIs."""
    owners = list_owners()
    statements = list_owner_statements()
    approvals = list_approval_requests()

    active_owners = sum(1 for o in owners if o["status"] == OwnerStatus.ACTIVE.value)
    total_reserve_balance = round(sum(o["reserve_balance"] for o in owners), 2)
    total_reserve_target = round(sum(o["reserve_target"] for o in owners), 2)
    total_disbursed = round(
        sum(
            s["net_disbursement"]
            for s in statements
            if s["status"] == StatementStatus.DISBURSED.value
        ),
        2,
    )
    total_mgmt_fees = round(sum(s["management_fee_amount"] for s in statements), 2)
    pending_statements = sum(
        1
        for s in statements
        if s["status"] in (StatementStatus.DRAFT.value, StatementStatus.ISSUED.value)
    )
    pending_approvals = [a for a in approvals if a["status"] == ApprovalStatus.PENDING.value]
    approved_count = sum(1 for a in approvals if a["status"] == ApprovalStatus.APPROVED.value)
    rejected_count = sum(1 for a in approvals if a["status"] == ApprovalStatus.REJECTED.value)
    decided = approved_count + rejected_count
    approval_rate_pct = round((approved_count / decided) * 100.0, 2) if decided > 0 else 100.0

    return {
        "total_owners": len(owners),
        "active_owners": active_owners,
        "total_reserve_balance": total_reserve_balance,
        "total_reserve_target": total_reserve_target,
        "total_statements": len(statements),
        "pending_statements": pending_statements,
        "total_net_disbursed": total_disbursed,
        "total_management_fees": total_mgmt_fees,
        "pending_approvals_count": len(pending_approvals),
        "pending_capex_exposure": round(sum(a["estimated_cost"] for a in pending_approvals), 2),
        "approval_rate_pct": approval_rate_pct,
    }
