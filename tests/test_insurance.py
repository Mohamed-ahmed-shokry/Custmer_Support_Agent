"""Unit tests for resident renters insurance policies, claims, and compliance."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from api import insurance


@pytest.fixture
def memory_db():
    """Create an isolated SQLite database connection with pre-seeded demo records."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create parent tables
    cursor.execute(
        """
        CREATE TABLE units (
            id TEXT PRIMARY KEY,
            unit_number TEXT NOT NULL,
            building_name TEXT NOT NULL,
            monthly_rent REAL NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE tenants (
            id TEXT PRIMARY KEY,
            unit_id TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            balance_due REAL DEFAULT 0.0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE billing_transactions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            due_date TEXT NOT NULL,
            description TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE webhook_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # Insert test units and tenants
    cursor.execute(
        "INSERT INTO units VALUES ('unit_101', '101', 'Building A', 1450.0)"
    )
    cursor.execute(
        "INSERT INTO units VALUES ('unit_PH1', 'PH1', 'Horizon Tower', 4500.0)"
    )
    cursor.execute(
        "INSERT INTO tenants (id, unit_id, first_name, last_name, email, phone, balance_due) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("tenant_1", "unit_101", "Sarah", "Connor", "sarah@example.com", "+1-555-0199", 0.0),
    )
    cursor.execute(
        "INSERT INTO tenants (id, unit_id, first_name, last_name, email, phone, balance_due) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("tenant_3", "unit_PH1", "Elena", "Rostova", "elena@example.com", "+1-555-0301", 0.0),
    )
    conn.commit()

    insurance.init_insurance_db(conn)
    yield conn
    conn.close()


def test_init_insurance_db_seeds_defaults(memory_db: sqlite3.Connection):
    """Verify default policies and claims are seeded."""
    min_policies = 2
    policies = insurance.list_insurance_policies(conn=memory_db)
    assert len(policies) >= min_policies
    claims = insurance.list_insurance_claims(conn=memory_db)
    assert len(claims) >= 1

    expected_liability = 100000.0
    p_101 = insurance.get_insurance_policy("pol_seed_101", conn=memory_db)
    assert p_101 is not None
    assert p_101["carrier_name"] == "Lemonade Insurance"
    assert p_101["liability_coverage_amount"] == expected_liability
    assert p_101["status"] == "active"
    assert p_101["tenant_name"] == "Sarah Connor"


def test_create_and_verify_insurance_policy(memory_db: sqlite3.Connection):
    """Verify policy creation, retrieval, and verification workflow."""
    payload: dict[str, Any] = {
        "tenant_id": "tenant_1",
        "carrier_name": "Geico / Assurant",
        "policy_number": "GEI-2026-9901",
        "liability_coverage_amount": 100000.0,
        "personal_property_coverage": 30000.0,
        "deductible_amount": 250.0,
        "effective_start_date": "2026-01-01",
        "expiration_date": "2027-01-01",
        "interested_party_listed": 1,
    }
    policy = insurance.create_insurance_policy(payload, conn=memory_db)
    assert policy["id"].startswith("pol_")
    assert policy["status"] == "pending_verification"

    # Approve policy
    verified = insurance.verify_insurance_policy(
        policy["id"], is_approved=True, verified_by="manager_bob", notes="All good", conn=memory_db
    )
    assert verified is not None
    assert verified["status"] == "active"
    assert verified["verified_by"] == "manager_bob"

    # Reject policy
    rejected = insurance.verify_insurance_policy(
        policy["id"],
        is_approved=False,
        verified_by="manager_bob",
        notes="Interested party missing",
        conn=memory_db,
    )
    assert rejected is not None
    assert rejected["status"] == "rejected"


def test_assess_non_compliance_fee(memory_db: sqlite3.Connection):
    """Verify non-compliance fee assessment updates tenant ledger and policy."""
    expected_fee = 25.0
    fee_res = insurance.assess_insurance_non_compliance_fee(
        "pol_seed_101", fee_amount=expected_fee, conn=memory_db
    )
    assert fee_res is not None
    assert fee_res["success"] is True
    assert fee_res["fee_amount"] == expected_fee

    # Check tenant balance updated
    cursor = memory_db.cursor()
    cursor.execute("SELECT balance_due FROM tenants WHERE id = 'tenant_1'")
    bal = cursor.fetchone()[0]
    assert bal == expected_fee

    # Check transaction recorded
    cursor.execute("SELECT * FROM billing_transactions WHERE id = ?", (fee_res["transaction_id"],))
    tx = cursor.fetchone()
    assert tx is not None
    assert tx["amount"] == expected_fee
    assert tx["transaction_type"] == "insurance_fee"


def test_create_and_update_insurance_claim(memory_db: sqlite3.Connection):
    """Verify claim filing and adjuster settlement updates."""
    loss_est = 3500.0
    claim_payload: dict[str, Any] = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "policy_id": "pol_seed_101",
        "claim_type": insurance.InsuranceClaimType.FIRE_SMOKE,
        "incident_date": "2026-11-12",
        "description": "Toaster malfunction caused smoke damage to kitchen cabinets.",
        "estimated_loss": loss_est,
    }
    claim = insurance.create_insurance_claim(claim_payload, conn=memory_db)
    assert claim["claim_number"].startswith("CLM-")
    assert claim["status"] == "submitted"
    assert claim["estimated_loss"] == loss_est

    # Update claim
    settled_target = 3200.0
    updated = insurance.update_insurance_claim(
        claim["id"],
        {
            "status": insurance.InsuranceClaimStatus.SETTLED,
            "settled_amount": settled_target,
            "adjuster_name": "Alice Adjuster",
            "resolution_notes": "Claim settled with resident.",
        },
        conn=memory_db,
    )
    assert updated is not None
    assert updated["status"] == "settled"
    assert updated["settled_amount"] == settled_target
    assert updated["adjuster_name"] == "Alice Adjuster"


def test_summaries_and_metrics(memory_db: sqlite3.Connection):
    """Verify unit/tenant summaries and aggregated insurance KPIs."""
    min_policies = 2
    u_sum = insurance.get_unit_insurance_summary("unit_101", conn=memory_db)
    assert u_sum["is_compliant"] is True
    assert u_sum["policies_count"] >= 1
    assert u_sum["claims_count"] >= 1

    t_sum = insurance.get_tenant_insurance_summary("tenant_1", conn=memory_db)
    assert t_sum["is_compliant"] is True
    assert t_sum["tenant_id"] == "tenant_1"

    metrics = insurance.get_insurance_metrics_summary(conn=memory_db)
    assert metrics["total_policies"] >= min_policies
    assert metrics["active_policies"] >= 1
    assert metrics["compliance_rate_pct"] > 0.0
    assert metrics["total_claims"] >= 1
