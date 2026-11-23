"""Unit tests for the security deposit escrow, deductions, disposition, and dispute engine."""

from __future__ import annotations

import pytest
from api import db_utils
from api import security_deposits as sd
from api.security_deposits import (
    DeductionCategory,
    DepositStatus,
    DepositType,
    DisputeStatus,
    RefundMethod,
)

MIN_SEED_DEPOSITS = 2
SEED_102_DEDUCTION = 185.0
SEED_102_NET = 1627.0
PET_PRINCIPAL = 1500.0
PET_INTEREST = 10.50
PET_NET = 1510.50
UPDATED_INTEREST = 15.0
UPDATED_NET = 1515.0
EXPECTED_TWO = 2
EXPECTED_THREE = 3
CLEANING_AMOUNT = 150.0
NET_AFTER_CLEANING = 850.0
ADJUSTED_REFUND = 1100.0
MAX_PERCENT = 100.0


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_security_deposits.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    monkeypatch.setattr(sd.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_webhooks()
    sd.init_security_deposits_db()
    return db_path


def _get_seeded_unit_and_tenant() -> tuple[str, str]:
    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id, unit_id FROM tenants LIMIT 1").fetchone()
        assert row is not None
        return str(row["unit_id"]), str(row["id"])
    finally:
        conn.close()


def test_seed_deposits_initialized():
    deposits = sd.list_deposits()
    assert len(deposits) >= MIN_SEED_DEPOSITS
    seeded = sd.get_deposit("dep_seed_102")
    assert seeded is not None
    assert seeded["status"] == DepositStatus.ITEMIZED_PENDING.value
    assert seeded["total_deductions"] == SEED_102_DEDUCTION
    assert seeded["net_refundable"] == SEED_102_NET


def test_create_get_list_and_update_deposit():
    unit_id, tenant_id = _get_seeded_unit_and_tenant()
    created = sd.create_deposit(
        unit_id=unit_id,
        principal_amount=PET_PRINCIPAL,
        tenant_id=tenant_id,
        deposit_type=DepositType.PET_DEPOSIT.value,
        accrued_interest=PET_INTEREST,
        escrow_account_ref="ESC-PET-999",
        move_out_date="2099-06-01",
        notes="Pet deposit for golden retriever",
    )
    assert created["id"].startswith("dep_")
    assert created["principal_amount"] == PET_PRINCIPAL
    assert created["accrued_interest"] == PET_INTEREST
    assert created["net_refundable"] == PET_NET
    assert created["statutory_deadline_date"] == "2099-06-22"

    fetched = sd.get_deposit(created["id"])
    assert fetched is not None
    assert fetched["escrow_account_ref"] == "ESC-PET-999"

    filtered = sd.list_deposits(unit_id=unit_id, deposit_type=DepositType.PET_DEPOSIT.value)
    assert any(d["id"] == created["id"] for d in filtered)

    updated = sd.update_deposit(
        created["id"],
        {"accrued_interest": UPDATED_INTEREST, "forwarding_address": "100 Main St"},
    )
    assert updated is not None
    assert updated["accrued_interest"] == UPDATED_INTEREST
    assert updated["net_refundable"] == UPDATED_NET
    assert updated["forwarding_address"] == "100 Main St"


def test_create_deposit_validation_errors():
    unit_id, _ = _get_seeded_unit_and_tenant()
    with pytest.raises(ValueError, match="principal_amount"):
        sd.create_deposit(unit_id=unit_id, principal_amount=0)
    with pytest.raises(ValueError, match="accrued_interest"):
        sd.create_deposit(unit_id=unit_id, principal_amount=500, accrued_interest=-1)
    with pytest.raises(ValueError, match="deposit_type"):
        sd.create_deposit(unit_id=unit_id, principal_amount=500, deposit_type="invalid")
    with pytest.raises(ValueError, match="Unit"):
        sd.create_deposit(unit_id="unit_nonexistent", principal_amount=500)


def test_deductions_statement_and_refund_lifecycle():
    unit_id, tenant_id = _get_seeded_unit_and_tenant()
    dep = sd.create_deposit(unit_id=unit_id, principal_amount=1000.0, tenant_id=tenant_id)

    ded1 = sd.add_deduction(
        dep["id"],
        DeductionCategory.CLEANING.value,
        "Deep carpet cleaning",
        CLEANING_AMOUNT,
        evidence_ref="INSP-101",
    )
    ded2 = sd.add_deduction(
        dep["id"],
        DeductionCategory.KEY_REPLACEMENT.value,
        "Missing garage fob",
        75.0,
    )
    assert len(sd.list_deductions(dep["id"])) == EXPECTED_TWO
    assert sd.delete_deduction(ded2["id"]) is True
    assert sd.delete_deduction("ded_missing") is False

    stmt = sd.issue_disposition_statement(
        dep["id"],
        move_out_date="2099-07-01",
        forwarding_address="555 Oak Blvd",
    )
    assert stmt is not None
    assert stmt["status"] == DepositStatus.ITEMIZED_PENDING.value
    assert stmt["total_deductions"] == CLEANING_AMOUNT
    assert stmt["net_refundable"] == NET_AFTER_CLEANING
    assert "Deep carpet cleaning" in stmt["statement_markdown"]
    assert ded1["evidence_ref"] in stmt["statement_markdown"]

    refunded = sd.issue_refund(dep["id"], RefundMethod.ACH.value, notes="Sent via ACH")
    assert refunded is not None
    assert refunded["status"] == DepositStatus.PARTIAL_REFUND.value
    assert refunded["refund_amount"] == NET_AFTER_CLEANING
    assert refunded["refund_method"] == RefundMethod.ACH.value


def test_dispute_workflow_and_metrics_and_summaries():
    unit_id, tenant_id = _get_seeded_unit_and_tenant()
    dep = sd.create_deposit(
        unit_id=unit_id,
        principal_amount=1200.0,
        tenant_id=tenant_id,
        move_out_date="2020-01-01",
    )
    assert dep["is_overdue"] is True

    dispute = sd.open_dispute(
        dep["id"],
        disputed_amount=200.0,
        reason="Carpet wear was normal after 3-year tenancy",
    )
    assert dispute["status"] == DisputeStatus.OPEN.value
    after_open = sd.get_deposit(dep["id"])
    assert after_open is not None
    assert after_open["status"] == DepositStatus.DISPUTED.value

    open_list = sd.list_disputes(deposit_id=dep["id"], status=DisputeStatus.OPEN.value)
    assert len(open_list) == 1

    resolved = sd.resolve_dispute(
        dispute["id"],
        DisputeStatus.RESOLVED_ADJUSTED.value,
        resolution_notes="Waived $100 of carpet cleaning fee",
        adjusted_refund_amount=ADJUSTED_REFUND,
    )
    assert resolved is not None
    assert resolved["status"] == DisputeStatus.RESOLVED_ADJUSTED.value
    assert resolved["adjusted_refund_amount"] == ADJUSTED_REFUND

    unit_summary = sd.get_unit_deposit_summary(unit_id)
    assert unit_summary["total_deposits"] >= 1
    tenant_summary = sd.get_tenant_deposit_summary(tenant_id)
    assert tenant_summary["total_deposits"] >= 1

    metrics = sd.get_deposit_metrics_summary()
    assert metrics["total_deposits"] >= EXPECTED_THREE
    assert metrics["overdue_deadlines_count"] >= 1
    assert 0.0 <= metrics["statutory_compliance_rate"] <= MAX_PERCENT
