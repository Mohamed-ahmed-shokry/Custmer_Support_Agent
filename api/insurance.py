"""Database schema, models, CRUD helpers, verification, and metrics for renters insurance."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils, webhooks

# Constants
MIN_REQUIRED_LIABILITY_COVERAGE = 100000.0  # $100k standard liability limit
DEFAULT_NON_COMPLIANCE_FEE = 25.0  # $25 monthly force-placed non-compliance fee
DEFAULT_INTERESTED_PARTY = "Metropolis Property Management LLC"
MIN_SEEDED_POLICIES = 2


class InsurancePolicyStatus(StrEnum):
    ACTIVE = "active"
    PENDING_VERIFICATION = "pending_verification"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    LAPSED = "lapsed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class InsuranceClaimType(StrEnum):
    WATER_DAMAGE = "water_damage"
    FIRE_SMOKE = "fire_smoke"
    THEFT_BURGLARY = "theft_burglary"
    PERSONAL_LIABILITY = "personal_liability"
    STORM_WEATHER = "storm_weather"
    OTHER = "other"


class InsuranceClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ADJUSTER_ASSIGNED = "adjuster_assigned"
    APPROVED = "approved"
    SETTLED = "settled"
    DENIED = "denied"


def _generate_policy_id() -> str:
    return f"pol_{secrets.token_hex(4)}"


def _generate_claim_number() -> str:
    today_str = datetime.datetime.now(UTC).strftime("%Y%m%d")
    rand = secrets.token_hex(2).upper()
    return f"CLM-{today_str}-{rand}"


def init_insurance_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize database tables for resident renters insurance policies and claims."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS insurance_policies (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                carrier_name TEXT NOT NULL,
                policy_number TEXT NOT NULL,
                liability_coverage_amount REAL NOT NULL DEFAULT 100000.0,
                personal_property_coverage REAL DEFAULT 20000.0,
                deductible_amount REAL DEFAULT 500.0,
                effective_start_date TEXT NOT NULL,
                expiration_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_verification',
                interested_party_listed INTEGER NOT NULL DEFAULT 1,
                interested_party_name TEXT DEFAULT 'Metropolis Property Management LLC',
                document_url TEXT,
                verification_notes TEXT,
                verified_by TEXT,
                verified_at TEXT,
                non_compliance_fee_assessed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS insurance_claims (
                id TEXT PRIMARY KEY,
                claim_number TEXT UNIQUE NOT NULL,
                policy_id TEXT,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'submitted',
                incident_date TEXT NOT NULL,
                description TEXT NOT NULL,
                estimated_loss REAL NOT NULL DEFAULT 0.0,
                settled_amount REAL DEFAULT 0.0,
                adjuster_name TEXT,
                adjuster_phone TEXT,
                adjuster_email TEXT,
                resolution_notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (policy_id) REFERENCES insurance_policies(id) ON DELETE SET NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_insurance_policies_tenant
            ON insurance_policies (tenant_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_insurance_policies_unit
            ON insurance_policies (unit_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_insurance_policies_status
            ON insurance_policies (status)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_insurance_claims_tenant
            ON insurance_claims (tenant_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_insurance_claims_policy
            ON insurance_claims (policy_id)
            """
        )

        conn.commit()
        _seed_default_insurance(conn)
    finally:
        if close_conn:
            conn.close()


