"""Database schema, CRUD operations, policy enforcement, and metrics for resident pets."""

from __future__ import annotations

import datetime
import json
import secrets
import sqlite3
from enum import StrEnum
from typing import Any

from api import db_utils

# Minimum seeded records and constants
MIN_DEFAULT_POLICIES = 1
MIN_DEFAULT_PETS = 1
DEFAULT_PET_FINE = 50.0
DEFAULT_PET_RENT = 35.0
DEFAULT_PET_DEPOSIT = 300.0
DEFAULT_MAX_WEIGHT = 65.0
DEFAULT_MAX_PETS = 2


class PetType(StrEnum):
    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    CAGED_SMALL = "caged_small"
    FISH = "fish"
    REPTILE = "reptile"
    OTHER = "other"


class PetStatus(StrEnum):
    ACTIVE = "active"
    PENDING_APPROVAL = "pending_approval"
    DEPARTED = "departed"
    DECEASED = "deceased"
    REJECTED = "rejected"


class IncidentType(StrEnum):
    NOISE_BARKING = "noise_barking"
    OFF_LEASH = "off_leash"
    WASTE_CLEANUP = "waste_cleanup"
    AGGRESSIVE_BEHAVIOR = "aggressive_behavior"
    UNAUTHORIZED_PET = "unauthorized_pet"
    PROPERTY_DAMAGE = "property_damage"


class IncidentStatus(StrEnum):
    REPORTED = "reported"
    WARNING_ISSUED = "warning_issued"
    FINE_ASSESSED = "fine_assessed"
    RESOLVED = "resolved"
    DISPUTED = "disputed"


DEFAULT_RESTRICTED_BREEDS: list[str] = [
    "Pit Bull Terrier",
    "Staffordshire Terrier",
    "Rottweiler",
    "Doberman Pinscher",
    "Chow Chow",
    "Wolf Hybrid",
]

DEFAULT_PET_POLICY: dict[str, Any] = {
    "id": "policy_default",
    "property_name": "Grand Community Apartments",
    "building": "All Buildings",
    "pet_type": "all",
    "max_weight_lbs": DEFAULT_MAX_WEIGHT,
    "max_pets_per_unit": DEFAULT_MAX_PETS,
    "monthly_pet_rent": DEFAULT_PET_RENT,
    "one_time_deposit": DEFAULT_PET_DEPOSIT,
    "restricted_breeds": json.dumps(DEFAULT_RESTRICTED_BREEDS),
    "rules_and_restrictions": (
        "All dogs must remain on a handheld leash in common areas. Pet waste must be disposed "
        "of immediately in designated pet stations. Current rabies vaccination required on file."
    ),
}

DEFAULT_SEEDED_PETS: list[dict[str, Any]] = [
    {
        "id": "pet_elena_01",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "name": "Barnaby",
        "pet_type": PetType.DOG.value,
        "breed": "Golden Retriever Mix",
        "weight_lbs": 38.0,
        "color": "Golden",
        "age_years": 3,
        "is_service_animal": 0,
        "is_esa": 0,
        "rabies_tag": "RAB-2026-8812",
        "vaccination_expires": "2027-05-15",
        "license_number": "PET-LIC-9481",
        "status": PetStatus.ACTIVE.value,
        "photo_url": None,
        "notes": "Registered dog noted in Elena Rostova corporate lease.",
    }
]


