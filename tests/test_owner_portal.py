"""Unit tests for property owner portals, statements, CapEx reserves, and approvals engine."""

from __future__ import annotations

import pytest
from api import db_utils
from api import owner_portal as op
from api.owner_portal import (
    ApprovalCategory,
    ApprovalStatus,
    DisbursementMethod,
    OwnerStatus,
    StatementStatus,
)

MIN_SEED_OWNERS = 2
EXPECTED_FEE_PCT = 10.0
EXPECTED_GROSS = 10000.0
EXPECTED_MGMT_FEE = 1000.0
EXPECTED_NET = 7500.0
EXPECTED_RESERVE_AFTER = 1500.0
EXPECTED_COST = 3200.0
MAX_PERCENT = 100.0


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_owner_portal.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    monkeypatch.setattr(op.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_webhooks()
    op.init_owner_portal_db()
    return db_path


def _get_seeded_unit_id() -> str:
    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
        assert row is not None
        return str(row["id"])
    finally:
        conn.close()


def test_seed_owner_portal_data():
    owners = op.list_owners()
    assert len(owners) >= MIN_SEED_OWNERS
    assert len(op.list_owner_statements()) >= 1
    assert len(op.list_approval_requests()) >= 1


def test_owner_crud_and_validation():
    created = op.create_owner(
        "Clara Sterling",
        "clara@sterlingcap.example",
        entity_name="Sterling Properties LLC",
        management_fee_pct=EXPECTED_FEE_PCT,
        reserve_balance=1000.0,
        reserve_target=5000.0,
        disbursement_method=DisbursementMethod.WIRE.value,
    )
    assert created["id"].startswith("own_")
    assert created["management_fee_pct"] == EXPECTED_FEE_PCT
    assert created["status"] == OwnerStatus.ACTIVE.value

    fetched = op.get_owner(created["id"])
    assert fetched is not None
    assert fetched["entity_name"] == "Sterling Properties LLC"

    updated = op.update_owner(created["id"], {"notes": "Prefers quarterly CapEx briefings"})
    assert updated is not None
    assert updated["notes"] == "Prefers quarterly CapEx briefings"

    with pytest.raises(ValueError, match="email"):
        op.create_owner("Bad Owner", "invalid-email")
    with pytest.raises(ValueError, match="management_fee_pct"):
        op.create_owner("High Fee", "a@b.com", management_fee_pct=75.0)
    with pytest.raises(ValueError, match="disbursement_method"):
        op.create_owner("Bad Method", "a@b.com", disbursement_method="crypto")


def test_statement_generation_markdown_and_disbursement():
    owner = op.create_owner(
        "Clara Sterling",
        "clara@sterlingcap.example",
        management_fee_pct=EXPECTED_FEE_PCT,
        reserve_balance=1000.0,
    )
    stmt = op.generate_owner_statement(
        owner["id"],
        "2099-05",
        gross_rent_collected=EXPECTED_GROSS,
        operating_expenses=1000.0,
        reserve_contribution=500.0,
        notes="May operating statement",
    )
    assert stmt["id"].startswith("stm_")
    assert stmt["management_fee_amount"] == EXPECTED_MGMT_FEE
    assert stmt["net_disbursement"] == EXPECTED_NET
    assert "May operating statement" in stmt["statement_markdown"]

    fetched = op.get_owner_statement(stmt["id"])
    assert fetched is not None
    assert "Cash Flow Summary" in fetched["statement_markdown"]

    disbursed = op.disburse_owner_statement(stmt["id"], notes="Sent via ACH batch #42")
    assert disbursed is not None
    assert disbursed["status"] == StatementStatus.DISBURSED.value
    refreshed_owner = op.get_owner(owner["id"])
    assert refreshed_owner is not None
    assert refreshed_owner["reserve_balance"] == EXPECTED_RESERVE_AFTER


def test_capex_approval_workflow_and_summaries():
    unit_id = _get_seeded_unit_id()
    approval = op.create_approval_request(
        "own_seed_01",
        "Roof Membrane Waterproofing",
        EXPECTED_COST,
        unit_id=unit_id,
        category=ApprovalCategory.MAJOR_REPAIR.value,
        vendor_name="Summit Roofing Co",
    )
    assert approval["id"].startswith("apr_")
    assert approval["status"] == ApprovalStatus.PENDING.value

    decided = op.decide_approval_request(
        approval["id"],
        ApprovalStatus.APPROVED.value,
        owner_decision_notes="Approved — proceed before rainy season.",
    )
    assert decided is not None
    assert decided["status"] == ApprovalStatus.APPROVED.value
    assert decided["decided_at"] is not None

    owner_sum = op.get_owner_summary("own_seed_01")
    assert owner_sum is not None
    assert owner_sum["total_statements"] >= 1

    unit_sum = op.get_unit_owner_approvals_summary(unit_id)
    assert unit_sum["total_approvals"] >= 1

    metrics = op.get_owner_portal_metrics_summary()
    assert metrics["total_owners"] >= MIN_SEED_OWNERS
    assert 0.0 <= metrics["approval_rate_pct"] <= MAX_PERCENT
