"""Tests for Resident Pet Registry and Animal Policies FastAPI Routes (api/main.py)."""

from __future__ import annotations

import pytest
from api import db_utils, pets
from api.main import app
from fastapi.testclient import TestClient

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_404 = 404
EXPECTED_METRICS_PETS = 1
MIN_POLICIES_COUNT = 2
TEST_FINE = 75.0
TEST_UPDATED_FINE = 100.0
TEST_UPDATED_WEIGHT = 64.5
TEST_INITIAL_POLICY_WEIGHT = 45.0
TEST_UPDATED_RENT = 45.0
TEST_UPDATED_POLICY_WEIGHT = 50.0


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    """Provide a test client against an isolated SQLite test database."""
    test_db = tmp_path / "test_pet_routes.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(test_db))
    db_utils.create_tenants()
    db_utils.create_units()
    db_utils.create_application_logs()
    db_utils.create_webhooks()
    db_utils.create_session_labels()
    pets.init_pets_db()

    return TestClient(app)


def test_pet_metrics_and_defaults(client_with_db):
    """Verify community pet metrics endpoint and seeded pet defaults."""
    res = client_with_db.get("/pets/metrics")
    assert res.status_code == HTTP_200
    data = res.json()
    assert data["total_active_pets"] >= EXPECTED_METRICS_PETS
    assert data["total_dogs"] >= EXPECTED_METRICS_PETS

    # Verify default seeded policy is reachable
    pol_res = client_with_db.get("/pet-policies/policy_default")
    assert pol_res.status_code == HTTP_200
    assert pol_res.json()["policy"]["property_name"] == "Grand Community Apartments"