def init_pets_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize resident_pets, pet_policies, and pet_incidents tables idempotently."""
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_policies (
                id TEXT PRIMARY KEY,
                property_name TEXT NOT NULL DEFAULT 'Grand Community Apartments',
                building TEXT,
                pet_type TEXT NOT NULL DEFAULT 'all',
                max_weight_lbs REAL NOT NULL DEFAULT 65.0,
                max_pets_per_unit INTEGER NOT NULL DEFAULT 2,
                monthly_pet_rent REAL NOT NULL DEFAULT 35.0,
                one_time_deposit REAL NOT NULL DEFAULT 300.0,
                restricted_breeds TEXT NOT NULL DEFAULT '[]',
                rules_and_restrictions TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS resident_pets (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                name TEXT NOT NULL,
                pet_type TEXT NOT NULL DEFAULT 'dog',
                breed TEXT,
                weight_lbs REAL NOT NULL DEFAULT 0.0,
                color TEXT,
                age_years INTEGER,
                is_service_animal INTEGER NOT NULL DEFAULT 0,
                is_esa INTEGER NOT NULL DEFAULT 0,
                rabies_tag TEXT,
                vaccination_expires TEXT,
                license_number TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                photo_url TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pets_tenant ON resident_pets(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pets_unit ON resident_pets(unit_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pets_status ON resident_pets(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pets_type ON resident_pets(pet_type)")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_incidents (
                id TEXT PRIMARY KEY,
                pet_id TEXT,
                tenant_id TEXT,
                unit_id TEXT,
                incident_type TEXT NOT NULL,
                incident_date TEXT NOT NULL,
                fine_amount REAL NOT NULL DEFAULT 50.0,
                status TEXT NOT NULL DEFAULT 'reported',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_pet ON pet_incidents(pet_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidents_tenant ON pet_incidents(tenant_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON pet_incidents(status)")

        # Seed default policy if empty
        cursor.execute("SELECT COUNT(*) FROM pet_policies")
        if cursor.fetchone()[0] == 0:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            cursor.execute(
                """
                INSERT INTO pet_policies (
                    id, property_name, building, pet_type, max_weight_lbs,
                    max_pets_per_unit, monthly_pet_rent, one_time_deposit,
                    restricted_breeds, rules_and_restrictions, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_PET_POLICY["id"],
                    DEFAULT_PET_POLICY["property_name"],
                    DEFAULT_PET_POLICY["building"],
                    DEFAULT_PET_POLICY["pet_type"],
                    DEFAULT_PET_POLICY["max_weight_lbs"],
                    DEFAULT_PET_POLICY["max_pets_per_unit"],
                    DEFAULT_PET_POLICY["monthly_pet_rent"],
                    DEFAULT_PET_POLICY["one_time_deposit"],
                    DEFAULT_PET_POLICY["restricted_breeds"],
                    DEFAULT_PET_POLICY["rules_and_restrictions"],
                    now,
                    now,
                ),
            )

        # Seed default pets if empty
        cursor.execute("SELECT COUNT(*) FROM resident_pets")
        if cursor.fetchone()[0] == 0:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            for p in DEFAULT_SEEDED_PETS:
                cursor.execute(
                    """
                    INSERT INTO resident_pets (
                        id, tenant_id, unit_id, name, pet_type, breed,
                        weight_lbs, color, age_years, is_service_animal, is_esa,
                        rabies_tag, vaccination_expires, license_number,
                        status, photo_url, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p["id"],
                        p["tenant_id"],
                        p["unit_id"],
                        p["name"],
                        p["pet_type"],
                        p["breed"],
                        p["weight_lbs"],
                        p["color"],
                        p["age_years"],
                        p["is_service_animal"],
                        p["is_esa"],
                        p["rabies_tag"],
                        p["vaccination_expires"],
                        p["license_number"],
                        p["status"],
                        p["photo_url"],
                        p["notes"],
                        now,
                        now,
                    ),
                )
        conn.commit()
    finally:
        if owns_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Resident Pets CRUD
# ---------------------------------------------------------------------------


def create_resident_pet(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    name: str,
    pet_type: str = PetType.DOG.value,
    breed: str | None = None,
    weight_lbs: float = 0.0,
    color: str | None = None,
    age_years: int | None = None,
    is_service_animal: bool = False,
    is_esa: bool = False,
    rabies_tag: str | None = None,
    vaccination_expires: str | None = None,
    license_number: str | None = None,
    status: str = PetStatus.ACTIVE.value,
    photo_url: str | None = None,
    notes: str | None = None,
    pet_id: str | None = None,
) -> dict[str, Any]:
    """Register a resident pet."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        pid = pet_id or f"pet_{secrets.token_hex(4)}"
        now = datetime.datetime.now(datetime.UTC).isoformat()
        cursor.execute(
            """
            INSERT INTO resident_pets (
                id, tenant_id, unit_id, name, pet_type, breed,
                weight_lbs, color, age_years, is_service_animal, is_esa,
                rabies_tag, vaccination_expires, license_number,
                status, photo_url, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                tenant_id,
                unit_id,
                name.strip(),
                pet_type.lower().strip(),
                breed.strip() if breed else None,
                float(weight_lbs),
                color.strip() if color else None,
                age_years,
                1 if is_service_animal else 0,
                1 if is_esa else 0,
                rabies_tag.strip() if rabies_tag else None,
                vaccination_expires.strip() if vaccination_expires else None,
                license_number.strip() if license_number else None,
                status,
                photo_url.strip() if photo_url else None,
                notes.strip() if notes else None,
                now,
                now,
            ),
        )
        conn.commit()
        return get_resident_pet(pid)  # type: ignore[return-value]
    finally:
        conn.close()


def get_resident_pet(pet_id: str) -> dict[str, Any] | None:
    """Retrieve details for a resident pet."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM resident_pets WHERE id = ?", (pet_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["is_service_animal"] = bool(res.get("is_service_animal"))
        res["is_esa"] = bool(res.get("is_esa"))
        return res
    finally:
        conn.close()


def list_resident_pets(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    pet_type: str | None = None,
    status: str | None = None,
    is_service_animal: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List resident pets with optional filtering and pagination."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM resident_pets WHERE 1=1"
        params: list[Any] = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if pet_type:
            query += " AND pet_type = ?"
            params.append(pet_type.lower().strip())
        if status:
            query += " AND status = ?"
            params.append(status)
        if is_service_animal is not None:
            query += " AND (is_service_animal = ? OR is_esa = ?)"
            val = 1 if is_service_animal else 0
            params.extend([val, val])
        if search:
            query += " AND (name LIKE ? OR breed LIKE ? OR rabies_tag LIKE ?)"
            s = f"%{search.strip()}%"
            params.extend([s, s, s])

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["is_service_animal"] = bool(d.get("is_service_animal"))
            d["is_esa"] = bool(d.get("is_esa"))
            result.append(d)
        return result
    finally:
        conn.close()


def get_tenant_pets(tenant_id: str) -> list[dict[str, Any]]:
    """Retrieve all pets registered to a tenant or residing in their leased unit."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM resident_pets
            WHERE tenant_id = ? OR unit_id IN (
                SELECT unit_id FROM tenants WHERE id = ?
            )
            ORDER BY created_at ASC
            """,
            (tenant_id, tenant_id),
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["is_service_animal"] = bool(d.get("is_service_animal"))
            d["is_esa"] = bool(d.get("is_esa"))
            result.append(d)
        return result
    finally:
        conn.close()


def update_resident_pet(  # noqa: PLR0913, PLR0917
    pet_id: str,
    name: str | None = None,
    pet_type: str | None = None,
    breed: str | None = None,
    weight_lbs: float | None = None,
    color: str | None = None,
    age_years: int | None = None,
    is_service_animal: bool | None = None,
    is_esa: bool | None = None,
    rabies_tag: str | None = None,
    vaccination_expires: str | None = None,
    license_number: str | None = None,
    status: str | None = None,
    photo_url: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update details for an existing resident pet."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        current = get_resident_pet(pet_id)
        if not current:
            return None

        norm_pet_type = pet_type.lower().strip() if pet_type else None
        if norm_pet_type and norm_pet_type not in [p.value for p in PetType]:
            norm_pet_type = PetType.OTHER.value

        now = datetime.datetime.now(datetime.UTC).isoformat()
        cursor.execute(
            """
            UPDATE resident_pets SET
                name = COALESCE(?, name),
                pet_type = COALESCE(?, pet_type),
                breed = COALESCE(?, breed),
                weight_lbs = COALESCE(?, weight_lbs),
                color = COALESCE(?, color),
                age_years = COALESCE(?, age_years),
                is_service_animal = COALESCE(?, is_service_animal),
                is_esa = COALESCE(?, is_esa),
                rabies_tag = COALESCE(?, rabies_tag),
                vaccination_expires = COALESCE(?, vaccination_expires),
                license_number = COALESCE(?, license_number),
                status = COALESCE(?, status),
                photo_url = COALESCE(?, photo_url),
                notes = COALESCE(?, notes),
                updated_at = ?
            WHERE id = ?
            """,
            (
                name.strip() if name is not None else None,
                norm_pet_type,
                breed.strip() if breed is not None else None,
                float(weight_lbs) if weight_lbs is not None else None,
                color.strip() if color is not None else None,
                age_years,
                1 if is_service_animal else (0 if is_service_animal is False else None),
                1 if is_esa else (0 if is_esa is False else None),
                rabies_tag.strip() if rabies_tag is not None else None,
                vaccination_expires.strip() if vaccination_expires is not None else None,
                license_number.strip() if license_number is not None else None,
                status,
                photo_url.strip() if photo_url is not None else None,
                notes.strip() if notes is not None else None,
                now,
                pet_id,
            ),
        )
        conn.commit()
        return get_resident_pet(pet_id)
    finally:
        conn.close()


def delete_resident_pet(pet_id: str) -> bool:
    """Delete or deactivate a resident pet record."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM resident_pets WHERE id = ?", (pet_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pet Policies CRUD
# ---------------------------------------------------------------------------


def create_pet_policy(  # noqa: PLR0913, PLR0917
    property_name: str = "Grand Community Apartments",
    building: str | None = None,
    pet_type: str = "all",
    max_weight_lbs: float = DEFAULT_MAX_WEIGHT,
    max_pets_per_unit: int = DEFAULT_MAX_PETS,
    monthly_pet_rent: float = DEFAULT_PET_RENT,
    one_time_deposit: float = DEFAULT_PET_DEPOSIT,
    restricted_breeds: list[str] | None = None,
    rules_and_restrictions: str | None = None,
    policy_id: str | None = None,
) -> dict[str, Any]:
    """Create a pet policy for a property or specific building."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        pid = policy_id or f"policy_{secrets.token_hex(4)}"
        now = datetime.datetime.now(datetime.UTC).isoformat()
        raw_breeds = (
            restricted_breeds if restricted_breeds is not None else DEFAULT_RESTRICTED_BREEDS
        )
        breeds_json = json.dumps(raw_breeds)
        cursor.execute(
            """
            INSERT INTO pet_policies (
                id, property_name, building, pet_type, max_weight_lbs,
                max_pets_per_unit, monthly_pet_rent, one_time_deposit,
                restricted_breeds, rules_and_restrictions, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                property_name.strip(),
                building.strip() if building else None,
                pet_type.lower().strip(),
                float(max_weight_lbs),
                int(max_pets_per_unit),
                float(monthly_pet_rent),
                float(one_time_deposit),
                breeds_json,
                rules_and_restrictions.strip() if rules_and_restrictions else None,
                now,
                now,
            ),
        )
        conn.commit()
        return get_pet_policy(pid)  # type: ignore[return-value]
    finally:
        conn.close()


def get_pet_policy(policy_id: str) -> dict[str, Any] | None:
    """Retrieve details for a pet policy."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pet_policies WHERE id = ?", (policy_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        try:
            res["restricted_breeds"] = json.loads(res.get("restricted_breeds") or "[]")
        except Exception:
            res["restricted_breeds"] = []
        return res
    finally:
        conn.close()


def list_pet_policies(
    building: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List pet policies."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM pet_policies WHERE 1=1"
        params: list[Any] = []
        if building:
            query += " AND (building = ? OR building IS NULL OR building = 'All Buildings')"
            params.append(building.strip())
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["restricted_breeds"] = json.loads(d.get("restricted_breeds") or "[]")
            except Exception:
                d["restricted_breeds"] = []
            result.append(d)
        return result
    finally:
        conn.close()


def update_pet_policy(  # noqa: PLR0913, PLR0917
    policy_id: str,
    property_name: str | None = None,
    building: str | None = None,
    max_weight_lbs: float | None = None,
    max_pets_per_unit: int | None = None,
    monthly_pet_rent: float | None = None,
    one_time_deposit: float | None = None,
    restricted_breeds: list[str] | None = None,
    rules_and_restrictions: str | None = None,
) -> dict[str, Any] | None:
    """Update pet policy terms, fees, or restrictions."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        current = get_pet_policy(policy_id)
        if not current:
            return None

        now = datetime.datetime.now(datetime.UTC).isoformat()
        breeds_json = json.dumps(restricted_breeds) if restricted_breeds is not None else None

        cursor.execute(
            """
            UPDATE pet_policies SET
                property_name = COALESCE(?, property_name),
                building = COALESCE(?, building),
                max_weight_lbs = COALESCE(?, max_weight_lbs),
                max_pets_per_unit = COALESCE(?, max_pets_per_unit),
                monthly_pet_rent = COALESCE(?, monthly_pet_rent),
                one_time_deposit = COALESCE(?, one_time_deposit),
                restricted_breeds = COALESCE(?, restricted_breeds),
                rules_and_restrictions = COALESCE(?, rules_and_restrictions),
                updated_at = ?
            WHERE id = ?
            """,
            (
                property_name.strip() if property_name is not None else None,
                building.strip() if building is not None else None,
                float(max_weight_lbs) if max_weight_lbs is not None else None,
                int(max_pets_per_unit) if max_pets_per_unit is not None else None,
                float(monthly_pet_rent) if monthly_pet_rent is not None else None,
                float(one_time_deposit) if one_time_deposit is not None else None,
                breeds_json,
                rules_and_restrictions.strip() if rules_and_restrictions is not None else None,
                now,
                policy_id,
            ),
        )
        conn.commit()
        return get_pet_policy(policy_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pet Incidents & Nuisance Reports CRUD
# ---------------------------------------------------------------------------


def record_pet_incident(  # noqa: PLR0913, PLR0917
    incident_type: str,
    incident_date: str | None = None,
    pet_id: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
    fine_amount: float = DEFAULT_PET_FINE,
    status: str = IncidentStatus.REPORTED.value,
    notes: str | None = None,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Record a pet infraction, barking complaint, or off-leash incident."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        iid = incident_id or f"inc_{secrets.token_hex(4)}"
        now = datetime.datetime.now(datetime.UTC).isoformat()
        inc_date = incident_date or now

        # Auto-fill tenant or unit if pet_id is given
        if pet_id and (not tenant_id or not unit_id):
            cursor.execute("SELECT tenant_id, unit_id FROM resident_pets WHERE id = ?", (pet_id,))
            p_row = cursor.fetchone()
            if p_row:
                tenant_id = tenant_id or p_row["tenant_id"]
                unit_id = unit_id or p_row["unit_id"]

        cursor.execute(
            """
            INSERT INTO pet_incidents (
                id, pet_id, tenant_id, unit_id, incident_type,
                incident_date, fine_amount, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                iid,
                pet_id,
                tenant_id,
                unit_id,
                incident_type.lower().strip(),
                inc_date,
                float(fine_amount),
                status,
                notes.strip() if notes else None,
                now,
                now,
            ),
        )
        conn.commit()
        return get_pet_incident(iid)  # type: ignore[return-value]
    finally:
        conn.close()


def get_pet_incident(incident_id: str) -> dict[str, Any] | None:
    """Retrieve details for a pet incident."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pet_incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def list_pet_incidents(  # noqa: PLR0913, PLR0917
    pet_id: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
    incident_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List pet incidents and complaints with optional filters."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM pet_incidents WHERE 1=1"
        params: list[Any] = []

        if pet_id:
            query += " AND pet_id = ?"
            params.append(pet_id)
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if incident_type:
            query += " AND incident_type = ?"
            params.append(incident_type.lower().strip())
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY incident_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def update_pet_incident(
    incident_id: str,
    status: str | None = None,
    fine_amount: float | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update incident status (warning, fine assessed, resolved, disputed) or fine amount."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()
        current = get_pet_incident(incident_id)
        if not current:
            return None

        now = datetime.datetime.now(datetime.UTC).isoformat()
        cursor.execute(
            """
            UPDATE pet_incidents SET
                status = COALESCE(?, status),
                fine_amount = COALESCE(?, fine_amount),
                notes = COALESCE(?, notes),
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                float(fine_amount) if fine_amount is not None else None,
                notes.strip() if notes is not None else None,
                now,
                incident_id,
            ),
        )
        conn.commit()
        return get_pet_incident(incident_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Portfolio Pet Analytics & KPIs
# ---------------------------------------------------------------------------


def get_pet_summary_metrics() -> dict[str, Any]:
    """Retrieve portfolio pet statistics, species counts, and compliance KPIs."""
    init_pets_db()
    conn = db_utils.get_db_connection()
    try:
        cursor = conn.cursor()

        # Pets metrics
        cursor.execute("SELECT COUNT(*) FROM resident_pets WHERE status = 'active'")
        active_pets = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM resident_pets WHERE status = 'active' AND pet_type = 'dog'"
        )
        total_dogs = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM resident_pets WHERE status = 'active' AND pet_type = 'cat'"
        )
        total_cats = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM resident_pets "
            "WHERE status = 'active' AND (is_service_animal = 1 OR is_esa = 1)"
        )
        total_service_animals = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM resident_pets WHERE status = 'pending_approval'")
        pending_approvals = cursor.fetchone()[0]

        # Expiring vaccinations (< 30 days or already expired)
        now_date = datetime.datetime.now(datetime.UTC).date()
        threshold_date = (now_date + datetime.timedelta(days=30)).isoformat()
        cursor.execute(
            """
            SELECT COUNT(*) FROM resident_pets
            WHERE status = 'active' AND vaccination_expires IS NOT NULL AND vaccination_expires <= ?
            """,
            (threshold_date,),
        )
        expiring_vaccinations = cursor.fetchone()[0]

        # Incidents metrics
        cursor.execute(
            "SELECT COUNT(*) FROM pet_incidents "
            "WHERE status IN ('reported', 'warning_issued', 'fine_assessed')"
        )
        active_incidents = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COALESCE(SUM(fine_amount), 0.0) FROM pet_incidents "
            "WHERE status = 'fine_assessed'"
        )
        outstanding_fines = float(cursor.fetchone()[0])

        # Monthly Pet Rent Roll
        cursor.execute("SELECT monthly_pet_rent FROM pet_policies WHERE id = 'policy_default'")
        policy_row = cursor.fetchone()
        pet_rent_rate = float(policy_row[0]) if policy_row else DEFAULT_PET_RENT
        # Service/ESA animals are legally exempt from pet rent
        billable_pets = max(0, active_pets - total_service_animals)
        monthly_pet_revenue = round(billable_pets * pet_rent_rate, 2)

        return {
            "total_active_pets": active_pets,
            "total_dogs": total_dogs,
            "total_cats": total_cats,
            "total_other_pets": max(0, active_pets - total_dogs - total_cats),
            "service_animals_count": total_service_animals,
            "pending_approvals": pending_approvals,
            "expiring_vaccinations_count": expiring_vaccinations,
            "active_incidents_count": active_incidents,
            "outstanding_fines": outstanding_fines,
            "monthly_pet_rent_roll": monthly_pet_revenue,
        }
    finally:
        conn.close()
