"""Unit tests for the access control database schema, credentials, and guest passes."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from api import access_control, db_utils

TEST_REPLACEMENT_FEE = 50.0
TEST_UPDATED_FEE = 75.0
MIN_EXPECTED_CREDS = 2
MIN_EXPECTED_PASSES = 1
MIN_EXPECTED_INTERCOM = 1


@pytest.fixture(autouse=True)
def setup_access_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Fixture providing an isolated temporary database for each test."""
    db_file = tmp_path / "test_access_control.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_file))
    with closing(sqlite3.connect(str(db_file))) as conn:
        conn.row_factory = sqlite3.Row
    db_utils.create_units()
    db_utils.create_tenants()
    access_control.init_access_control_db()
    yield


def test_init_access_control_db_seeds_defaults():
    """Verify that init_access_control_db bootstraps tables and seeds initial data."""
    creds = access_control.list_access_credentials()
    assert len(creds) >= MIN_EXPECTED_CREDS
    fob = next((c for c in creds if c["credential_number"] == "FOB-9042"), None)
    assert fob is not None
    assert fob["tenant_id"] == "tenant_3"
    assert fob["unit_id"] == "unit_PH1"
    assert fob["access_level"] == access_control.AccessLevel.ALL_ACCESS.value
    assert fob["status"] == access_control.CredentialStatus.ACTIVE.value

    passes = access_control.list_guest_passes()
    assert len(passes) >= MIN_EXPECTED_PASSES
    assert passes[0]["guest_name"] == "Paws & Walk Dog Walker"
    assert passes[0]["access_code"] == "618902"

    intercom = access_control.list_intercom_entries()
    assert len(intercom) >= MIN_EXPECTED_INTERCOM
    assert intercom[0]["directory_code"] == "PH1"
    assert intercom[0]["display_name"] == "Rostova, E."


def test_create_and_get_access_credential():
    """Verify creating, querying, and retrieving an access credential."""
    cred = access_control.create_access_credential(
        tenant_id="tenant_1",
        unit_id="unit_101",
        credential_type=access_control.CredentialType.KEY_FOB.value,
        credential_number="FOB-1011",
        access_level=access_control.AccessLevel.STANDARD.value,
        assigned_to_name="Sarah Chen",
    )
    assert cred["id"].startswith("cred_")
    assert cred["credential_number"] == "FOB-1011"
    assert cred["tenant_id"] == "tenant_1"

    fetched = access_control.get_access_credential(cred["id"])
    assert fetched is not None
    assert fetched["credential_number"] == "FOB-1011"


def test_update_and_delete_access_credential():
    """Verify updating and deleting credentials."""
    cred = access_control.create_access_credential(
        tenant_id="tenant_2",
        unit_id="unit_202",
        credential_type=access_control.CredentialType.ACCESS_CARD.value,
        credential_number="CARD-2022",
    )
    updated = access_control.update_access_credential(
        cred_id=cred["id"],
        status=access_control.CredentialStatus.SUSPENDED.value,
        notes="Temporary suspension due to maintenance check",
    )
    assert updated is not None
    assert updated["status"] == access_control.CredentialStatus.SUSPENDED.value
    assert updated["notes"] == "Temporary suspension due to maintenance check"

    deleted = access_control.delete_access_credential(cred["id"])
    assert deleted is True
    assert access_control.get_access_credential(cred["id"]) is None


def test_report_lost_fob_and_fee_assessment():
    """Verify reporting a fob lost revokes access and assesses replacement fee."""
    cred = access_control.create_access_credential(
        tenant_id="tenant_1",
        unit_id="unit_101",
        credential_type=access_control.CredentialType.KEY_FOB.value,
        credential_number="FOB-9999",
    )
    lost_cred = access_control.report_lost_fob(
        cred_id=cred["id"],
        deactivation_reason="Dropped in parking lot drain",
        charge_replacement_fee=True,
    )
    assert lost_cred is not None
    assert lost_cred["status"] == access_control.CredentialStatus.LOST.value
    assert lost_cred["replacement_fee"] == TEST_REPLACEMENT_FEE
    assert lost_cred["deactivated_at"] is not None


def test_guest_pass_lifecycle():
    """Verify guest pass creation, usage increment, and auto-completion."""
    gpass = access_control.create_guest_pass(
        tenant_id="tenant_1",
        unit_id="unit_101",
        guest_name="FedEx Courier",
        pass_type=access_control.GuestPassType.DELIVERY.value,
        max_uses=1,
        allowed_zones=["main_lobby", "package_room"],
    )
    assert gpass["id"].startswith("pass_")
    assert len(gpass["access_code"]) == access_control.DEFAULT_ACCESS_CODE_LENGTH
    assert gpass["uses_count"] == 0
    assert gpass["status"] == access_control.GuestPassStatus.ACTIVE.value

    # Use pass once -> reach max_uses -> status becomes 'used'
    updated = access_control.update_guest_pass(
        pass_id=gpass["id"],
        increment_use=True,
    )
    assert updated is not None
    assert updated["uses_count"] == 1
    assert updated["status"] == access_control.GuestPassStatus.USED.value


def test_intercom_directory_crud():
    """Verify CRUD on intercom directory."""
    entry = access_control.create_intercom_entry(
        tenant_id="tenant_1",
        unit_id="unit_101",
        display_name="Chen, S.",
        directory_code="101",
        forwarding_phone="+1-555-0111",
        buzzer_enabled=True,
    )
    assert entry["id"].startswith("dir_")
    assert entry["directory_code"] == "101"

    updated = access_control.update_intercom_entry(
        entry_id=entry["id"],
        forwarding_phone="+1-555-0999",
        allow_video=True,
    )
    assert updated is not None
    assert updated["forwarding_phone"] == "+1-555-0999"
    assert updated["allow_video"] == 1

    deleted = access_control.delete_intercom_entry(entry["id"])
    assert deleted is True
    assert access_control.get_intercom_entry(entry["id"]) is None


def test_access_control_summary_metrics():
    """Verify aggregation metrics for access control."""
    metrics = access_control.get_access_control_summary_metrics()
    assert metrics["total_credentials"] >= MIN_EXPECTED_CREDS
    assert metrics["active_credentials"] >= 1
    assert metrics["total_guest_passes"] >= MIN_EXPECTED_PASSES
    assert metrics["intercom_directory_count"] >= MIN_EXPECTED_INTERCOM
