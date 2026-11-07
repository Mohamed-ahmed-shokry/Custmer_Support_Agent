"""Database schema, CRUD operations, credentials, guest passes, and access engine."""

from __future__ import annotations

import datetime
import json
import secrets
import sqlite3
from enum import StrEnum
from typing import Any

from api import db_utils

# Constants
DEFAULT_REPLACEMENT_FOB_FEE = 50.0
DEFAULT_ACCESS_CODE_LENGTH = 6
MIN_SEEDED_CREDENTIALS = 2
MIN_SEEDED_PASSES = 1
MIN_SEEDED_INTERCOM = 1


class CredentialType(StrEnum):
    KEY_FOB = "key_fob"
    ACCESS_CARD = "access_card"
    MOBILE_KEY = "mobile_key"
    PIN_CODE = "pin_code"


class CredentialStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOST = "lost"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AccessLevel(StrEnum):
    STANDARD = "standard"
    ALL_ACCESS = "all_access"
    PARKING_ONLY = "parking_only"
    RESIDENT_STAFF = "resident_staff"


class GuestPassType(StrEnum):
    VISITOR = "visitor"
    DELIVERY = "delivery"
    CONTRACTOR = "contractor"
    DOG_WALKER = "dog_walker"
    SERVICE = "service"


class GuestPassStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    USED = "used"
    REVOKED = "revoked"


DEFAULT_SEEDED_CREDENTIALS: list[dict[str, Any]] = [
    {
        "id": "cred_elena_01",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "credential_type": CredentialType.KEY_FOB.value,
        "credential_number": "FOB-9042",
        "status": CredentialStatus.ACTIVE.value,
        "access_level": AccessLevel.ALL_ACCESS.value,
        "assigned_to_name": "Elena Rostova",
        "issued_at": "2026-01-01T00:00:00",
        "expires_at": "2027-01-01T00:00:00",
        "deactivated_at": None,
        "deactivation_reason": None,
        "replacement_fee": DEFAULT_REPLACEMENT_FOB_FEE,
        "notes": "Primary high-security RFID key fob for Penthouse 1 resident.",
    },
    {
        "id": "cred_elena_02",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "credential_type": CredentialType.MOBILE_KEY.value,
        "credential_number": "MOB-3319",
        "status": CredentialStatus.ACTIVE.value,
        "access_level": AccessLevel.STANDARD.value,
        "assigned_to_name": "Elena Rostova",
        "issued_at": "2026-01-01T00:00:00",
        "expires_at": "2027-01-01T00:00:00",
        "deactivated_at": None,
        "deactivation_reason": None,
        "replacement_fee": 0.0,
        "notes": "BLE / NFC smartphone digital mobile key credential.",
    },
]

DEFAULT_SEEDED_GUEST_PASSES: list[dict[str, Any]] = [
    {
        "id": "pass_elena_dogwalker",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "guest_name": "Paws & Walk Dog Walker",
        "guest_phone": "+1-555-0144",
        "pass_type": GuestPassType.DOG_WALKER.value,
        "access_code": "618902",
        "status": GuestPassStatus.ACTIVE.value,
        "valid_from": "2026-01-01T08:00:00",
        "valid_until": "2027-12-31T20:00:00",
        "max_uses": 0,  # 0 indicates unlimited during valid hours
        "uses_count": 14,
        "allowed_zones": json.dumps(["main_lobby", "elevator", "unit_door", "dog_run"]),
        "notes": "Daily dog walking access for Elena's registered pet Barnaby.",
    }
]

DEFAULT_SEEDED_INTERCOM: list[dict[str, Any]] = [
    {
        "id": "dir_elena_01",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "display_name": "Rostova, E.",
        "directory_code": "PH1",
        "forwarding_phone": "+1-555-0199",
        "buzzer_enabled": 1,
        "allow_video": 1,
    }
]


