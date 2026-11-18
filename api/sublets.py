"""Database schema, models, CRUD helpers, approval workflow, and occupancy verification."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils, webhooks

# Constants
DEFAULT_ADMINISTRATIVE_FEE = 150.0  # Standard $150 admin/review fee for sublets
DEFAULT_UNAUTHORIZED_RENTAL_FINE = 250.0  # Standard fine for unauthorized short-term rental
DEFAULT_MAX_OCCUPANCY_PER_BEDROOM = 2
DEFAULT_BASE_OCCUPANCY_ALLOWANCE = 1
MIN_SEEDED_SUBLETS = 2


class SubletType(StrEnum):
    FULL_UNIT = "full_unit"
    PARTIAL_ROOM = "partial_room"
    ROOMMATE_REPLACEMENT = "roommate_replacement"
    LEASE_ASSIGNMENT = "lease_assignment"


class SubletStatus(StrEnum):
    PENDING = "pending"
    BACKGROUND_CHECK = "background_check"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class OccupantType(StrEnum):
    SUBTENANT = "subtenant"
    TEMPORARY_GUEST = "temporary_guest"
    REPLACEMENT_ROOMMATE = "replacement_roommate"
    PERMANENT_OCCUPANT = "permanent_occupant"


class OccupantStatus(StrEnum):
    ACTIVE = "active"
    DEPARTED = "departed"
    REVOKED = "revoked"


class RentalAlertStatus(StrEnum):
    SUSPECTED = "suspected"
    INVESTIGATING = "investigating"
    CONFIRMED_VIOLATION = "confirmed_violation"
    RESOLVED = "resolved"
    CLEARED = "cleared"


def _generate_sublet_id() -> str:
    return f"sub_{secrets.token_hex(4)}"


def _generate_occupant_id() -> str:
    return f"occ_{secrets.token_hex(4)}"


def _generate_alert_id() -> str:
    return f"ura_{secrets.token_hex(4)}"


def init_sublets_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize SQLite tables, triggers, indexes, and initial seeds for sublets and occupancy."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        # 1. Sublet requests table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sublet_requests (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                subtenant_name TEXT NOT NULL,
                subtenant_email TEXT NOT NULL,
                subtenant_phone TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                sublet_type TEXT NOT NULL DEFAULT 'full_unit',
                status TEXT NOT NULL DEFAULT 'pending',
                monthly_rent REAL NOT NULL DEFAULT 0.0,
                administrative_fee REAL NOT NULL DEFAULT 150.0,
                fee_paid INTEGER NOT NULL DEFAULT 0,
                fee_transaction_id TEXT DEFAULT NULL,
                reason TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                reviewed_by TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # 2. Sublet occupants and guests table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sublet_occupants (
                id TEXT PRIMARY KEY,
                sublet_id TEXT DEFAULT NULL REFERENCES sublet_requests(id) ON DELETE SET NULL,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                occupant_type TEXT NOT NULL DEFAULT 'subtenant',
                relationship_to_tenant TEXT NOT NULL DEFAULT 'subtenant',
                id_verified INTEGER NOT NULL DEFAULT 0,
                background_cleared INTEGER NOT NULL DEFAULT 0,
                check_in_date TEXT NOT NULL,
                expected_check_out_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                emergency_contact TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # 3. Unauthorized short-term rental alerts table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS unauthorized_rental_alerts (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                platform TEXT NOT NULL DEFAULT 'airbnb',
                listing_url TEXT NOT NULL DEFAULT '',
                reported_by TEXT NOT NULL DEFAULT 'security_patrol',
                evidence_summary TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'suspected',
                penalty_fee REAL NOT NULL DEFAULT 0.0,
                fee_transaction_id TEXT DEFAULT NULL,
                resolution_notes TEXT NOT NULL DEFAULT '',
                investigated_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # Indexes for fast lookup
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublet_requests_tenant ON sublet_requests(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublet_requests_unit ON sublet_requests(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublet_requests_status ON sublet_requests(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublet_occupants_unit ON sublet_occupants(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublet_occupants_sublet ON sublet_occupants(sublet_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublet_occupants_status ON sublet_occupants(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rental_alerts_unit "
            "ON unauthorized_rental_alerts(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rental_alerts_status "
            "ON unauthorized_rental_alerts(status)"
        )

        conn.commit()
        _seed_default_sublets(conn)
    finally:
        if close_conn:
            conn.close()


def _seed_default_sublets(conn: sqlite3.Connection) -> None:
    """Seed initial sublets, occupants, and rental alert records if not already populated."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sublet_requests")
    count = cursor.fetchone()[0]

    if count < MIN_SEEDED_SUBLETS:
        cursor.execute("SELECT id FROM units ORDER BY id LIMIT 3")
        unit_rows = cursor.fetchall()
        cursor.execute("SELECT id FROM tenants ORDER BY id LIMIT 3")
        tenant_rows = cursor.fetchall()

        if unit_rows and tenant_rows:
            unit_1 = unit_rows[0][0]
            tenant_1 = tenant_rows[0][0]
            unit_2 = unit_rows[1][0] if len(unit_rows) > 1 else unit_1
            tenant_2 = tenant_rows[1][0] if len(tenant_rows) > 1 else tenant_1

            now = datetime.datetime.now(UTC)
            now_iso = now.isoformat()
            today = now.date()

            # Seed 1: Approved sublet request
            sublet_1_id = "sub_seed_101"
            sub1_start = (today + datetime.timedelta(days=14)).isoformat()
            sub1_end = (today + datetime.timedelta(days=120)).isoformat()
            cursor.execute(
                """
                INSERT OR IGNORE INTO sublet_requests (
                    id, tenant_id, unit_id, subtenant_name, subtenant_email,
                    subtenant_phone, start_date, end_date, sublet_type, status,
                    monthly_rent, administrative_fee, fee_paid, fee_transaction_id,
                    reason, notes, reviewed_by, reviewed_at, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, 'Alex Rivera', 'alex.rivera@example.com',
                    '(555) 432-8765', ?, ?, 'full_unit', 'approved',
                    1850.0, 150.0, 1, 'tx_sub_fee_101',
                    'Work assignment in Chicago for 3 months',
                    'Background check cleared, ID verified, fee received.',
                    'Leasing Manager Sarah Jenkins', ?, ?, ?
                )
                """,
                (sublet_1_id, tenant_1, unit_1, sub1_start, sub1_end, now_iso, now_iso, now_iso),
            )

            # Seed 2: Pending roommate replacement request
            sublet_2_id = "sub_seed_102"
            sub2_start = (today + datetime.timedelta(days=7)).isoformat()
            sub2_end = (today + datetime.timedelta(days=180)).isoformat()
            cursor.execute(
                """
                INSERT OR IGNORE INTO sublet_requests (
                    id, tenant_id, unit_id, subtenant_name, subtenant_email,
                    subtenant_phone, start_date, end_date, sublet_type, status,
                    monthly_rent, administrative_fee, fee_paid, fee_transaction_id,
                    reason, notes, reviewed_by, reviewed_at, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, 'Elena Rostova', 'elena.rostova@example.com',
                    '(555) 876-1234', ?, ?, 'roommate_replacement', 'pending',
                    925.0, 150.0, 0, NULL,
                    'Departing roommate relocated for university',
                    'Applicant submitted ID and references; awaiting credit approval.',
                    '', NULL, ?, ?
                )
                """,
                (sublet_2_id, tenant_2, unit_2, sub2_start, sub2_end, now_iso, now_iso),
            )

            # Seed Occupants
            cursor.execute(
                """
                INSERT OR IGNORE INTO sublet_occupants (
                    id, sublet_id, unit_id, tenant_id, full_name, email,
                    phone, occupant_type, relationship_to_tenant, id_verified,
                    background_cleared, check_in_date, expected_check_out_date,
                    status, emergency_contact, notes, created_at, updated_at
                ) VALUES (
                    'occ_seed_101', ?, ?, ?, 'Alex Rivera', 'alex.rivera@example.com',
                    '(555) 432-8765', 'subtenant', 'subtenant', 1, 1,
                    ?, ?, 'active', 'Maria Rivera (555) 999-1122',
                    'Registered subtenant with authorized parking pass', ?, ?
                )
                """,
                (sublet_1_id, unit_1, tenant_1, sub1_start, sub1_end, now_iso, now_iso),
            )

            cursor.execute(
                """
                INSERT OR IGNORE INTO sublet_occupants (
                    id, sublet_id, unit_id, tenant_id, full_name, email,
                    phone, occupant_type, relationship_to_tenant, id_verified,
                    background_cleared, check_in_date, expected_check_out_date,
                    status, emergency_contact, notes, created_at, updated_at
                ) VALUES (
                    'occ_seed_102', NULL, ?, ?, 'Jordan Lee', 'jordan.lee@example.com',
                    '(555) 234-5678', 'temporary_guest', 'sibling', 1, 0,
                    ?, ?, 'active', 'Tenant primary',
                    'Guest staying for visiting academic fellowship', ?, ?
                )
                """,
                (
                    unit_2,
                    tenant_2,
                    (today - datetime.timedelta(days=5)).isoformat(),
                    (today + datetime.timedelta(days=25)).isoformat(),
                    now_iso,
                    now_iso,
                ),
            )

            # Seed Unauthorized Rental Alert
            cursor.execute(
                """
                INSERT OR IGNORE INTO unauthorized_rental_alerts (
                    id, unit_id, tenant_id, platform, listing_url, reported_by,
                    evidence_summary, status, penalty_fee, fee_transaction_id,
                    resolution_notes, investigated_by, created_at, updated_at
                ) VALUES (
                    'ura_seed_101', ?, ?, 'airbnb',
                    'https://airbnb.com/rooms/seed-test-unit', 'concierge_desk',
                    'Weekend guests seen carrying lockboxes and luggage asking for Unit 101 keys.',
                    'investigating', 0.0, NULL,
                    'Security confirmed exterior keybox removed; awaiting resident interview.',
                    'Property Manager David Vance', ?, ?
                )
                """,
                (unit_1, tenant_1, now_iso, now_iso),
            )

            conn.commit()


