"""Unit tests for the incidents, violation notices, and appeals engine."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from api import db_utils, incidents

TEST_FINE_AMOUNT = 50.0
TEST_REDUCED_FINE = 25.0
EXPECTED_SEEDED_INCIDENTS = 1
EXPECTED_SEEDED_NOTICES = 1
EXPECTED_SEEDED_APPEALS = 1


@pytest.fixture(autouse=True)
def setup_incidents_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Fixture providing an isolated temporary database for each test."""
    db_file = tmp_path / "test_incidents.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_file))
    with closing(sqlite3.connect(str(db_file))) as conn:
        conn.row_factory = sqlite3.Row
    db_utils.create_units()
    db_utils.create_tenants()
    incidents.init_incidents_db()
    yield


def test_init_incidents_db_seeds_defaults():
    """Verify that init_incidents_db bootstraps tables and seeds default records."""
    res = incidents.list_incidents()
    assert res["total"] >= EXPECTED_SEEDED_INCIDENTS
    inc = next((i for i in res["items"] if i["incident_number"] == "INC-2026-101"), None)
    assert inc is not None
    assert inc["tenant_id"] == "tenant_3"
    assert inc["unit_id"] == "unit_PH1"
    assert inc["incident_type"] == incidents.IncidentType.NOISE_COMPLAINT.value

    notices = incidents.list_violation_notices()
    assert notices["total"] >= EXPECTED_SEEDED_NOTICES
    vn = next((n for n in notices["items"] if n["notice_number"] == "VN-2026-089"), None)
    assert vn is not None
    assert vn["notice_type"] == incidents.NoticeType.COURTESY_WARNING.value

    appeals = incidents.list_violation_appeals()
    assert appeals["total"] >= EXPECTED_SEEDED_APPEALS
    apl = next((a for a in appeals["items"] if a["appeal_number"] == "APL-2026-042"), None)
    assert apl is not None
    assert apl["status"] == incidents.AppealStatus.UNDER_REVIEW.value


def test_create_and_get_incident():
    """Verify creating, retrieving, and listing community incidents."""
    created = incidents.create_incident(
        incident_type=incidents.IncidentType.TRASH_DISPOSAL.value,
        description="Improper disposal of oversized cardboard boxes in hallway.",
        severity=incidents.IncidentSeverity.LOW.value,
        unit_id="unit_101",
        tenant_id="tenant_1",
        reported_by="staff",
        location="1st Floor Trash Chute",
    )
    assert created["id"].startswith("inc_")
    assert created["incident_number"].startswith("INC-")
    assert created["incident_type"] == incidents.IncidentType.TRASH_DISPOSAL.value
    assert created["status"] == incidents.IncidentStatus.REPORTED.value

    retrieved = incidents.get_incident(created["id"])
    assert retrieved is not None
    assert retrieved["id"] == created["id"]
    assert retrieved["unit_id"] == "unit_101"

    retrieved_by_num = incidents.get_incident(created["incident_number"])
    assert retrieved_by_num is not None
    assert retrieved_by_num["id"] == created["id"]

    filtered = incidents.list_incidents(
        incident_type=incidents.IncidentType.TRASH_DISPOSAL.value,
        tenant_id="tenant_1",
    )
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == created["id"]


def test_update_and_delete_incident():
    """Verify updating incident details, resolution, and deletion."""
    created = incidents.create_incident(
        incident_type=incidents.IncidentType.PET_WASTE_VIOLATION.value,
        description="Dog waste observed in inner courtyard lawn.",
        severity=incidents.IncidentSeverity.MEDIUM.value,
        unit_id="unit_101",
        tenant_id="tenant_1",
    )

    updated = incidents.update_incident(
        incident_id=created["id"],
        status=incidents.IncidentStatus.RESOLVED.value,
        action_taken="Maintenance team dispatched to sanitize area; resident contacted.",
        resolution_notes="Resident apologized and agreed to comply with leash/cleanup rules.",
    )
    assert updated is not None
    assert updated["status"] == incidents.IncidentStatus.RESOLVED.value
    assert updated["resolved_at"] is not None
    assert "sanitized" not in updated["action_taken"]
    assert updated["action_taken"] is not None

    deleted = incidents.delete_incident(created["id"])
    assert deleted is True
    assert incidents.get_incident(created["id"]) is None