def init_access_control_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize access_credentials, guest_passes, and intercom_directory tables."""
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS access_credentials (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                credential_type TEXT NOT NULL DEFAULT 'key_fob',
                credential_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                access_level TEXT NOT NULL DEFAULT 'standard',
                assigned_to_name TEXT,
                issued_at TEXT NOT NULL,
                expires_at TEXT,
                deactivated_at TEXT,
                deactivation_reason TEXT,
                replacement_fee REAL NOT NULL DEFAULT 50.0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_access_creds_tenant ON access_credentials(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_access_creds_unit ON access_credentials(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_access_creds_status ON access_credentials(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_access_creds_number ON "
            "access_credentials(credential_number)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS guest_passes (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                guest_name TEXT NOT NULL,
                guest_phone TEXT,
                pass_type TEXT NOT NULL DEFAULT 'visitor',
                access_code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                valid_from TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                max_uses INTEGER DEFAULT 1,
                uses_count INTEGER NOT NULL DEFAULT 0,
                allowed_zones TEXT NOT NULL DEFAULT '["main_lobby", "elevator", "unit_door"]',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_guest_passes_tenant ON guest_passes(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_guest_passes_unit ON guest_passes(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_guest_passes_code ON guest_passes(access_code)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_guest_passes_status ON guest_passes(status)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS intercom_directory (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                directory_code TEXT NOT NULL UNIQUE,
                forwarding_phone TEXT NOT NULL,
                buzzer_enabled INTEGER NOT NULL DEFAULT 1,
                allow_video INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_intercom_tenant ON intercom_directory(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_intercom_unit ON intercom_directory(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_intercom_code ON intercom_directory(directory_code)"
        )

        cursor.execute("SELECT COUNT(*) FROM access_credentials")
        row = cursor.fetchone()
        cred_count = row[0] if row else 0
        if cred_count < MIN_SEEDED_CREDENTIALS:
            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            for cred in DEFAULT_SEEDED_CREDENTIALS:
                cursor.execute("SELECT id FROM access_credentials WHERE id = ?", (cred["id"],))
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO access_credentials (
                            id, tenant_id, unit_id, credential_type, credential_number,
                            status, access_level, assigned_to_name, issued_at, expires_at,
                            deactivated_at, deactivation_reason, replacement_fee, notes,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cred["id"],
                            cred["tenant_id"],
                            cred["unit_id"],
                            cred["credential_type"],
                            cred["credential_number"],
                            cred["status"],
                            cred["access_level"],
                            cred["assigned_to_name"],
                            cred["issued_at"],
                            cred["expires_at"],
                            cred["deactivated_at"],
                            cred["deactivation_reason"],
                            cred["replacement_fee"],
                            cred["notes"],
                            now_iso,
                            now_iso,
                        ),
                    )

        cursor.execute("SELECT COUNT(*) FROM guest_passes")
        row = cursor.fetchone()
        pass_count = row[0] if row else 0
        if pass_count < MIN_SEEDED_PASSES:
            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            for pass_data in DEFAULT_SEEDED_GUEST_PASSES:
                cursor.execute("SELECT id FROM guest_passes WHERE id = ?", (pass_data["id"],))
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO guest_passes (
                            id, tenant_id, unit_id, guest_name, guest_phone,
                            pass_type, access_code, status, valid_from, valid_until,
                            max_uses, uses_count, allowed_zones, notes, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            pass_data["id"],
                            pass_data["tenant_id"],
                            pass_data["unit_id"],
                            pass_data["guest_name"],
                            pass_data["guest_phone"],
                            pass_data["pass_type"],
                            pass_data["access_code"],
                            pass_data["status"],
                            pass_data["valid_from"],
                            pass_data["valid_until"],
                            pass_data["max_uses"],
                            pass_data["uses_count"],
                            pass_data["allowed_zones"],
                            pass_data["notes"],
                            now_iso,
                            now_iso,
                        ),
                    )

        cursor.execute("SELECT COUNT(*) FROM intercom_directory")
        row = cursor.fetchone()
        intercom_count = row[0] if row else 0
        if intercom_count < MIN_SEEDED_INTERCOM:
            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            for entry in DEFAULT_SEEDED_INTERCOM:
                cursor.execute("SELECT id FROM intercom_directory WHERE id = ?", (entry["id"],))
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO intercom_directory (
                            id, tenant_id, unit_id, display_name, directory_code,
                            forwarding_phone, buzzer_enabled, allow_video, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry["id"],
                            entry["tenant_id"],
                            entry["unit_id"],
                            entry["display_name"],
                            entry["directory_code"],
                            entry["forwarding_phone"],
                            entry["buzzer_enabled"],
                            entry["allow_video"],
                            now_iso,
                            now_iso,
                        ),
                    )

        conn.commit()
    finally:
        if owns_conn:
            conn.close()


def generate_pin_code(length: int = DEFAULT_ACCESS_CODE_LENGTH) -> str:
    """Generate a cryptographic random numeric PIN code."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


# =========================================================================
# Access Credentials CRUD
# =========================================================================

