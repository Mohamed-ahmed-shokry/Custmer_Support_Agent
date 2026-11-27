"""Unit tests for eviction compliance, legal notices, court filings, and payment plan workouts."""

from __future__ import annotations

import pytest
from api import db_utils
from api import evictions as ev
from api.evictions import CaseStatus, DeliveryMethod, NoticeType, PaymentPlanStatus

MIN_SEED_CASES = 2
EXPECTED_ARREARS = 2400.0
EXPECTED_INSTALLMENT = 800.0
MAX_PERCENT = 100.0


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_evictions.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    monkeypatch.setattr(ev.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_webhooks()
    ev.init_evictions_db()
    return db_path


def _get_seeded_unit_and_tenant() -> tuple[str, str]:
    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id, unit_id FROM tenants LIMIT 1").fetchone()
        assert row is not None
        return str(row["unit_id"]), str(row["id"])
    finally:
        conn.close()


def test_seed_evictions_and_plans():
    cases = ev.list_eviction_cases()
    assert len(cases) >= MIN_SEED_CASES
    plans = ev.list_payment_plans()
    assert len(plans) >= 1


def test_eviction_case_crud_court_filing_and_closure():
    unit_id, tenant_id = _get_seeded_unit_and_tenant()
    case = ev.create_eviction_case(
        unit_id,
        tenant_id,
        "Non-payment of rent for May",
        notice_type=NoticeType.PAY_OR_QUIT.value,
        delivery_method=DeliveryMethod.PERSONAL_SERVICE.value,
        arrears_amount=EXPECTED_ARREARS,
        notice_served_date="2020-01-01",
    )
    assert case["id"].startswith("evc_")
    assert case["is_cure_expired"] is True
    assert case["arrears_amount"] == EXPECTED_ARREARS

    updated = ev.update_eviction_case(case["id"], {"attorney_name": "J. Miller Esq."})
    assert updated is not None
    assert updated["attorney_name"] == "J. Miller Esq."

    filed = ev.record_court_filing(
        case["id"],
        "CV-2099-00412",
        "Travis County Justice Court Pct 5",
        hearing_date="2099-06-20",
        attorney_name="J. Miller Esq.",
    )
    assert filed is not None
    assert filed["status"] == CaseStatus.HEARING_SCHEDULED.value
    assert filed["court_case_number"] == "CV-2099-00412"

    closed = ev.close_eviction_case(
        case["id"],
        CaseStatus.CURED_DISMISSED.value,
        "Resident paid full balance plus court costs prior to hearing.",
    )
    assert closed is not None
    assert closed["status"] == CaseStatus.CURED_DISMISSED.value
    assert closed["closed_at"] is not None

    with pytest.raises(ValueError, match="notice_type"):
        ev.create_eviction_case(unit_id, tenant_id, "Bad notice", notice_type="invalid")


def test_payment_plan_auto_cure_and_default():
    unit_id, tenant_id = _get_seeded_unit_and_tenant()
    case = ev.create_eviction_case(
        unit_id, tenant_id, "Past-due balance workout", arrears_amount=EXPECTED_ARREARS
    )
    plan = ev.create_payment_plan(
        tenant_id,
        unit_id,
        total_arrears=EXPECTED_ARREARS,
        installment_count=3,
        next_due_date="2099-07-01",
        case_id=case["id"],
    )
    assert plan["installment_amount"] == EXPECTED_INSTALLMENT
    refreshed_case = ev.get_eviction_case(case["id"])
    assert refreshed_case is not None
    assert refreshed_case["status"] == CaseStatus.PAYMENT_PLAN_ACTIVE.value

    # Pay full balance across installments -> auto-completes plan and auto-cures linked case
    p1 = ev.record_plan_installment(plan["id"], EXPECTED_INSTALLMENT, next_due_date="2099-08-01")
    assert p1 is not None
    assert p1["status"] == PaymentPlanStatus.ACTIVE.value
    p2 = ev.record_plan_installment(plan["id"], 1600.0)
    assert p2 is not None
    assert p2["status"] == PaymentPlanStatus.COMPLETED.value

    cured_case = ev.get_eviction_case(case["id"])
    assert cured_case is not None
    assert cured_case["status"] == CaseStatus.CURED_DISMISSED.value

    # Test default workflow
    plan2 = ev.create_payment_plan(
        tenant_id, unit_id, total_arrears=900.0, installment_count=2, next_due_date="2099-09-01"
    )
    defaulted = ev.default_payment_plan(plan2["id"], "Missed first installment")
    assert defaulted is not None
    assert defaulted["status"] == PaymentPlanStatus.DEFAULTED.value


def test_summaries_and_metrics():
    unit_id, tenant_id = _get_seeded_unit_and_tenant()
    t_sum = ev.get_tenant_eviction_summary(tenant_id)
    assert t_sum["total_cases"] >= 1
    u_sum = ev.get_unit_eviction_summary(unit_id)
    assert u_sum["total_cases"] >= 1

    metrics = ev.get_eviction_metrics_summary()
    assert metrics["total_cases"] >= MIN_SEED_CASES
    assert 0.0 <= metrics["cure_rate_pct"] <= MAX_PERCENT