def test_violation_notice_lifecycle():
    """Verify violation notice creation, cure deadline, and resolution."""
    notice = incidents.create_violation_notice(
        tenant_id="tenant_1",
        unit_id="unit_101",
        violation_type=incidents.IncidentType.SMOKING_PROHIBITED.value,
        notice_type=incidents.NoticeType.FIRST_NOTICE_TO_CURE.value,
        remedy_instructions="Smoking is prohibited in all indoor units and common hallways.",
        cure_days=3,
        fine_amount=TEST_FINE_AMOUNT,
        charge_to_ledger=True,
    )
    assert notice["id"].startswith("viol_")
    assert notice["notice_number"].startswith("VN-")
    assert notice["fine_amount"] == TEST_FINE_AMOUNT
    assert notice["fine_charged_to_ledger"] is True
    assert notice["status"] == incidents.ViolationStatus.ISSUED.value
    assert notice["cure_deadline"] is not None

    updated = incidents.update_violation_notice(
        notice_id=notice["id"],
        status=incidents.ViolationStatus.CURED.value,
        notes="Resident ceased smoking inside unit following air quality inspection.",
    )
    assert updated is not None
    assert updated["status"] == incidents.ViolationStatus.CURED.value
    assert updated["cured_at"] is not None

    deleted = incidents.delete_violation_notice(notice["id"])
    assert deleted is True
    assert incidents.get_violation_notice(notice["id"]) is None


def test_violation_appeal_lifecycle():
    """Verify submitting an appeal, status transitions, and decision outcomes."""
    notice = incidents.create_violation_notice(
        tenant_id="tenant_1",
        unit_id="unit_101",
        violation_type=incidents.IncidentType.ALTERATION_UNAPPROVED.value,
        notice_type=incidents.NoticeType.FINE_ASSESSMENT.value,
        remedy_instructions=(
            "Remove non-conforming door wreath and bracket per building guidelines."
        ),
        fine_amount=TEST_FINE_AMOUNT,
    )

    appeal = incidents.create_violation_appeal(
        notice_id=notice["id"],
        tenant_id="tenant_1",
        unit_id="unit_101",
        reason="Bracket was temporary for holiday celebration and removed promptly.",
    )
    assert appeal["id"].startswith("appeal_")
    assert appeal["appeal_number"].startswith("APL-")
    assert appeal["status"] == incidents.AppealStatus.SUBMITTED.value

    # Notice status should now be updated to APPEALED
    re_notice = incidents.get_violation_notice(notice["id"])
    assert re_notice is not None
    assert re_notice["status"] == incidents.ViolationStatus.APPEALED.value

    # Test appeal reduction decision
    updated_appeal = incidents.update_violation_appeal(
        appeal_id=appeal["id"],
        status=incidents.AppealStatus.REDUCED.value,
        reviewed_by="Community Manager",
        decision_notes="First offense and prompt compliance; fine reduced by 50%.",
        adjusted_fine_amount=TEST_REDUCED_FINE,
    )
    assert updated_appeal is not None
    assert updated_appeal["status"] == incidents.AppealStatus.REDUCED.value
    assert updated_appeal["adjusted_fine_amount"] == TEST_REDUCED_FINE
    assert updated_appeal["decided_at"] is not None

    # Notice fine should be adjusted to $25.00
    re_notice_2 = incidents.get_violation_notice(notice["id"])
    assert re_notice_2 is not None
    assert re_notice_2["fine_amount"] == TEST_REDUCED_FINE
    assert re_notice_2["status"] == incidents.ViolationStatus.ISSUED.value


def test_incident_metrics_summary():
    """Verify aggregated portfolio incident and violation metrics."""
    metrics = incidents.get_incident_metrics_summary()
    assert isinstance(metrics, dict)
    assert metrics["total_incidents"] >= 1
    assert metrics["active_incidents"] >= 0
    assert metrics["total_violations"] >= 1
    assert metrics["open_violations"] >= 1
    assert metrics["cured_violations"] >= 0
    assert metrics["total_appeals"] >= 1
    assert metrics["pending_appeals"] >= 1
    assert metrics["appeals_waived"] >= 0