def create_access_credential(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    credential_type: str = CredentialType.KEY_FOB.value,
    credential_number: str | None = None,
    status: str = CredentialStatus.ACTIVE.value,
    access_level: str = AccessLevel.STANDARD.value,
    assigned_to_name: str | None = None,
    issued_at: str | None = None,
    expires_at: str | None = None,
    replacement_fee: float = DEFAULT_REPLACEMENT_FOB_FEE,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a new access credential record."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cred_id = f"cred_{secrets.token_hex(6)}"
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        final_issued_at = issued_at or now_iso

        if not credential_number:
            prefix_map = {
                CredentialType.KEY_FOB.value: "FOB",
                CredentialType.ACCESS_CARD.value: "CARD",
                CredentialType.MOBILE_KEY.value: "MOB",
            }
            prefix = prefix_map.get(credential_type, "PIN")
            credential_number = f"{prefix}-{secrets.randbelow(9000) + 1000}"

        cursor.execute(
            """
            INSERT INTO access_credentials (
                id, tenant_id, unit_id, credential_type, credential_number,
                status, access_level, assigned_to_name, issued_at, expires_at,
                deactivated_at, deactivation_reason, replacement_fee, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cred_id,
                tenant_id,
                unit_id,
                credential_type,
                credential_number,
                status,
                access_level,
                assigned_to_name,
                final_issued_at,
                expires_at,
                None,
                None,
                replacement_fee,
                notes,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        return get_access_credential(cred_id, conn=conn) or {}
    finally:
        if owns_conn:
            conn.close()


def get_access_credential(
    cred_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Retrieve an access credential by ID."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM access_credentials WHERE id = ?", (cred_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        if owns_conn:
            conn.close()


def list_access_credentials(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    credential_type: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List access credentials with optional filters."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        query = "SELECT * FROM access_credentials WHERE 1=1"
        params: list[Any] = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if credential_type:
            query += " AND credential_type = ?"
            params.append(credential_type)

        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if owns_conn:
            conn.close()


def update_access_credential(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    cred_id: str,
    status: str | None = None,
    access_level: str | None = None,
    assigned_to_name: str | None = None,
    expires_at: str | None = None,
    deactivation_reason: str | None = None,
    replacement_fee: float | None = None,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update mutable fields of an access credential."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        fields: list[str] = []
        params: list[Any] = []

        if status is not None:
            fields.append("status = ?")
            params.append(status)
            deactivated_statuses = (
                CredentialStatus.LOST.value,
                CredentialStatus.REVOKED.value,
                CredentialStatus.SUSPENDED.value,
            )
            if status in deactivated_statuses:
                fields.append("deactivated_at = ?")
                params.append(datetime.datetime.now(datetime.UTC).isoformat())

        if access_level is not None:
            fields.append("access_level = ?")
            params.append(access_level)
        if assigned_to_name is not None:
            fields.append("assigned_to_name = ?")
            params.append(assigned_to_name)
        if expires_at is not None:
            fields.append("expires_at = ?")
            params.append(expires_at)
        if deactivation_reason is not None:
            fields.append("deactivation_reason = ?")
            params.append(deactivation_reason)
        if replacement_fee is not None:
            fields.append("replacement_fee = ?")
            params.append(replacement_fee)
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)

        if not fields:
            return get_access_credential(cred_id, conn=conn)

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        fields.append("updated_at = ?")
        params.append(now_iso)

        params.append(cred_id)
        query = f"UPDATE access_credentials SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return get_access_credential(cred_id, conn=conn)
    finally:
        if owns_conn:
            conn.close()


def delete_access_credential(
    cred_id: str,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Delete an access credential record."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM access_credentials WHERE id = ?", (cred_id,))
        conn.commit()
        return bool(cursor.rowcount > 0)
    finally:
        if owns_conn:
            conn.close()


def report_lost_fob(
    cred_id: str,
    deactivation_reason: str = "Resident reported key fob lost or stolen",
    charge_replacement_fee: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Report a key fob as lost, immediately revoking access and assessing replacement fee."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cred = get_access_credential(cred_id, conn=conn)
        if not cred:
            return None

        fee = DEFAULT_REPLACEMENT_FOB_FEE if charge_replacement_fee else 0.0
        return update_access_credential(
            cred_id=cred_id,
            status=CredentialStatus.LOST.value,
            deactivation_reason=deactivation_reason,
            replacement_fee=fee,
            conn=conn,
        )
    finally:
        if owns_conn:
            conn.close()


# =========================================================================
# Guest Passes CRUD
# =========================================================================

def create_guest_pass(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    guest_name: str,
    guest_phone: str | None = None,
    pass_type: str = GuestPassType.VISITOR.value,
    access_code: str | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
    max_uses: int = 1,
    allowed_zones: list[str] | None = None,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a temporary guest access pass with 6-digit access PIN."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        pass_id = f"pass_{secrets.token_hex(6)}"
        now = datetime.datetime.now(datetime.UTC)
        now_iso = now.isoformat()

        final_valid_from = valid_from or now_iso
        final_valid_until = valid_until or (now + datetime.timedelta(hours=24)).isoformat()
        final_code = access_code or generate_pin_code()
        final_zones = allowed_zones or ["main_lobby", "elevator", "unit_door"]

        cursor.execute(
            """
            INSERT INTO guest_passes (
                id, tenant_id, unit_id, guest_name, guest_phone,
                pass_type, access_code, status, valid_from, valid_until,
                max_uses, uses_count, allowed_zones, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pass_id,
                tenant_id,
                unit_id,
                guest_name,
                guest_phone,
                pass_type,
                final_code,
                GuestPassStatus.ACTIVE.value,
                final_valid_from,
                final_valid_until,
                max_uses,
                0,
                json.dumps(final_zones),
                notes,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        return get_guest_pass(pass_id, conn=conn) or {}
    finally:
        if owns_conn:
            conn.close()


def get_guest_pass(pass_id: str, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Retrieve a guest pass by ID."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM guest_passes WHERE id = ?", (pass_id,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        if isinstance(data.get("allowed_zones"), str):
            try:
                data["allowed_zones"] = json.loads(data["allowed_zones"])
            except Exception:
                data["allowed_zones"] = []
        return data
    finally:
        if owns_conn:
            conn.close()


def list_guest_passes(
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    pass_type: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List guest passes with optional filters."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        query = "SELECT * FROM guest_passes WHERE 1=1"
        params: list[Any] = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if pass_type:
            query += " AND pass_type = ?"
            params.append(pass_type)

        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("allowed_zones"), str):
                try:
                    d["allowed_zones"] = json.loads(d["allowed_zones"])
                except Exception:
                    d["allowed_zones"] = []
            result.append(d)
        return result
    finally:
        if owns_conn:
            conn.close()


def update_guest_pass(  # noqa: PLR0913, PLR0917
    pass_id: str,
    status: str | None = None,
    valid_until: str | None = None,
    allowed_zones: list[str] | None = None,
    notes: str | None = None,
    increment_use: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update a guest pass's parameters or record access usage."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        fields: list[str] = []
        params: list[Any] = []

        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if valid_until is not None:
            fields.append("valid_until = ?")
            params.append(valid_until)
        if allowed_zones is not None:
            fields.append("allowed_zones = ?")
            params.append(json.dumps(allowed_zones))
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)
        if increment_use:
            fields.append("uses_count = uses_count + 1")

        if not fields:
            return get_guest_pass(pass_id, conn=conn)

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        fields.append("updated_at = ?")
        params.append(now_iso)

        params.append(pass_id)
        query = f"UPDATE guest_passes SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        item = get_guest_pass(pass_id, conn=conn)
        if item and item.get("max_uses") and item.get("uses_count", 0) >= item["max_uses"]:
            cursor.execute(
                "UPDATE guest_passes SET status = ? WHERE id = ?",
                (GuestPassStatus.USED.value, pass_id),
            )
            conn.commit()
            item = get_guest_pass(pass_id, conn=conn)

        return item
    finally:
        if owns_conn:
            conn.close()


def delete_guest_pass(pass_id: str, conn: sqlite3.Connection | None = None) -> bool:
    """Delete a guest pass."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM guest_passes WHERE id = ?", (pass_id,))
        conn.commit()
        return bool(cursor.rowcount > 0)
    finally:
        if owns_conn:
            conn.close()


# =========================================================================
# Intercom Directory CRUD
# =========================================================================

def create_intercom_entry(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    display_name: str,
    directory_code: str,
    forwarding_phone: str,
    buzzer_enabled: bool = True,
    allow_video: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a callbox/intercom directory entry."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        entry_id = f"dir_{secrets.token_hex(6)}"
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO intercom_directory (
                id, tenant_id, unit_id, display_name, directory_code,
                forwarding_phone, buzzer_enabled, allow_video, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                tenant_id,
                unit_id,
                display_name,
                directory_code,
                forwarding_phone,
                1 if buzzer_enabled else 0,
                1 if allow_video else 0,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        return get_intercom_entry(entry_id, conn=conn) or {}
    finally:
        if owns_conn:
            conn.close()


def get_intercom_entry(
    entry_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Retrieve an intercom directory entry by ID."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM intercom_directory WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        if owns_conn:
            conn.close()


def list_intercom_entries(
    tenant_id: str | None = None,
    unit_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List intercom directory entries with optional filters."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        query = "SELECT * FROM intercom_directory WHERE 1=1"
        params: list[Any] = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)

        query += " ORDER BY directory_code ASC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if owns_conn:
            conn.close()


def update_intercom_entry(  # noqa: PLR0913, PLR0917
    entry_id: str,
    display_name: str | None = None,
    forwarding_phone: str | None = None,
    buzzer_enabled: bool | None = None,
    allow_video: bool | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update an intercom directory entry."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        fields: list[str] = []
        params: list[Any] = []

        if display_name is not None:
            fields.append("display_name = ?")
            params.append(display_name)
        if forwarding_phone is not None:
            fields.append("forwarding_phone = ?")
            params.append(forwarding_phone)
        if buzzer_enabled is not None:
            fields.append("buzzer_enabled = ?")
            params.append(1 if buzzer_enabled else 0)
        if allow_video is not None:
            fields.append("allow_video = ?")
            params.append(1 if allow_video else 0)

        if not fields:
            return get_intercom_entry(entry_id, conn=conn)

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        fields.append("updated_at = ?")
        params.append(now_iso)

        params.append(entry_id)
        query = f"UPDATE intercom_directory SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return get_intercom_entry(entry_id, conn=conn)
    finally:
        if owns_conn:
            conn.close()


def delete_intercom_entry(entry_id: str, conn: sqlite3.Connection | None = None) -> bool:
    """Delete an intercom directory entry."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM intercom_directory WHERE id = ?", (entry_id,))
        conn.commit()
        return bool(cursor.rowcount > 0)
    finally:
        if owns_conn:
            conn.close()


# =========================================================================
# Summary Metrics & Analytics
# =========================================================================

def get_access_control_summary_metrics(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Calculate aggregate KPIs for access credentials, guest passes, and intercom."""
    init_access_control_db(conn)
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM access_credentials")
        row = cursor.fetchone()
        total_credentials = row[0] if row else 0

        cursor.execute("SELECT COUNT(*) FROM access_credentials WHERE status = 'active'")
        row = cursor.fetchone()
        active_credentials = row[0] if row else 0

        cursor.execute("SELECT COUNT(*) FROM access_credentials WHERE status = 'lost'")
        row = cursor.fetchone()
        lost_credentials = row[0] if row else 0

        cursor.execute(
            "SELECT COUNT(*) FROM access_credentials WHERE credential_type = 'mobile_key'"
        )
        row = cursor.fetchone()
        mobile_keys_count = row[0] if row else 0

        cursor.execute(
            "SELECT COALESCE(SUM(replacement_fee), 0.0) FROM access_credentials "
            "WHERE status = 'lost'"
        )
        row = cursor.fetchone()
        replacement_fees_assessed = float(row[0]) if row else 0.0

        cursor.execute("SELECT COUNT(*) FROM guest_passes")
        row = cursor.fetchone()
        total_guest_passes = row[0] if row else 0

        cursor.execute("SELECT COUNT(*) FROM guest_passes WHERE status = 'active'")
        row = cursor.fetchone()
        active_guest_passes = row[0] if row else 0

        cursor.execute("SELECT COALESCE(SUM(uses_count), 0) FROM guest_passes")
        row = cursor.fetchone()
        total_guest_entries = int(row[0]) if row else 0

        cursor.execute("SELECT COUNT(*) FROM intercom_directory")
        row = cursor.fetchone()
        intercom_directory_count = row[0] if row else 0

        cursor.execute("SELECT COUNT(*) FROM intercom_directory WHERE buzzer_enabled = 1")
        row = cursor.fetchone()
        buzzer_enabled_count = row[0] if row else 0

        return {
            "total_credentials": total_credentials,
            "active_credentials": active_credentials,
            "lost_credentials": lost_credentials,
            "mobile_keys_count": mobile_keys_count,
            "replacement_fees_assessed": replacement_fees_assessed,
            "total_guest_passes": total_guest_passes,
            "active_guest_passes": active_guest_passes,
            "total_guest_entries": total_guest_entries,
            "intercom_directory_count": intercom_directory_count,
            "buzzer_enabled_count": buzzer_enabled_count,
        }
    finally:
        if owns_conn:
            conn.close()