def _seed_default_insurance(conn: sqlite3.Connection) -> None:
    """Seed sample renters insurance policies and claims for default demo units."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM insurance_policies")
    count = cursor.fetchone()[0]
    if count >= MIN_SEEDED_POLICIES:
        return

    now_iso = datetime.datetime.now(UTC).isoformat()
    today_date = datetime.datetime.now(UTC).date()
    future_exp = (today_date + datetime.timedelta(days=240)).isoformat()
    soon_exp = (today_date + datetime.timedelta(days=15)).isoformat()
    start_date = (today_date - datetime.timedelta(days=125)).isoformat()

    sample_policies = [
        (
            "pol_seed_101",
            "tenant_1",
            "unit_101",
            "Lemonade Insurance",
            "LEM-7890123",
            100000.0,
            25000.0,
            500.0,
            start_date,
            future_exp,
            InsurancePolicyStatus.ACTIVE,
            1,
            DEFAULT_INTERESTED_PARTY,
            "https://documents.internal/policies/LEM-7890123.pdf",
            "Policy verified and active. Meets $100k liability limit.",
            "leasing_desk",
            now_iso,
            0,
            now_iso,
            now_iso,
        ),
        (
            "pol_seed_PH1",
            "tenant_3",
            "unit_PH1",
            "State Farm",
            "SF-9912345",
            300000.0,
            50000.0,
            1000.0,
            start_date,
            soon_exp,
            InsurancePolicyStatus.EXPIRING_SOON,
            1,
            DEFAULT_INTERESTED_PARTY,
            "https://documents.internal/policies/SF-9912345.pdf",
            "Verified premium penthouse coverage. Renewal reminder sent.",
            "property_manager",
            now_iso,
            0,
            now_iso,
            now_iso,
        ),
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO insurance_policies (
            id, tenant_id, unit_id, carrier_name, policy_number,
            liability_coverage_amount, personal_property_coverage, deductible_amount,
            effective_start_date, expiration_date, status, interested_party_listed,
            interested_party_name, document_url, verification_notes, verified_by,
            verified_at, non_compliance_fee_assessed, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_policies,
    )

    sample_claims = [
        (
            "clm_seed_1",
            "CLM-20261101-9A2F",
            "pol_seed_101",
            "tenant_1",
            "unit_101",
            InsuranceClaimType.WATER_DAMAGE,
            InsuranceClaimStatus.APPROVED,
            (today_date - datetime.timedelta(days=20)).isoformat(),
            "Minor kitchen sink supply line overflow damaged baseboards and rug.",
            1200.0,
            1200.0,
            "Mark Adjuster",
            "+1-555-0888",
            "claims@lemonade.com",
            "Coverage confirmed. Repair claim approved.",
            now_iso,
            now_iso,
        )
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO insurance_claims (
            id, claim_number, policy_id, tenant_id, unit_id, claim_type,
            status, incident_date, description, estimated_loss, settled_amount,
            adjuster_name, adjuster_phone, adjuster_email, resolution_notes,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_claims,
    )

    conn.commit()


# ---------------------------------------------------------------------------
# Policy CRUD & Verification Operations
# ---------------------------------------------------------------------------


def create_insurance_policy(
    payload: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Register a new renters insurance policy submitted by a resident or property team."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        policy_id = payload.get("id") or _generate_policy_id()
        now_iso = datetime.datetime.now(UTC).isoformat()

        # Check tenant exists
        cursor = conn.cursor()
        cursor.execute("SELECT unit_id FROM tenants WHERE id = ?", (payload["tenant_id"],))
        t_row = cursor.fetchone()
        resolved_unit_id = payload.get("unit_id") or (t_row[0] if t_row else "unknown")

        liability_amt = float(
            payload.get("liability_coverage_amount") or MIN_REQUIRED_LIABILITY_COVERAGE
        )
        personal_amt = float(payload.get("personal_property_coverage") or 20000.0)
        deductible = float(payload.get("deductible_amount") or 500.0)
        start_date = (
            payload.get("effective_start_date") or datetime.datetime.now(UTC).date().isoformat()
        )
        exp_date = (
            payload.get("expiration_date")
            or (datetime.datetime.now(UTC).date() + datetime.timedelta(days=365)).isoformat()
        )
        status = payload.get("status") or InsurancePolicyStatus.PENDING_VERIFICATION
        interested = int(payload.get("interested_party_listed", 1))
        interested_name = payload.get("interested_party_name") or DEFAULT_INTERESTED_PARTY

        cursor.execute(
            """
            INSERT INTO insurance_policies (
                id, tenant_id, unit_id, carrier_name, policy_number,
                liability_coverage_amount, personal_property_coverage, deductible_amount,
                effective_start_date, expiration_date, status, interested_party_listed,
                interested_party_name, document_url, verification_notes, verified_by,
                verified_at, non_compliance_fee_assessed, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                policy_id,
                payload["tenant_id"],
                resolved_unit_id,
                payload["carrier_name"],
                payload["policy_number"],
                liability_amt,
                personal_amt,
                deductible,
                start_date,
                exp_date,
                status,
                interested,
                interested_name,
                payload.get("document_url"),
                payload.get("verification_notes"),
                payload.get("verified_by"),
                payload.get("verified_at"),
                0,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        policy = get_insurance_policy(policy_id, conn)

        webhooks.dispatch_event(
            "insurance.policy_submitted",
            {"policy_id": policy_id, "policy": policy},
        )
        return policy or {}
    finally:
        if close_conn:
            conn.close()


def get_insurance_policy(
    policy_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve details of a renters insurance policy by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM insurance_policies p
            LEFT JOIN tenants t ON p.tenant_id = t.id
            LEFT JOIN units u ON p.unit_id = u.id
            WHERE p.id = ?
            """,
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        d = dict(row)
        t_first = d.pop("first_name", "") or ""
        t_last = d.pop("last_name", "") or ""
        d["tenant_name"] = f"{t_first} {t_last}".strip() or "Resident"
        return d
    finally:
        if close_conn:
            conn.close()


def list_insurance_policies(  # noqa: PLR0912, PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List insurance policies with optional tenant, unit, and status filtering."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        cursor = conn.cursor()
        query = """
            SELECT p.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM insurance_policies p
            LEFT JOIN tenants t ON p.tenant_id = t.id
            LEFT JOIN units u ON p.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []
        if tenant_id:
            query += " AND p.tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND p.unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND p.status = ?"
            params.append(status)

        query += " ORDER BY p.created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            t_first = d.pop("first_name", "") or ""
            t_last = d.pop("last_name", "") or ""
            d["tenant_name"] = f"{t_first} {t_last}".strip() or "Resident"
            results.append(d)
        return results
    finally:
        if close_conn:
            conn.close()


def verify_insurance_policy(  # noqa: PLR0913, PLR0917
    policy_id: str,
    is_approved: bool,
    verified_by: str,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Verify or reject a resident renters insurance policy."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        cursor = conn.cursor()
        now_iso = datetime.datetime.now(UTC).isoformat()
        new_status = (
            InsurancePolicyStatus.ACTIVE if is_approved else InsurancePolicyStatus.REJECTED
        )

        cursor.execute(
            """
            UPDATE insurance_policies
            SET status = ?, verified_by = ?, verified_at = ?,
                verification_notes = COALESCE(?, verification_notes),
                updated_at = ?
            WHERE id = ?
            """,
            (new_status, verified_by, now_iso, notes, now_iso, policy_id),
        )
        conn.commit()
        policy = get_insurance_policy(policy_id, conn)
        if not policy:
            return None

        event = "insurance.policy_verified" if is_approved else "insurance.policy_rejected"
        webhooks.dispatch_event(
            event,
            {"policy_id": policy_id, "policy": policy, "verified_by": verified_by},
        )
        return policy
    finally:
        if close_conn:
            conn.close()


def assess_insurance_non_compliance_fee(
    policy_id: str,
    fee_amount: float = DEFAULT_NON_COMPLIANCE_FEE,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Assess and post a force-placed non-compliance fee to resident rent ledger."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        policy = get_insurance_policy(policy_id, conn)
        if not policy:
            return None

        tenant_id = policy["tenant_id"]
        unit_id = policy["unit_id"]
        now_iso = datetime.datetime.now(UTC).isoformat()
        now_date = datetime.datetime.now(UTC).date().isoformat()
        cursor = conn.cursor()

        # Insert fee transaction into billing_transactions
        tx_id = f"tx_ins_fee_{secrets.token_hex(4)}"
        cursor.execute(
            """
            INSERT INTO billing_transactions (
                id, tenant_id, unit_id, transaction_type, reason,
                amount, status, due_date, posted_at, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx_id,
                tenant_id,
                unit_id,
                "charge",
                "other",
                fee_amount,
                "posted",
                now_date,
                now_iso,
                f"Renters insurance non-compliance fee for policy {policy['policy_number']}",
                now_iso,
                now_iso,
            ),
        )

        # Update tenant balance_due
        cursor.execute(
            """
            UPDATE tenants
            SET balance_due = COALESCE(balance_due, 0.0) + ?
            WHERE id = ?
            """,
            (fee_amount, tenant_id),
        )

        # Mark fee assessed on policy
        cursor.execute(
            """
            UPDATE insurance_policies
            SET non_compliance_fee_assessed = non_compliance_fee_assessed + 1,
                status = CASE WHEN status = 'active' THEN 'lapsed' ELSE status END,
                updated_at = ?
            WHERE id = ?
            """,
            (now_iso, policy_id),
        )
        conn.commit()

        updated_policy = get_insurance_policy(policy_id, conn)
        webhooks.dispatch_event(
            "insurance.fee_assessed",
            {
                "policy_id": policy_id,
                "tenant_id": tenant_id,
                "fee_amount": fee_amount,
                "transaction_id": tx_id,
            },
        )
        return {
            "policy": updated_policy,
            "transaction_id": tx_id,
            "fee_amount": fee_amount,
            "success": True,
        }
    finally:
        if close_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Insurance Claims CRUD & Tracking
# ---------------------------------------------------------------------------


def create_insurance_claim(
    payload: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """File a resident insurance claim."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        claim_id = payload.get("id") or f"clm_{secrets.token_hex(4)}"
        claim_number = payload.get("claim_number") or _generate_claim_number()
        now_iso = datetime.datetime.now(UTC).isoformat()
        incident_date = (
            payload.get("incident_date") or datetime.datetime.now(UTC).date().isoformat()
        )
        est_loss = float(payload.get("estimated_loss") or 0.0)
        settled_amt = float(payload.get("settled_amount") or 0.0)
        status = payload.get("status") or InsuranceClaimStatus.SUBMITTED

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO insurance_claims (
                id, claim_number, policy_id, tenant_id, unit_id, claim_type,
                status, incident_date, description, estimated_loss, settled_amount,
                adjuster_name, adjuster_phone, adjuster_email, resolution_notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                claim_number,
                payload.get("policy_id"),
                payload["tenant_id"],
                payload["unit_id"],
                payload.get("claim_type") or InsuranceClaimType.OTHER,
                status,
                incident_date,
                payload.get("description") or "Resident insurance claim",
                est_loss,
                settled_amt,
                payload.get("adjuster_name"),
                payload.get("adjuster_phone"),
                payload.get("adjuster_email"),
                payload.get("resolution_notes"),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        claim = get_insurance_claim(claim_id, conn)

        webhooks.dispatch_event(
            "insurance.claim_filed",
            {"claim_id": claim_id, "claim": claim},
        )
        return claim or {}
    finally:
        if close_conn:
            conn.close()


def get_insurance_claim(
    claim_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve details of an insurance claim by ID or claim number."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.*, t.first_name, t.last_name, u.unit_number, u.building_name,
                   p.carrier_name, p.policy_number
            FROM insurance_claims c
            LEFT JOIN tenants t ON c.tenant_id = t.id
            LEFT JOIN units u ON c.unit_id = u.id
            LEFT JOIN insurance_policies p ON c.policy_id = p.id
            WHERE c.id = ? OR c.claim_number = ?
            """,
            (claim_id, claim_id),
        )
        row = cursor.fetchone()
        if not row:
            return None

        d = dict(row)
        t_first = d.pop("first_name", "") or ""
        t_last = d.pop("last_name", "") or ""
        d["tenant_name"] = f"{t_first} {t_last}".strip() or "Resident"
        return d
    finally:
        if close_conn:
            conn.close()


def list_insurance_claims(  # noqa: PLR0912, PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    claim_type: str | None = None,
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List insurance claims with optional filtering."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        cursor = conn.cursor()
        query = """
            SELECT c.*, t.first_name, t.last_name, u.unit_number, u.building_name,
                   p.carrier_name, p.policy_number
            FROM insurance_claims c
            LEFT JOIN tenants t ON c.tenant_id = t.id
            LEFT JOIN units u ON c.unit_id = u.id
            LEFT JOIN insurance_policies p ON c.policy_id = p.id
            WHERE 1=1
        """
        params: list[Any] = []
        if tenant_id:
            query += " AND c.tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND c.unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND c.status = ?"
            params.append(status)
        if claim_type:
            query += " AND c.claim_type = ?"
            params.append(claim_type)

        query += " ORDER BY c.created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            t_first = d.pop("first_name", "") or ""
            t_last = d.pop("last_name", "") or ""
            d["tenant_name"] = f"{t_first} {t_last}".strip() or "Resident"
            results.append(d)
        return results
    finally:
        if close_conn:
            conn.close()


def update_insurance_claim(
    claim_id: str, payload: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Update claim status, adjuster info, or settlement details."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        cursor = conn.cursor()
        now_iso = datetime.datetime.now(UTC).isoformat()

        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [now_iso]

        updatable = [
            "status",
            "estimated_loss",
            "settled_amount",
            "adjuster_name",
            "adjuster_phone",
            "adjuster_email",
            "resolution_notes",
        ]
        for f in updatable:
            if f in payload and payload[f] is not None:
                fields.append(f"{f} = ?")
                values.append(payload[f])

        values.append(claim_id)
        cursor.execute(
            f"UPDATE insurance_claims SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
        return get_insurance_claim(claim_id, conn)
    finally:
        if close_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Summaries & Metrics Aggregation
# ---------------------------------------------------------------------------


def get_unit_insurance_summary(
    unit_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Get active insurance policy, compliance status, and claims for a unit."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        policies = list_insurance_policies(unit_id=unit_id)
        claims = list_insurance_claims(unit_id=unit_id)

        active_policy = next(
            (p for p in policies if p.get("status") in ("active", "expiring_soon")),
            None,
        )
        is_compliant = (
            active_policy is not None
            and active_policy.get("liability_coverage_amount", 0) >= MIN_REQUIRED_LIABILITY_COVERAGE
        )

        return {
            "unit_id": unit_id,
            "policies_count": len(policies),
            "is_compliant": is_compliant,
            "primary_policy": active_policy or (policies[0] if policies else None),
            "claims_count": len(claims),
            "recent_claims": claims[:5],
        }
    finally:
        if close_conn:
            conn.close()


def get_tenant_insurance_summary(
    tenant_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Get renters insurance compliance record and claim history for a resident."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        policies = list_insurance_policies(tenant_id=tenant_id)
        claims = list_insurance_claims(tenant_id=tenant_id)

        active_policy = next(
            (p for p in policies if p.get("status") in ("active", "expiring_soon")),
            None,
        )
        is_compliant = (
            active_policy is not None
            and active_policy.get("liability_coverage_amount", 0) >= MIN_REQUIRED_LIABILITY_COVERAGE
        )

        return {
            "tenant_id": tenant_id,
            "unit_id": policies[0].get("unit_id") if policies else None,
            "policies_count": len(policies),
            "is_compliant": is_compliant,
            "primary_policy": active_policy or (policies[0] if policies else None),
            "claims_count": len(claims),
            "recent_claims": claims[:5],
        }
    finally:
        if close_conn:
            conn.close()


def get_insurance_metrics_summary(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Aggregated portfolio renters insurance compliance and claims metrics."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_insurance_db(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM insurance_policies")
        total_policies = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM insurance_policies WHERE status = 'active'")
        active_policies = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM insurance_policies
            WHERE status IN ('pending_verification', 'under_review')
            """
        )
        pending_verification = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM insurance_policies WHERE status = 'expiring_soon'")
        expiring_soon = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM insurance_policies
            WHERE status IN ('expired', 'lapsed', 'rejected')
            """
        )
        non_compliant = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*), COALESCE(SUM(estimated_loss), 0.0) FROM insurance_claims")
        claim_row = cursor.fetchone()
        total_claims = claim_row[0]
        total_loss = claim_row[1]

        cursor.execute(
            """
            SELECT COUNT(*) FROM insurance_claims
            WHERE status IN ('submitted', 'under_review', 'adjuster_assigned')
            """
        )
        open_claims = cursor.fetchone()[0]

        compliance_rate = (
            round((active_policies / total_policies) * 100.0, 1) if total_policies > 0 else 0.0
        )

        return {
            "total_policies": total_policies,
            "active_policies": active_policies,
            "pending_verification": pending_verification,
            "expiring_soon": expiring_soon,
            "non_compliant_policies": non_compliant,
            "compliance_rate_pct": compliance_rate,
            "total_claims": total_claims,
            "open_claims": open_claims,
            "total_estimated_loss": total_loss,
        }
    finally:
        if close_conn:
            conn.close()
