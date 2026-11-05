"""Unit tests for resident pets database schema, policies, incidents, and metrics."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from api import db_utils, pets

TEST_FINE_AMOUNT = 75.0
TEST_ESCALATED_FINE = 100.0
TEST_UPDATED_RENT = 25.0
TEST_PET_WEIGHT = 9.5
TEST_UPDATED_WEIGHT = 58.5
MIN_EXPECTED_DOGS = 2
MAX_BUILDING_B_PETS = 3


@pytest.fixture(autouse=True)
def setup_temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Fixture providing an isolated temporary database for each test."""
    db_file = tmp_path / "test_pets.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_file))
    with closing(sqlite3.connect(str(db_file))) as conn:
        conn.row_factory = sqlite3.Row
    db_utils.create_units()
    db_utils.create_tenants()
    pets.init_pets_db()
    yield


def test_init_pets_db_seeds_defaults():
    """Verify that init_pets_db bootstraps tables and seeds default policy and pet."""
    policy = pets.get_pet_policy("policy_default")
    assert policy is not None
    assert policy["property_name"] == "Grand Community Apartments"
    assert policy["monthly_pet_rent"] == pets.DEFAULT_PET_RENT
    assert "Pit Bull Terrier" in policy["restricted_breeds"]

    seeded_pet = pets.get_resident_pet("pet_elena_01")
    assert seeded_pet is not None
    assert seeded_pet["name"] == "Barnaby"
    assert seeded_pet["tenant_id"] == "tenant_3"
    assert seeded_pet["pet_type"] == "dog"


def test_create_and_get_resident_pet():
    """Verify resident pet creation and retrieval."""
    pet = pets.create_resident_pet(
        tenant_id="tenant_1",
        unit_id="unit_101",
        name="Mochi",
        pet_type="cat",
        breed="Siamese",
        weight_lbs=9.5,
        color="Cream / Seal Point",
        age_years=2,
        is_service_animal=False,
        is_esa=True,
        rabies_tag="RAB-9912",
        vaccination_expires="2027-01-01",
        license_number="LIC-101-CAT",
        status="active",
        notes="Indoor cat, friendly",
    )
    assert pet["id"].startswith("pet_")
    assert pet["name"] == "Mochi"
    assert pet["is_esa"] is True
    assert pet["is_service_animal"] is False
    assert pet["weight_lbs"] == TEST_PET_WEIGHT

    fetched = pets.get_resident_pet(pet["id"])
    assert fetched is not None
    assert fetched["breed"] == "Siamese"


def test_list_and_update_resident_pet():
    """Verify listing resident pets with filters and updating fields."""
    pets.create_resident_pet(
        tenant_id="tenant_1",
        unit_id="unit_101",
        name="Luna",
        pet_type="dog",
        breed="Labrador",
        weight_lbs=55.0,
        is_service_animal=True,
    )
    # Search by pet type
    dogs = pets.list_resident_pets(pet_type="dog")
    assert len(dogs) >= MIN_EXPECTED_DOGS  # Barnaby + Luna

    # Search by service animal
    service_pets = pets.list_resident_pets(is_service_animal=True)
    assert len(service_pets) >= 1
    assert any(p["name"] == "Luna" for p in service_pets)

    # Search by name query
    matched = pets.list_resident_pets(search="Lun")
    assert len(matched) == 1
    assert matched[0]["name"] == "Luna"

    # Update pet
    pet_id = matched[0]["id"]
    updated = pets.update_resident_pet(
        pet_id, weight_lbs=TEST_UPDATED_WEIGHT, status="pending_approval"
    )
    assert updated is not None
    assert updated["weight_lbs"] == TEST_UPDATED_WEIGHT
    assert updated["status"] == "pending_approval"

    # Delete pet
    deleted = pets.delete_resident_pet(pet_id)
    assert deleted is True
    assert pets.get_resident_pet(pet_id) is None


def test_get_tenant_pets():
    """Verify tenant pets lookup by tenant_id or unit."""
    t3_pets = pets.get_tenant_pets("tenant_3")
    assert len(t3_pets) >= 1
    assert t3_pets[0]["name"] == "Barnaby"


def test_pet_policies_crud():
    """Verify pet policy creation, listing, and updates."""
    policy = pets.create_pet_policy(
        property_name="Grand Community Apartments",
        building="Building B",
        pet_type="cat",
        max_weight_lbs=25.0,
        max_pets_per_unit=3,
        monthly_pet_rent=20.0,
        one_time_deposit=150.0,
        restricted_breeds=[],
        rules_and_restrictions="Cats only in Building B.",
    )
    assert policy["id"].startswith("policy_")
    assert policy["max_pets_per_unit"] == MAX_BUILDING_B_PETS

    b_policies = pets.list_pet_policies(building="Building B")
    assert len(b_policies) >= 1

    updated = pets.update_pet_policy(policy["id"], monthly_pet_rent=TEST_UPDATED_RENT)
    assert updated is not None
    assert updated["monthly_pet_rent"] == TEST_UPDATED_RENT


def test_pet_incidents_crud():
    """Verify recording, listing, and updating pet incidents."""
    inc = pets.record_pet_incident(
        incident_type="noise_barking",
        pet_id="pet_elena_01",
        fine_amount=TEST_FINE_AMOUNT,
        status="reported",
        notes="Continuous barking reported after 10 PM.",
    )
    assert inc["id"].startswith("inc_")
    assert inc["tenant_id"] == "tenant_3"
    assert inc["unit_id"] == "unit_PH1"

    incidents = pets.list_pet_incidents(incident_type="noise_barking")
    assert len(incidents) >= 1

    updated = pets.update_pet_incident(
        inc["id"], status="fine_assessed", fine_amount=TEST_ESCALATED_FINE
    )
    assert updated is not None
    assert updated["status"] == "fine_assessed"
    assert updated["fine_amount"] == TEST_ESCALATED_FINE


def test_pet_summary_metrics():
    """Verify pet summary metrics calculation."""
    # Seeded pet: 1 active dog, exempt from rent? No, is_service_animal=0
    metrics = pets.get_pet_summary_metrics()
    assert metrics["total_active_pets"] >= 1
    assert metrics["total_dogs"] >= 1
    assert metrics["monthly_pet_rent_roll"] >= pets.DEFAULT_PET_RENT