# Sublet Requests CRUD & Workflow
def create_sublet_request(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    subtenant_name: str,
    subtenant_email: str,
    start_date: str,
    end_date: str,
    subtenant_phone: str = "",
    sublet_type: str = SubletType.FULL_UNIT,
    monthly_rent: float = 0.0,
    administrative_fee: float = DEFAULT_ADMINISTRATIVE_FEE,
    reason: str = "",
    notes: str = "",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create a new sublet authorization request."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        sublet_id = _generate_sublet_id()
        now_iso = datetime.datetime.now(UTC).isoformat()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO sublet_requests (
                id, tenant_id, unit_id, subtenant_name, subtenant_email,
                subtenant_phone, start_date, end_date, sublet_type, status,
                monthly_rent, administrative_fee, fee_paid, fee_transaction_id,
                reason, notes, reviewed_by, reviewed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0, NULL, ?, ?, '', NULL, ?, ?)
            """,
            (
                sublet_id,
                tenant_id,
                unit_id,
                subtenant_name.strip(),
                subtenant_email.strip(),
                subtenant_phone.strip(),
                start_date.strip(),
                end_date.strip(),
                sublet_type,
                float(monthly_rent),
                float(administrative_fee),
                reason.strip(),
                notes.strip(),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

        # Dispatch webhook
        webhooks.dispatch_event(
            "sublet.requested",
            {
                "sublet_id": sublet_id,
                "tenant_id": tenant_id,
                "unit_id": unit_id,
                "subtenant_name": subtenant_name,
                "sublet_type": sublet_type,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        result = get_sublet_request(sublet_id, conn)
        return result or {}
    finally:
        if close_conn:
            conn.close()


def get_sublet_request(
    sublet_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve details of a sublet request by ID with joined tenant and unit info."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM sublet_requests s
            LEFT JOIN tenants t ON s.tenant_id = t.id
            LEFT JOIN units u ON s.unit_id = u.id
            WHERE s.id = ?
            """,
            (sublet_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        col_names = [description[0] for description in cursor.description]
        return dict(zip(col_names, row, strict=False))
    finally:
        if close_conn:
            conn.close()


def list_sublet_requests(  # noqa: PLR0912, PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    sublet_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List sublet requests matching given filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()

        query = """
            SELECT s.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM sublet_requests s
            LEFT JOIN tenants t ON s.tenant_id = t.id
            LEFT JOIN units u ON s.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []

        if tenant_id:
            query += " AND s.tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND s.unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND s.status = ?"
            params.append(status)
        if sublet_type:
            query += " AND s.sublet_type = ?"
            params.append(sublet_type)

        query += " ORDER BY s.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        return [dict(zip(col_names, r, strict=False)) for r in rows]
    finally:
        if close_conn:
            conn.close()


def update_sublet_request(
    sublet_id: str,
    updates: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update fields on an existing sublet request."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        current = get_sublet_request(sublet_id, conn)
        if not current:
            return None

        allowed_fields = {
            "subtenant_name",
            "subtenant_email",
            "subtenant_phone",
            "start_date",
            "end_date",
            "sublet_type",
            "status",
            "monthly_rent",
            "administrative_fee",
            "fee_paid",
            "fee_transaction_id",
            "reason",
            "notes",
            "reviewed_by",
            "reviewed_at",
        }

        set_clauses: list[str] = []
        params: list[Any] = []

        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = ?")
                params.append(value)

        if not set_clauses:
            return current

        set_clauses.append("updated_at = ?")
        params.append(datetime.datetime.now(UTC).isoformat())
        params.append(sublet_id)

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE sublet_requests SET {', '.join(set_clauses)} WHERE id = ?",  # noqa: S608
            params,
        )
        conn.commit()

        return get_sublet_request(sublet_id, conn)
    finally:
        if close_conn:
            conn.close()


def approve_sublet_request(  # noqa: PLR0913, PLR0917
    sublet_id: str,
    reviewed_by: str,
    assess_fee: bool = True,
    fee_amount: float = DEFAULT_ADMINISTRATIVE_FEE,
    notes: str = "",
    auto_register_occupant: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Approve a sublet request, optionally assess fee to ledger, and auto-register occupant."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        sublet = get_sublet_request(sublet_id, conn)
        if not sublet:
            return None

        now_iso = datetime.datetime.now(UTC).isoformat()
        today = datetime.datetime.now(UTC).date().isoformat()
        new_status = (
            SubletStatus.ACTIVE if sublet["start_date"] <= today else SubletStatus.APPROVED
        )

        fee_tx_id = sublet.get("fee_transaction_id")
        fee_paid = sublet.get("fee_paid", 0)

        if assess_fee and not fee_tx_id:
            fee_res = assess_sublet_fee(sublet_id, fee_amount=fee_amount, conn=conn)
            if fee_res:
                fee_tx_id = fee_res["transaction_id"]
                fee_paid = 1

        review_notes = (
            f"{sublet.get('notes', '')}\nApproval notes: {notes}".strip()
            if notes
            else sublet.get("notes", "")
        )

        updates = {
            "status": new_status,
            "reviewed_by": reviewed_by,
            "reviewed_at": now_iso,
            "notes": review_notes,
            "fee_paid": fee_paid,
            "fee_transaction_id": fee_tx_id,
        }
        updated = update_sublet_request(sublet_id, updates, conn=conn)

        # Auto-register occupant if desired and not already registered
        if auto_register_occupant and updated:
            existing_occ = list_occupants(sublet_id=sublet_id, conn=conn)
            if not existing_occ:
                register_occupant(
                    unit_id=updated["unit_id"],
                    tenant_id=updated["tenant_id"],
                    full_name=updated["subtenant_name"],
                    email=updated["subtenant_email"],
                    phone=updated["subtenant_phone"],
                    sublet_id=sublet_id,
                    occupant_type=OccupantType.SUBTENANT,
                    relationship_to_tenant="subtenant",
                    id_verified=1,
                    background_cleared=1,
                    check_in_date=updated["start_date"],
                    expected_check_out_date=updated["end_date"],
                    notes=f"Auto-registered upon approval of sublet {sublet_id}",
                    conn=conn,
                )

        # Dispatch webhook
        webhooks.dispatch_event(
            "sublet.approved",
            {
                "sublet_id": sublet_id,
                "tenant_id": sublet["tenant_id"],
                "unit_id": sublet["unit_id"],
                "status": new_status,
                "reviewed_by": reviewed_by,
                "fee_assessed": assess_fee,
                "fee_amount": fee_amount,
            },
        )

        return updated
    finally:
        if close_conn:
            conn.close()


def reject_sublet_request(
    sublet_id: str,
    reason: str,
    reviewed_by: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Reject a sublet request with recorded reason."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        sublet = get_sublet_request(sublet_id, conn)
        if not sublet:
            return None

        now_iso = datetime.datetime.now(UTC).isoformat()
        review_notes = f"{sublet.get('notes', '')}\nRejection reason: {reason}".strip()

        updates = {
            "status": SubletStatus.REJECTED,
            "reviewed_by": reviewed_by,
            "reviewed_at": now_iso,
            "notes": review_notes,
        }
        updated = update_sublet_request(sublet_id, updates, conn=conn)

        # Dispatch webhook
        webhooks.dispatch_event(
            "sublet.rejected",
            {
                "sublet_id": sublet_id,
                "tenant_id": sublet["tenant_id"],
                "unit_id": sublet["unit_id"],
                "reason": reason,
                "reviewed_by": reviewed_by,
            },
        )

        return updated
    finally:
        if close_conn:
            conn.close()


def assess_sublet_fee(
    sublet_id: str,
    fee_amount: float = DEFAULT_ADMINISTRATIVE_FEE,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Assess and post a sublet administrative review fee directly to resident rent ledger."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        sublet = get_sublet_request(sublet_id, conn)
        if not sublet:
            return None

        tenant_id = sublet["tenant_id"]
        unit_id = sublet["unit_id"]
        now_iso = datetime.datetime.now(UTC).isoformat()
        now_date = datetime.datetime.now(UTC).date().isoformat()
        cursor = conn.cursor()

        tx_id = f"tx_sub_fee_{secrets.token_hex(4)}"
        desc = f"Sublet administrative & background review fee for {sublet['subtenant_name']}"
        cursor.execute(
            """
            INSERT INTO billing_transactions (
                id, tenant_id, unit_id, transaction_type, amount,
                status, due_date, description, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 'sublet_fee', ?, 'posted', ?, ?, ?, ?, ?)
            """,
            (
                tx_id,
                tenant_id,
                unit_id,
                fee_amount,
                now_date,
                desc,
                f"Assessed for sublet request {sublet_id}",
                now_iso,
                now_iso,
            ),
        )

        cursor.execute(
            """
            UPDATE sublet_requests
            SET fee_paid = 1, fee_transaction_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (tx_id, now_iso, sublet_id),
        )
        conn.commit()

        # Dispatch webhook
        webhooks.dispatch_event(
            "sublet.fee_assessed",
            {
                "sublet_id": sublet_id,
                "tenant_id": tenant_id,
                "unit_id": unit_id,
                "fee_amount": fee_amount,
                "transaction_id": tx_id,
            },
        )

        return {
            "sublet_id": sublet_id,
            "transaction_id": tx_id,
            "tenant_id": tenant_id,
            "unit_id": unit_id,
            "fee_amount": fee_amount,
            "status": "posted",
            "posted_at": now_iso,
        }
    finally:
        if close_conn:
            conn.close()


# Occupants & Guests Management
def register_occupant(  # noqa: PLR0913, PLR0917
    unit_id: str,
    tenant_id: str,
    full_name: str,
    check_in_date: str,
    sublet_id: str | None = None,
    email: str = "",
    phone: str = "",
    occupant_type: str = OccupantType.SUBTENANT,
    relationship_to_tenant: str = "subtenant",
    id_verified: int = 0,
    background_cleared: int = 0,
    expected_check_out_date: str = "",
    emergency_contact: str = "",
    notes: str = "",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Register an authorized occupant, subtenant, or temporary guest."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        occ_id = _generate_occupant_id()
        now_iso = datetime.datetime.now(UTC).isoformat()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO sublet_occupants (
                id, sublet_id, unit_id, tenant_id, full_name, email,
                phone, occupant_type, relationship_to_tenant, id_verified,
                background_cleared, check_in_date, expected_check_out_date,
                status, emergency_contact, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                occ_id,
                sublet_id,
                unit_id,
                tenant_id,
                full_name.strip(),
                email.strip(),
                phone.strip(),
                occupant_type,
                relationship_to_tenant.strip(),
                int(id_verified),
                int(background_cleared),
                check_in_date.strip(),
                expected_check_out_date.strip(),
                emergency_contact.strip(),
                notes.strip(),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

        result = get_occupant(occ_id, conn)
        return result or {}
    finally:
        if close_conn:
            conn.close()


def get_occupant(
    occupant_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve details of a registered occupant by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT o.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM sublet_occupants o
            LEFT JOIN tenants t ON o.tenant_id = t.id
            LEFT JOIN units u ON o.unit_id = u.id
            WHERE o.id = ?
            """,
            (occupant_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        col_names = [desc[0] for desc in cursor.description]
        return dict(zip(col_names, row, strict=False))
    finally:
        if close_conn:
            conn.close()


def list_occupants(  # noqa: PLR0912, PLR0913, PLR0917
    unit_id: str | None = None,
    tenant_id: str | None = None,
    sublet_id: str | None = None,
    status: str | None = None,
    occupant_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List registered occupants matching given filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()

        query = """
            SELECT o.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM sublet_occupants o
            LEFT JOIN tenants t ON o.tenant_id = t.id
            LEFT JOIN units u ON o.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []

        if unit_id:
            query += " AND o.unit_id = ?"
            params.append(unit_id)
        if tenant_id:
            query += " AND o.tenant_id = ?"
            params.append(tenant_id)
        if sublet_id:
            query += " AND o.sublet_id = ?"
            params.append(sublet_id)
        if status:
            query += " AND o.status = ?"
            params.append(status)
        if occupant_type:
            query += " AND o.occupant_type = ?"
            params.append(occupant_type)

        query += " ORDER BY o.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        return [dict(zip(col_names, r, strict=False)) for r in rows]
    finally:
        if close_conn:
            conn.close()


def update_occupant(
    occupant_id: str,
    updates: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update fields on an existing registered occupant."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        current = get_occupant(occupant_id, conn)
        if not current:
            return None

        allowed = {
            "full_name",
            "email",
            "phone",
            "occupant_type",
            "relationship_to_tenant",
            "id_verified",
            "background_cleared",
            "check_in_date",
            "expected_check_out_date",
            "status",
            "emergency_contact",
            "notes",
        }

        set_clauses: list[str] = []
        params: list[Any] = []

        for f, v in updates.items():
            if f in allowed:
                set_clauses.append(f"{f} = ?")
                params.append(v)

        if not set_clauses:
            return current

        set_clauses.append("updated_at = ?")
        params.append(datetime.datetime.now(UTC).isoformat())
        params.append(occupant_id)

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE sublet_occupants SET {', '.join(set_clauses)} WHERE id = ?",  # noqa: S608
            params,
        )
        conn.commit()

        return get_occupant(occupant_id, conn)
    finally:
        if close_conn:
            conn.close()


def calculate_unit_occupancy(
    unit_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Calculate unit occupancy threshold (2 * bedrooms + 1) and active occupants."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()

        # Check unit details
        cursor.execute(
            "SELECT unit_number, building_name, notes FROM units WHERE id = ?",
            (unit_id,),
        )
        unit_row = cursor.fetchone()
        unit_number = unit_row[0] if unit_row else unit_id
        building_name = unit_row[1] if unit_row else ""

        # Estimate bedrooms from unit_number or default: e.g. 2 bedrooms for 2xx units, 1 otherwise
        bedrooms = 2 if "2" in unit_number else 1
        max_limit = (
            bedrooms * DEFAULT_MAX_OCCUPANCY_PER_BEDROOM
        ) + DEFAULT_BASE_OCCUPANCY_ALLOWANCE

        # Count active primary tenants in this unit
        cursor.execute(
            "SELECT COUNT(*) FROM tenants WHERE unit_id = ?",
            (unit_id,),
        )
        active_tenants = cursor.fetchone()[0]

        # Count active registered occupants in sublet_occupants
        cursor.execute(
            "SELECT COUNT(*) FROM sublet_occupants WHERE unit_id = ? AND status = 'active'",
            (unit_id,),
        )
        active_occupants = cursor.fetchone()[0]

        total_current = active_tenants + active_occupants
        is_over = total_current > max_limit
        remaining = max(0, max_limit - total_current)

        return {
            "unit_id": unit_id,
            "unit_number": unit_number,
            "building_name": building_name,
            "estimated_bedrooms": bedrooms,
            "max_occupancy_limit": max_limit,
            "active_tenant_count": active_tenants,
            "active_occupant_count": active_occupants,
            "total_current_occupancy": total_current,
            "is_over_capacity": is_over,
            "remaining_capacity": remaining,
        }
    finally:
        if close_conn:
            conn.close()


# Unauthorized Short-Term Rental Alerts
def report_unauthorized_rental(  # noqa: PLR0913, PLR0917
    unit_id: str,
    tenant_id: str,
    evidence_summary: str,
    platform: str = "airbnb",
    listing_url: str = "",
    reported_by: str = "security_patrol",
    status: str = RentalAlertStatus.SUSPECTED,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Log an incident or investigation report for suspected unauthorized short-term rental."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        alert_id = _generate_alert_id()
        now_iso = datetime.datetime.now(UTC).isoformat()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO unauthorized_rental_alerts (
                id, unit_id, tenant_id, platform, listing_url, reported_by,
                evidence_summary, status, penalty_fee, fee_transaction_id,
                resolution_notes, investigated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, NULL, '', '', ?, ?)
            """,
            (
                alert_id,
                unit_id,
                tenant_id,
                platform.strip(),
                listing_url.strip(),
                reported_by.strip(),
                evidence_summary.strip(),
                status,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

        # Dispatch webhook
        webhooks.dispatch_event(
            "sublet.violation_detected",
            {
                "alert_id": alert_id,
                "unit_id": unit_id,
                "tenant_id": tenant_id,
                "platform": platform,
                "evidence_summary": evidence_summary,
            },
        )

        result = get_unauthorized_rental_alert(alert_id, conn)
        return result or {}
    finally:
        if close_conn:
            conn.close()


def get_unauthorized_rental_alert(
    alert_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve details of an unauthorized rental alert by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM unauthorized_rental_alerts a
            LEFT JOIN tenants t ON a.tenant_id = t.id
            LEFT JOIN units u ON a.unit_id = u.id
            WHERE a.id = ?
            """,
            (alert_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        col_names = [desc[0] for desc in cursor.description]
        return dict(zip(col_names, row, strict=False))
    finally:
        if close_conn:
            conn.close()


def list_unauthorized_rental_alerts(  # noqa: PLR0913, PLR0917
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List unauthorized rental alerts matching filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()

        query = """
            SELECT a.*, t.first_name, t.last_name, u.unit_number, u.building_name
            FROM unauthorized_rental_alerts a
            LEFT JOIN tenants t ON a.tenant_id = t.id
            LEFT JOIN units u ON a.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []

        if unit_id:
            query += " AND a.unit_id = ?"
            params.append(unit_id)
        if tenant_id:
            query += " AND a.tenant_id = ?"
            params.append(tenant_id)
        if status:
            query += " AND a.status = ?"
            params.append(status)

        query += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        return [dict(zip(col_names, r, strict=False)) for r in rows]
    finally:
        if close_conn:
            conn.close()


def update_unauthorized_rental_alert(
    alert_id: str,
    updates: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update status, resolution notes, or investigator on an alert."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        current = get_unauthorized_rental_alert(alert_id, conn)
        if not current:
            return None

        allowed = {
            "status",
            "penalty_fee",
            "fee_transaction_id",
            "resolution_notes",
            "investigated_by",
            "evidence_summary",
        }

        set_clauses: list[str] = []
        params: list[Any] = []

        for f, v in updates.items():
            if f in allowed:
                set_clauses.append(f"{f} = ?")
                params.append(v)

        if not set_clauses:
            return current

        set_clauses.append("updated_at = ?")
        params.append(datetime.datetime.now(UTC).isoformat())
        params.append(alert_id)

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE unauthorized_rental_alerts SET {', '.join(set_clauses)} WHERE id = ?",  # noqa: S608
            params,
        )
        conn.commit()

        return get_unauthorized_rental_alert(alert_id, conn)
    finally:
        if close_conn:
            conn.close()


def assess_unauthorized_rental_fine(
    alert_id: str,
    fine_amount: float = DEFAULT_UNAUTHORIZED_RENTAL_FINE,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Assess and post a violation penalty fine directly to resident rent ledger."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        alert = get_unauthorized_rental_alert(alert_id, conn)
        if not alert:
            return None

        tenant_id = alert["tenant_id"]
        unit_id = alert["unit_id"]
        now_iso = datetime.datetime.now(UTC).isoformat()
        now_date = datetime.datetime.now(UTC).date().isoformat()
        cursor = conn.cursor()

        tx_id = f"tx_sub_fine_{secrets.token_hex(4)}"
        platform_name = alert["platform"].capitalize()
        desc = f"Unauthorized short-term rental violation penalty ({platform_name})"
        cursor.execute(
            """
            INSERT INTO billing_transactions (
                id, tenant_id, unit_id, transaction_type, amount,
                status, due_date, description, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 'violation_fine', ?, 'posted', ?, ?, ?, ?, ?)
            """,
            (
                tx_id,
                tenant_id,
                unit_id,
                fine_amount,
                now_date,
                desc,
                f"Assessed for unauthorized rental alert {alert_id}",
                now_iso,
                now_iso,
            ),
        )

        cursor.execute(
            """
            UPDATE unauthorized_rental_alerts
            SET penalty_fee = ?, fee_transaction_id = ?,
                status = 'confirmed_violation', updated_at = ?
            WHERE id = ?
            """,
            (fine_amount, tx_id, now_iso, alert_id),
        )
        conn.commit()

        # Webhook
        webhooks.dispatch_event(
            "sublet.fee_assessed",
            {
                "alert_id": alert_id,
                "tenant_id": tenant_id,
                "unit_id": unit_id,
                "fine_amount": fine_amount,
                "transaction_id": tx_id,
            },
        )

        return {
            "alert_id": alert_id,
            "transaction_id": tx_id,
            "tenant_id": tenant_id,
            "unit_id": unit_id,
            "fine_amount": fine_amount,
            "status": "posted",
            "posted_at": now_iso,
        }
    finally:
        if close_conn:
            conn.close()


# Summaries & Metrics
def get_unit_sublet_summary(
    unit_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Retrieve unit sublets, active occupants, occupancy thresholds, and rental alerts."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        sublets = list_sublet_requests(unit_id=unit_id, conn=conn)
        occupants = list_occupants(unit_id=unit_id, conn=conn)
        alerts = list_unauthorized_rental_alerts(unit_id=unit_id, conn=conn)
        occupancy = calculate_unit_occupancy(unit_id, conn=conn)

        active_sublet = next(
            (s for s in sublets if s["status"] in (SubletStatus.ACTIVE, SubletStatus.APPROVED)),
            None,
        )

        return {
            "unit_id": unit_id,
            "occupancy": occupancy,
            "active_sublet": active_sublet,
            "total_sublet_requests": len(sublets),
            "sublets": sublets,
            "registered_occupants": occupants,
            "rental_alerts": alerts,
        }
    finally:
        if close_conn:
            conn.close()


def get_tenant_sublet_summary(
    tenant_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Retrieve tenant sublets, registered occupants, and relevant rental alerts."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        sublets = list_sublet_requests(tenant_id=tenant_id, conn=conn)
        occupants = list_occupants(tenant_id=tenant_id, conn=conn)
        alerts = list_unauthorized_rental_alerts(tenant_id=tenant_id, conn=conn)

        active_sublet = next(
            (s for s in sublets if s["status"] in (SubletStatus.ACTIVE, SubletStatus.APPROVED)),
            None,
        )

        return {
            "tenant_id": tenant_id,
            "active_sublet": active_sublet,
            "total_sublet_requests": len(sublets),
            "sublets": sublets,
            "registered_occupants": occupants,
            "rental_alerts": alerts,
        }
    finally:
        if close_conn:
            conn.close()


def get_sublet_metrics_summary(
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Aggregate portfolio-level metrics for sublets, occupants, and rental alerts."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_sublets_db(conn)
        cursor = conn.cursor()

        # Total sublets
        cursor.execute("SELECT COUNT(*) FROM sublet_requests")
        total_sublets = cursor.fetchone()[0]

        # By status
        cursor.execute(
            "SELECT status, COUNT(*) FROM sublet_requests GROUP BY status"
        )
        status_counts = dict(cursor.fetchall())

        # By type
        cursor.execute(
            "SELECT sublet_type, COUNT(*) FROM sublet_requests GROUP BY sublet_type"
        )
        type_counts = dict(cursor.fetchall())

        # Total occupants
        cursor.execute("SELECT COUNT(*) FROM sublet_occupants")
        total_occupants = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sublet_occupants WHERE status = 'active'")
        active_occupants = cursor.fetchone()[0]

        # Total rental alerts
        cursor.execute("SELECT COUNT(*) FROM unauthorized_rental_alerts")
        total_alerts = cursor.fetchone()[0]

        cursor.execute(
            "SELECT status, COUNT(*) FROM unauthorized_rental_alerts GROUP BY status"
        )
        alert_status_counts = dict(cursor.fetchall())

        # Administrative fees assessed
        cursor.execute(
            "SELECT SUM(administrative_fee) FROM sublet_requests WHERE fee_paid = 1"
        )
        fee_sum = cursor.fetchone()[0] or 0.0

        return {
            "total_sublet_requests": total_sublets,
            "pending_requests": status_counts.get(SubletStatus.PENDING, 0),
            "approved_requests": status_counts.get(SubletStatus.APPROVED, 0),
            "active_sublets": status_counts.get(SubletStatus.ACTIVE, 0),
            "completed_sublets": status_counts.get(SubletStatus.COMPLETED, 0),
            "rejected_requests": status_counts.get(SubletStatus.REJECTED, 0),
            "sublets_by_status": status_counts,
            "sublets_by_type": type_counts,
            "total_registered_occupants": total_occupants,
            "active_occupants": active_occupants,
            "total_rental_alerts": total_alerts,
            "active_investigations": alert_status_counts.get(RentalAlertStatus.INVESTIGATING, 0)
            + alert_status_counts.get(RentalAlertStatus.SUSPECTED, 0),
            "confirmed_violations": alert_status_counts.get(
                RentalAlertStatus.CONFIRMED_VIOLATION, 0
            ),
            "rental_alerts_by_status": alert_status_counts,
            "total_administrative_fees_collected": float(fee_sum),
        }
    finally:
        if close_conn:
            conn.close()