def test_resident_pet_crud_routes(client_with_db):
    """Test pet registration, filtering, retrieval, update, and deletion."""
    pet_payload = {
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "name": "Cooper",
        "pet_type": "dog",
        "breed": "Golden Retriever",
        "weight_lbs": 62.0,
        "color": "Golden",
        "age_years": 3,
        "is_service_animal": False,
        "is_esa": False,
        "rabies_tag": "RAB-2026-9999",
        "vaccination_expires": "2027-05-15",
        "notes": "Very friendly dog",
    }
    create_res = client_with_db.post("/pets", json=pet_payload)
    assert create_res.status_code == HTTP_201
    pet_id = create_res.json()["pet"]["id"]
    assert create_res.json()["pet"]["name"] == "Cooper"

    # List pets with filter
    list_res = client_with_db.get("/pets?pet_type=dog&status=active")
    assert list_res.status_code == HTTP_200
    items = list_res.json()["items"]
    assert any(p["id"] == pet_id for p in items)

    # Get pet by ID
    get_res = client_with_db.get(f"/pets/{pet_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["pet"]["breed"] == "Golden Retriever"

    # Update pet
    patch_res = client_with_db.patch(
        f"/pets/{pet_id}",
        json={"weight_lbs": TEST_UPDATED_WEIGHT, "notes": "Gained a little weight"},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["pet"]["weight_lbs"] == TEST_UPDATED_WEIGHT

    # Delete pet
    del_res = client_with_db.delete(f"/pets/{pet_id}")
    assert del_res.status_code == HTTP_200
    assert del_res.json()["status"] == "deleted"

    # Verify 404 after deletion
    not_found = client_with_db.get(f"/pets/{pet_id}")
    assert not_found.status_code == HTTP_404


def test_tenant_pets_route(client_with_db):
    """Test retrieving pets for a specific verified tenant."""
    # Seed tenant_3 has Barnaby
    res = client_with_db.get("/tenants/tenant_3/pets")
    assert res.status_code == HTTP_200
    items = res.json()["items"]
    assert len(items) >= 1
    assert items[0]["name"] == "Barnaby"

    # Unknown tenant returns 404
    missing_res = client_with_db.get("/tenants/nonexistent_tenant/pets")
    assert missing_res.status_code == HTTP_404


def test_session_register_pet_route(client_with_db):
    """Test 1-click resident pet registration grounded in active session."""
    session_id = "sess_pet_test_01"

    # Attempting registration without linked tenant profile fails
    fail_res = client_with_db.post(
        f"/sessions/{session_id}/register-pet",
        json={"name": "Shadow", "pet_type": "cat", "weight_lbs": 10.0},
    )
    assert fail_res.status_code == HTTP_400

    # Link session to tenant_1
    link_res = client_with_db.post(
        f"/sessions/{session_id}/link-tenant",
        json={"tenant_id": "tenant_1"},
    )
    assert link_res.status_code == HTTP_200

    # Now registration succeeds
    reg_res = client_with_db.post(
        f"/sessions/{session_id}/register-pet",
        json={
            "name": "Shadow",
            "pet_type": "cat",
            "breed": "Domestic Shorthair",
            "weight_lbs": 10.5,
            "color": "Black",
            "age_years": 2,
        },
    )
    assert reg_res.status_code == HTTP_201
    pet_data = reg_res.json()["pet"]
    assert pet_data["name"] == "Shadow"
    assert pet_data["tenant_id"] == "tenant_1"
    assert pet_data["unit_id"] == "unit_101"


def test_pet_policy_routes(client_with_db):
    """Test policy creation, listing, retrieval, and updating."""
    # Create building-specific policy
    policy_payload = {
        "property_name": "Grand Community Tower B",
        "building": "Tower B",
        "pet_type": "all",
        "max_weight_lbs": 45.0,
        "max_pets_per_unit": 1,
        "monthly_pet_rent": 40.0,
        "one_time_deposit": 350.0,
        "restricted_breeds": ["Akita", "Chow Chow"],
        "rules_and_restrictions": "Leash required in common areas at all times.",
    }
    create_res = client_with_db.post("/pet-policies", json=policy_payload)
    assert create_res.status_code == HTTP_201
    pol_id = create_res.json()["policy"]["id"]
    assert create_res.json()["policy"]["building"] == "Tower B"

    # List policies
    list_res = client_with_db.get("/pet-policies")
    assert list_res.status_code == HTTP_200
    assert len(list_res.json()["items"]) >= MIN_POLICIES_COUNT

    # Get by ID
    get_res = client_with_db.get(f"/pet-policies/{pol_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["policy"]["max_weight_lbs"] == TEST_INITIAL_POLICY_WEIGHT

    # Patch policy
    patch_res = client_with_db.patch(
        f"/pet-policies/{pol_id}",
        json={"monthly_pet_rent": TEST_UPDATED_RENT, "max_weight_lbs": TEST_UPDATED_POLICY_WEIGHT},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["policy"]["monthly_pet_rent"] == TEST_UPDATED_RENT
    assert patch_res.json()["policy"]["max_weight_lbs"] == TEST_UPDATED_POLICY_WEIGHT


def test_pet_incident_routes(client_with_db):
    """Test logging animal incidents, listing, and updating resolution/fines."""
    incident_payload = {
        "incident_type": "off_leash",
        "incident_date": "2026-11-04",
        "pet_id": "pet_elena_01",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "fine_amount": TEST_FINE,
        "status": "warning_issued",
        "notes": "Off leash near resident swimming pool courtyard.",
    }
    rec_res = client_with_db.post("/pet-incidents", json=incident_payload)
    assert rec_res.status_code == HTTP_201
    inc_id = rec_res.json()["incident"]["id"]
    assert rec_res.json()["incident"]["incident_type"] == "off_leash"

    # List incidents
    list_res = client_with_db.get("/pet-incidents?tenant_id=tenant_3")
    assert list_res.status_code == HTTP_200
    assert len(list_res.json()["items"]) >= 1

    # Get incident by ID
    get_res = client_with_db.get(f"/pet-incidents/{inc_id}")
    assert get_res.status_code == HTTP_200
    assert get_res.json()["incident"]["fine_amount"] == TEST_FINE

    # Update incident
    patch_res = client_with_db.patch(
        f"/pet-incidents/{inc_id}",
        json={"status": "fine_assessed", "fine_amount": TEST_UPDATED_FINE},
    )
    assert patch_res.status_code == HTTP_200
    assert patch_res.json()["incident"]["status"] == "fine_assessed"
    assert patch_res.json()["incident"]["fine_amount"] == TEST_UPDATED_FINE

    # Unknown incident 404
    missing = client_with_db.get("/pet-incidents/nonexistent_inc")
    assert missing.status_code == HTTP_404
