"""Unit tests for the prospective leasing CRM, tours, applications, and screening engine."""

from __future__ import annotations

import pytest
from api import db_utils
from api import leasing_crm as lc
from api.leasing_crm import (
    ApplicationStatus,
    BackgroundCheckStatus,
    LeadSource,
    ProspectStage,
    TourStatus,
    TourType,
)

MIN_SEED_PROSPECTS = 2
EXPECTED_BUDGET = 2900.0
EXPECTED_RATING = 5
EXPECTED_INCOME = 7500.0
EXPECTED_RATIO = 3.75
EXPECTED_CREDIT = 720
MAX_PERCENT = 100.0


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_leasing_crm.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    monkeypatch.setattr(lc.webhooks, "dispatch_event", lambda *a, **kw: None)
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_webhooks()
    lc.init_leasing_crm_db()
    return db_path


def _get_seeded_unit_id() -> str:
    conn = db_utils.get_db_connection()
    try:
        row = conn.execute("SELECT id FROM units LIMIT 1").fetchone()
        assert row is not None
        return str(row["id"])
    finally:
        conn.close()


def test_seed_leasing_data_initialized():
    prospects = lc.list_prospects()
    assert len(prospects) >= MIN_SEED_PROSPECTS
    assert len(lc.list_tours()) >= 1
    assert len(lc.list_applications()) >= 1


def test_prospect_crud_and_validation():
    unit_id = _get_seeded_unit_id()
    created = lc.create_prospect(
        "Elena Vance",
        "elena@example.com",
        phone="555-0201",
        lead_source=LeadSource.APARTMENTS_COM.value,
        desired_unit_id=unit_id,
        desired_bedrooms=2,
        max_budget=EXPECTED_BUDGET,
        assigned_agent="Samira Patel",
    )
    assert created["id"].startswith("prs_")
    assert created["stage"] == ProspectStage.NEW.value
    assert created["max_budget"] == EXPECTED_BUDGET

    fetched = lc.get_prospect(created["id"])
    assert fetched is not None
    assert fetched["email"] == "elena@example.com"

    updated = lc.update_prospect(
        created["id"],
        {"stage": ProspectStage.CONTACTED.value, "notes": "Sent virtual brochure"},
    )
    assert updated is not None
    assert updated["stage"] == ProspectStage.CONTACTED.value

    with pytest.raises(ValueError, match="email"):
        lc.create_prospect("Bad Lead", "invalid-email")
    with pytest.raises(ValueError, match="lead_source"):
        lc.create_prospect("Bad Source", "a@b.com", lead_source="flyer")
    with pytest.raises(ValueError, match="Unit"):
        lc.create_prospect("Missing Unit", "a@b.com", desired_unit_id="unit_nope")


def test_tour_scheduling_completion_and_cancellation():
    unit_id = _get_seeded_unit_id()
    prospect = lc.create_prospect("Liam Chen", "liam@example.com", desired_unit_id=unit_id)

    tour = lc.schedule_tour(
        prospect["id"],
        unit_id,
        "2099-06-15",
        scheduled_time="15:00",
        tour_type=TourType.VIRTUAL.value,
        leasing_agent="Jordan Ellis",
    )
    assert tour["status"] == TourStatus.SCHEDULED.value
    refreshed = lc.get_prospect(prospect["id"])
    assert refreshed is not None
    assert refreshed["stage"] == ProspectStage.TOUR_SCHEDULED.value

    completed = lc.complete_tour(
        tour["id"], feedback_rating=EXPECTED_RATING, feedback_notes="Loved natural light"
    )
    assert completed is not None
    assert completed["status"] == TourStatus.COMPLETED.value
    assert completed["feedback_rating"] == EXPECTED_RATING
    after_tour = lc.get_prospect(prospect["id"])
    assert after_tour is not None
    assert after_tour["stage"] == ProspectStage.TOURED.value

    tour2 = lc.schedule_tour(prospect["id"], unit_id, "2099-06-20")
    cancelled = lc.cancel_tour(tour2["id"])
    assert cancelled is not None
    assert cancelled["status"] == TourStatus.CANCELLED.value


def test_application_screening_and_decision_lifecycle():
    unit_id = _get_seeded_unit_id()
    prospect = lc.create_prospect("Nora Alvarez", "nora@example.com", desired_unit_id=unit_id)

    app = lc.submit_application(
        prospect["id"],
        unit_id,
        monthly_income=EXPECTED_INCOME,
        target_rent=2000.0,
        credit_score=EXPECTED_CREDIT,
        desired_move_in_date="2099-07-01",
    )
    assert app["id"].startswith("app_")
    assert app["income_to_rent_ratio"] == EXPECTED_RATIO
    assert app["status"] == ApplicationStatus.SUBMITTED.value

    screened = lc.screen_application(
        app["id"],
        credit_score=EXPECTED_CREDIT,
        background_status=BackgroundCheckStatus.PASSED.value,
        eviction_history_clear=True,
        decision_notes="Verified payroll & clean background",
    )
    assert screened is not None
    assert screened["recommended_decision"] == ApplicationStatus.APPROVED.value

    decided = lc.decide_application(
        app["id"],
        ApplicationStatus.APPROVED.value,
        decision_notes="Approved for 12-month lease",
    )
    assert decided is not None
    assert decided["status"] == ApplicationStatus.APPROVED.value
    after_approve = lc.get_prospect(prospect["id"])
    assert after_approve is not None
    assert after_approve["stage"] == ProspectStage.APPROVED.value

    # Verify automated conditional & denial recommendations
    assert (
        lc.evaluate_screening(2.6, 620, BackgroundCheckStatus.PASSED.value, True)
        == ApplicationStatus.CONDITIONALLY_APPROVED.value
    )
    assert (
        lc.evaluate_screening(4.0, 750, BackgroundCheckStatus.PASSED.value, False)
        == ApplicationStatus.DENIED.value
    )


def test_unit_leasing_summary_and_portfolio_metrics():
    unit_id = _get_seeded_unit_id()
    summary = lc.get_unit_leasing_summary(unit_id)
    assert summary["unit_id"] == unit_id
    assert summary["min_monthly_income"] >= 0.0
    assert summary["demand_status"] in ("available", "active_interest", "high_demand")

    metrics = lc.get_leasing_metrics_summary()
    assert metrics["total_prospects"] >= MIN_SEED_PROSPECTS
    assert 0.0 <= metrics["approval_rate_pct"] <= MAX_PERCENT
    assert 0.0 <= metrics["lead_to_approval_rate_pct"] <= MAX_PERCENT
