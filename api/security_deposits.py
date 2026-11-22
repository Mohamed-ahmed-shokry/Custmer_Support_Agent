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


def add_deduction(  # noqa: PLR0913
    deposit_id: str,
    category: str,
    description: str,
    amount: float,
    *,
    evidence_ref: str = "",
    approved: bool = True,
) -> dict[str, Any]:
    """Attach an itemized move-out deduction to a security deposit."""
    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    if not description or not description.strip():
        raise ValueError("description is required")

    valid_categories = {c.value for c in DeductionCategory}
    if category not in valid_categories:
        raise ValueError(f"Invalid deduction category '{category}'")

    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM security_deposits WHERE id = ?", (deposit_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Security deposit '{deposit_id}' not found")

        ded_id = _generate_deduction_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO deposit_deductions (
                id, deposit_id, category, description, amount, evidence_ref, approved, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ded_id,
                deposit_id,
                category,
                description.strip(),
                round(float(amount), 2),
                evidence_ref.strip(),
                1 if approved else 0,
                now_iso,
            ),
        )
        cursor.execute(
            "UPDATE security_deposits SET updated_at = ? WHERE id = ?",
            (now_iso, deposit_id),
        )
        conn.commit()

        cursor.execute("SELECT * FROM deposit_deductions WHERE id = ?", (ded_id,))
        deduction = _row_to_deduction(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("deposit.deduction_added", deduction)
    return deduction


def list_deductions(deposit_id: str) -> list[dict[str, Any]]:
    """List itemized deductions for a security deposit."""
    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM deposit_deductions WHERE deposit_id = ? ORDER BY created_at ASC",
            (deposit_id,),
        )
        return [_row_to_deduction(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def delete_deduction(deduction_id: str) -> bool:
    """Delete an itemized deduction by ID."""
    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT deposit_id FROM deposit_deductions WHERE id = ?",
            (deduction_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return False
        deposit_id = row["deposit_id"]
        cursor.execute("DELETE FROM deposit_deductions WHERE id = ?", (deduction_id,))
        cursor.execute(
            "UPDATE security_deposits SET updated_at = ? WHERE id = ?",
            (_now_iso(), deposit_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def render_disposition_markdown(deposit: dict[str, Any]) -> str:
    """Render a statutory itemized security deposit disposition statement in Markdown."""
    lines = [
        f"# Security Deposit Itemized Disposition Statement ({deposit['id']})",
        "",
        f"- **Unit:** {deposit['unit_id']}",
        f"- **Tenant:** {deposit.get('tenant_id') or 'N/A'}",
        f"- **Escrow Reference:** {deposit.get('escrow_account_ref') or 'N/A'}",
        f"- **Deposit Principal:** ${deposit['principal_amount']:,.2f}",
        f"- **Accrued Interest:** ${deposit['accrued_interest']:,.2f}",
        f"- **Total Approved Deductions:** ${deposit['total_deductions']:,.2f}",
        f"- **Net Refundable Amount:** ${deposit['net_refundable']:,.2f}",
        f"- **Statutory Deadline:** {deposit.get('statutory_deadline_date') or 'N/A'}",
        "",
        "## Itemized Deductions",
    ]
    deductions = deposit.get("deductions") or []
    if not deductions:
        lines.append("- None ($0.00)")
    else:
        for ded in deductions:
            ev = f" (Ref: {ded['evidence_ref']})" if ded.get("evidence_ref") else ""
            lines.append(
                f"- **{ded['category']}**: {ded['description']} — ${ded['amount']:,.2f}{ev}"
            )
    if deposit.get("forwarding_address"):
        lines.extend(["", f"**Forwarding Address:** {deposit['forwarding_address']}"])
    return "\n".join(lines)


def issue_disposition_statement(
    deposit_id: str,
    *,
    move_out_date: str | None = None,
    forwarding_address: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Issue a statutory itemized disposition statement for a security deposit."""
    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        now_iso = _now_iso()
        resolved_move_out = move_out_date or row["move_out_date"] or _today_str()
        deadline = row["statutory_deadline_date"] or _compute_deadline(resolved_move_out)
        fwd = (
            forwarding_address.strip()
            if forwarding_address is not None
            else (row["forwarding_address"] or "")
        )
        updated_notes = notes.strip() if notes is not None else (row["notes"] or "")

        hydrated = _hydrate_deposit(cursor, row)
        next_status = (
            DepositStatus.FORFEITED.value
            if hydrated["net_refundable"] <= 0 and hydrated["total_deductions"] > 0
            else DepositStatus.ITEMIZED_PENDING.value
        )

        cursor.execute(
            """
            UPDATE security_deposits
            SET status = ?, move_out_date = ?, statutory_deadline_date = ?,
                statement_issued_at = ?, forwarding_address = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_status,
                resolved_move_out,
                deadline,
                now_iso,
                fwd,
                updated_notes,
                now_iso,
                deposit_id,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        updated = _hydrate_deposit(cursor, cursor.fetchone())
    finally:
        conn.close()

    statement_md = render_disposition_markdown(updated)
    result = {**updated, "statement_markdown": statement_md}
    webhooks.dispatch_event("deposit.statement_issued", updated)
    return result


def issue_refund(
    deposit_id: str,
    refund_method: str,
    *,
    forwarding_address: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Record security deposit refund disbursement and finalize deposit status."""
    valid_methods = {m.value for m in RefundMethod}
    if refund_method not in valid_methods:
        raise ValueError(f"Invalid refund_method '{refund_method}'")

    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        hydrated = _hydrate_deposit(cursor, row)
        net_refund = hydrated["net_refundable"]
        if net_refund <= 0:
            next_status = DepositStatus.FORFEITED.value
        elif hydrated["total_deductions"] > 0:
            next_status = DepositStatus.PARTIAL_REFUND.value
        else:
            next_status = DepositStatus.REFUNDED.value

        now_iso = _now_iso()
        fwd = (
            forwarding_address.strip()
            if forwarding_address is not None
            else (row["forwarding_address"] or "")
        )
        updated_notes = notes.strip() if notes is not None else (row["notes"] or "")

        cursor.execute(
            """
            UPDATE security_deposits
            SET status = ?, refund_amount = ?, refund_method = ?,
                refund_issued_at = ?, forwarding_address = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_status,
                net_refund,
                refund_method,
                now_iso,
                fwd,
                updated_notes,
                now_iso,
                deposit_id,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        updated = _hydrate_deposit(cursor, cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("deposit.refund_issued", updated)
    return updated


def open_dispute(
    deposit_id: str,
    disputed_amount: float,
    reason: str,
    *,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Open a formal resident dispute against security deposit deductions."""
    if disputed_amount <= 0:
        raise ValueError("disputed_amount must be greater than 0")
    if not reason or not reason.strip():
        raise ValueError("reason is required")

    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_deposits WHERE id = ?", (deposit_id,))
        dep_row = cursor.fetchone()
        if dep_row is None:
            raise ValueError(f"Security deposit '{deposit_id}' not found")

        resolved_tenant = tenant_id or dep_row["tenant_id"]
        dsp_id = _generate_dispute_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO deposit_disputes (
                id, deposit_id, tenant_id, disputed_amount, reason, status,
                resolution_notes, opened_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dsp_id,
                deposit_id,
                resolved_tenant,
                round(float(disputed_amount), 2),
                reason.strip(),
                DisputeStatus.OPEN.value,
                "",
                now_iso,
                now_iso,
            ),
        )
        cursor.execute(
            "UPDATE security_deposits SET status = ?, updated_at = ? WHERE id = ?",
            (DepositStatus.DISPUTED.value, now_iso, deposit_id),
        )
        conn.commit()

        cursor.execute("SELECT * FROM deposit_disputes WHERE id = ?", (dsp_id,))
        dispute = _row_to_dispute(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("deposit.dispute_opened", dispute)
    return dispute


def list_disputes(
    deposit_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List deposit disputes with optional deposit or status filters."""
    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM deposit_disputes WHERE 1=1"
        params: list[Any] = []
        if deposit_id:
            query += " AND deposit_id = ?"
            params.append(deposit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY opened_at DESC"
        cursor.execute(query, params)
        return [_row_to_dispute(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def resolve_dispute(
    dispute_id: str,
    status: str,
    resolution_notes: str = "",
    *,
    adjusted_refund_amount: float | None = None,
) -> dict[str, Any] | None:
    """Resolve an open deposit dispute and optionally adjust the deposit refund."""
    valid_resolutions = {
        DisputeStatus.UNDER_REVIEW.value,
        DisputeStatus.RESOLVED_ADJUSTED.value,
        DisputeStatus.RESOLVED_UPHELD.value,
    }
    if status not in valid_resolutions:
        raise ValueError(f"Invalid dispute resolution status '{status}'")
    if adjusted_refund_amount is not None and adjusted_refund_amount < 0:
        raise ValueError("adjusted_refund_amount cannot be negative")

    conn = db_utils.get_db_connection()
    try:
        init_security_deposits_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deposit_disputes WHERE id = ?", (dispute_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        now_iso = _now_iso()
        is_final = status in (
            DisputeStatus.RESOLVED_ADJUSTED.value,
            DisputeStatus.RESOLVED_UPHELD.value,
        )
        resolved_at = now_iso if is_final else None
        adj_val = (
            round(float(adjusted_refund_amount), 2)
            if adjusted_refund_amount is not None
            else row["adjusted_refund_amount"]
        )

        cursor.execute(
            """
            UPDATE deposit_disputes
            SET status = ?, resolution_notes = ?, adjusted_refund_amount = ?,
                resolved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, resolution_notes.strip(), adj_val, resolved_at, now_iso, dispute_id),
        )

        if resolved_at is not None:
            deposit_id = row["deposit_id"]
            if adj_val is not None:
                cursor.execute(
                    """
                    UPDATE security_deposits
                    SET status = ?, refund_amount = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (DepositStatus.ITEMIZED_PENDING.value, adj_val, now_iso, deposit_id),
                )
            else:
                cursor.execute(
                    "UPDATE security_deposits SET status = ?, updated_at = ? WHERE id = ?",
                    (DepositStatus.ITEMIZED_PENDING.value, now_iso, deposit_id),
                )

        conn.commit()
        cursor.execute("SELECT * FROM deposit_disputes WHERE id = ?", (dispute_id,))
        updated = _row_to_dispute(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("deposit.dispute_resolved", updated)
    return updated


def _build_entity_summary(
    entity_key: str, entity_id: str, deposits: list[dict[str, Any]]
) -> dict[str, Any]:
    total_principal = round(sum(d["principal_amount"] for d in deposits), 2)
    total_interest = round(sum(d["accrued_interest"] for d in deposits), 2)
    total_deductions = round(sum(d["total_deductions"] for d in deposits), 2)
    total_net_refundable = round(sum(d["net_refundable"] for d in deposits), 2)
    open_disputes = sum(
        1
        for d in deposits
        for dsp in d["disputes"]
        if dsp["status"] in (DisputeStatus.OPEN.value, DisputeStatus.UNDER_REVIEW.value)
    )
    overdue_count = sum(1 for d in deposits if d["is_overdue"])
    primary = deposits[0] if deposits else None
    return {
        entity_key: entity_id,
        "total_deposits": len(deposits),
        "total_principal": total_principal,
        "total_interest": total_interest,
        "total_deductions": total_deductions,
        "total_net_refundable": total_net_refundable,
        "open_disputes_count": open_disputes,
        "overdue_deadlines_count": overdue_count,
        "primary_deposit": primary,
        "deposits": deposits,
    }


def get_unit_deposit_summary(unit_id: str) -> dict[str, Any]:
    """Summarize all security deposits, deductions, and disputes for a unit."""
    deposits = list_deposits(unit_id=unit_id)
    return _build_entity_summary("unit_id", unit_id, deposits)


def get_tenant_deposit_summary(tenant_id: str) -> dict[str, Any]:
    """Summarize all security deposits, deductions, and disputes for a tenant."""
    deposits = list_deposits(tenant_id=tenant_id)
    return _build_entity_summary("tenant_id", tenant_id, deposits)


def get_deposit_metrics_summary() -> dict[str, Any]:
    """Compute portfolio-wide security deposit escrow and statutory compliance KPIs."""
    deposits = list_deposits()
    disputes = list_disputes()

    total_deposits = len(deposits)
    held_count = sum(1 for d in deposits if d["status"] == DepositStatus.HELD.value)
    itemized_pending_count = sum(
        1 for d in deposits if d["status"] == DepositStatus.ITEMIZED_PENDING.value
    )
    refunded_count = sum(
        1
        for d in deposits
        if d["status"] in (DepositStatus.REFUNDED.value, DepositStatus.PARTIAL_REFUND.value)
    )
    disputed_count = sum(1 for d in deposits if d["status"] == DepositStatus.DISPUTED.value)
    overdue_deadlines_count = sum(1 for d in deposits if d["is_overdue"])
    open_disputes_count = sum(
        1
        for dsp in disputes
        if dsp["status"] in (DisputeStatus.OPEN.value, DisputeStatus.UNDER_REVIEW.value)
    )

    total_escrow_principal = round(sum(d["principal_amount"] for d in deposits), 2)
    total_accrued_interest = round(sum(d["accrued_interest"] for d in deposits), 2)
    total_deductions_assessed = round(sum(d["total_deductions"] for d in deposits), 2)
    total_refunded_amount = round(
        sum(d["refund_amount"] for d in deposits if d["refund_amount"] is not None), 2
    )

    with_deadlines = [d for d in deposits if d["statutory_deadline_date"]]
    if with_deadlines:
        on_time = len(with_deadlines) - overdue_deadlines_count
        statutory_compliance_rate = round((on_time / len(with_deadlines)) * 100.0, 2)
    else:
        statutory_compliance_rate = 100.0

    return {
        "total_deposits": total_deposits,
        "held_count": held_count,
        "itemized_pending_count": itemized_pending_count,
        "refunded_count": refunded_count,
        "disputed_count": disputed_count,
        "overdue_deadlines_count": overdue_deadlines_count,
        "open_disputes_count": open_disputes_count,
        "total_escrow_principal": total_escrow_principal,
        "total_accrued_interest": total_accrued_interest,
        "total_deductions_assessed": total_deductions_assessed,
        "total_refunded_amount": total_refunded_amount,
        "statutory_compliance_rate": statutory_compliance_rate,
    }

