"""Database schema, CRUD operations, incident reporting, violation notices, and appeals engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from enum import StrEnum
from typing import Any

from api import db_utils

# Constants
DEFAULT_CURE_DAYS = 7
DEFAULT_APPEAL_DAYS = 14
DEFAULT_VIOLATION_FINE = 50.0
MIN_SEEDED_INCIDENTS = 1
MIN_SEEDED_NOTICES = 1
MIN_SEEDED_APPEALS = 1


class IncidentType(StrEnum):
    NOISE_COMPLAINT = "noise_complaint"
    SMOKING_PROHIBITED = "smoking_prohibited"
    UNAUTHORIZED_OCCUPANT = "unauthorized_occupant"
    PET_WASTE_VIOLATION = "pet_waste_violation"
    PARKING_IMPROPER = "parking_improper"
    TRASH_DISPOSAL = "trash_disposal"
    COMMON_AREA_DAMAGE = "common_area_damage"
    ALTERATION_UNAPPROVED = "alteration_unapproved"
    SAFETY_HAZARD = "safety_hazard"
    OTHER = "other"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    REPORTED = "reported"
    UNDER_INVESTIGATION = "under_investigation"
    NOTICE_ISSUED = "notice_issued"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class NoticeType(StrEnum):
    COURTESY_WARNING = "courtesy_warning"
    FIRST_NOTICE_TO_CURE = "first_notice_to_cure"
    SECOND_NOTICE_TO_CURE = "second_notice_to_cure"
    FINAL_NOTICE_TO_VACATE = "final_notice_to_vacate"
    FINE_ASSESSMENT = "fine_assessment"
    LEGAL_REFERRAL = "legal_referral"


class ViolationStatus(StrEnum):
    ISSUED = "issued"
    CURED = "cured"
    ESCALATED = "escalated"
    APPEALED = "appealed"
    CLOSED = "closed"


class AppealStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    WAIVED = "waived"
    UPHELD = "upheld"
    REDUCED = "reduced"


DEFAULT_SEEDED_INCIDENTS: list[dict[str, Any]] = [
    {
        "id": "inc_elena_noise_01",
        "incident_number": "INC-2026-101",
        "incident_type": IncidentType.NOISE_COMPLAINT.value,
        "severity": IncidentSeverity.MEDIUM.value,
        "status": IncidentStatus.NOTICE_ISSUED.value,
        "unit_id": "unit_PH1",
        "tenant_id": "tenant_3",
        "reported_by": "neighbor",
        "reporter_name": "Resident Unit 14B",
        "incident_date": "2026-11-04T23:15:00Z",
        "location": "Unit PH1 Balcony / Terrace",
        "description": "Loud music and elevated gathering noise reported past 11 PM quiet hours.",
        "action_taken": "Courtesy warning notice issued to resident.",
        "resolution_notes": (
            "First recorded noise report; resident cooperated upon notice delivery."
        ),
        "resolved_at": None,
    }
]

DEFAULT_SEEDED_NOTICES: list[dict[str, Any]] = [
    {
        "id": "viol_elena_01",
        "notice_number": "VN-2026-089",
        "incident_id": "inc_elena_noise_01",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "violation_type": IncidentType.NOISE_COMPLAINT.value,
        "notice_type": NoticeType.COURTESY_WARNING.value,
        "status": ViolationStatus.ISSUED.value,
        "issued_at": "2026-11-05T09:00:00Z",
        "cure_deadline": "2026-11-12T23:59:59Z",
        "fine_amount": 0.0,
        "fine_charged_to_ledger": 0,
        "remedy_instructions": (
            "Maintain audio levels below 55 dB after 10 PM quiet hours per community rules."
        ),
        "notes": "Courtesy warning for first offense; no monetary fee assessed.",
        "cured_at": None,
    }
]

DEFAULT_SEEDED_APPEALS: list[dict[str, Any]] = [
    {
        "id": "appeal_elena_01",
        "appeal_number": "APL-2026-042",
        "notice_id": "viol_elena_01",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "status": AppealStatus.UNDER_REVIEW.value,
        "reason": "Music was played from neighbor's outdoor sound system on adjacent roof deck.",
        "submitted_at": "2026-11-05T14:30:00Z",
        "reviewed_by": "Property Management Staff",
        "decision_notes": "Investigating roof deck proximity and sound transmission.",
        "adjusted_fine_amount": 0.0,
        "decided_at": None,
    }
]


def init_incidents_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize community_incidents, violation_notices, and violation_appeals tables."""
    owns_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        owns_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS community_incidents (
                id TEXT PRIMARY KEY,
                incident_number TEXT NOT NULL UNIQUE,
                incident_type TEXT NOT NULL DEFAULT 'noise_complaint',
                severity TEXT NOT NULL DEFAULT 'low',
                status TEXT NOT NULL DEFAULT 'reported',
                unit_id TEXT,
                tenant_id TEXT,
                reported_by TEXT NOT NULL DEFAULT 'resident',
                reporter_name TEXT,
                incident_date TEXT NOT NULL,
                location TEXT,
                description TEXT NOT NULL,
                action_taken TEXT,
                resolution_notes TEXT,
                resolved_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidents_tenant ON community_incidents(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidents_unit ON community_incidents(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidents_status ON community_incidents(status)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS violation_notices (
                id TEXT PRIMARY KEY,
                notice_number TEXT NOT NULL UNIQUE,
                incident_id TEXT,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                violation_type TEXT NOT NULL DEFAULT 'noise_complaint',
                notice_type TEXT NOT NULL DEFAULT 'courtesy_warning',
                status TEXT NOT NULL DEFAULT 'issued',
                issued_at TEXT NOT NULL,
                cure_deadline TEXT,
                fine_amount REAL NOT NULL DEFAULT 0.0,
                fine_charged_to_ledger INTEGER NOT NULL DEFAULT 0,
                remedy_instructions TEXT NOT NULL,
                notes TEXT,
                cured_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (incident_id) REFERENCES community_incidents(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notices_tenant ON violation_notices(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notices_unit ON violation_notices(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notices_status ON violation_notices(status)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS violation_appeals (
                id TEXT PRIMARY KEY,
                appeal_number TEXT NOT NULL UNIQUE,
                notice_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'submitted',
                reason TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                reviewed_by TEXT,
                decision_notes TEXT,
                adjusted_fine_amount REAL,
                decided_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (notice_id) REFERENCES violation_notices(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_appeals_notice ON violation_appeals(notice_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_appeals_tenant ON violation_appeals(tenant_id)"
        )

        # Seed initial data if tables are empty
        cursor.execute("SELECT COUNT(*) FROM community_incidents")
        if cursor.fetchone()[0] == 0:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            for inc in DEFAULT_SEEDED_INCIDENTS:
                cursor.execute(
                    """
                    INSERT INTO community_incidents (
                        id, incident_number, incident_type, severity, status,
                        unit_id, tenant_id, reported_by, reporter_name,
                        incident_date, location, description, action_taken,
                        resolution_notes, resolved_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inc["id"],
                        inc["incident_number"],
                        inc["incident_type"],
                        inc["severity"],
                        inc["status"],
                        inc["unit_id"],
                        inc["tenant_id"],
                        inc["reported_by"],
                        inc["reporter_name"],
                        inc["incident_date"],
                        inc["location"],
                        inc["description"],
                        inc["action_taken"],
                        inc["resolution_notes"],
                        inc["resolved_at"],
                        now,
                        now,
                    ),
                )

        cursor.execute("SELECT COUNT(*) FROM violation_notices")
        if cursor.fetchone()[0] == 0:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            for v in DEFAULT_SEEDED_NOTICES:
                cursor.execute(
                    """
                    INSERT INTO violation_notices (
                        id, notice_number, incident_id, tenant_id, unit_id,
                        violation_type, notice_type, status, issued_at,
                        cure_deadline, fine_amount, fine_charged_to_ledger,
                        remedy_instructions, notes, cured_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        v["id"],
                        v["notice_number"],
                        v["incident_id"],
                        v["tenant_id"],
                        v["unit_id"],
                        v["violation_type"],
                        v["notice_type"],
                        v["status"],
                        v["issued_at"],
                        v["cure_deadline"],
                        v["fine_amount"],
                        v["fine_charged_to_ledger"],
                        v["remedy_instructions"],
                        v["notes"],
                        v["cured_at"],
                        now,
                        now,
                    ),
                )

        cursor.execute("SELECT COUNT(*) FROM violation_appeals")
        if cursor.fetchone()[0] == 0:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            for a in DEFAULT_SEEDED_APPEALS:
                cursor.execute(
                    """
                    INSERT INTO violation_appeals (
                        id, appeal_number, notice_id, tenant_id, unit_id,
                        status, reason, submitted_at, reviewed_by,
                        decision_notes, adjusted_fine_amount, decided_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        a["id"],
                        a["appeal_number"],
                        a["notice_id"],
                        a["tenant_id"],
                        a["unit_id"],
                        a["status"],
                        a["reason"],
                        a["submitted_at"],
                        a["reviewed_by"],
                        a["decision_notes"],
                        a["adjusted_fine_amount"],
                        a["decided_at"],
                        now,
                        now,
                    ),
                )

        conn.commit()
    finally:
        if owns_conn:
            conn.close()


def generate_incident_number() -> str:
    """Generate human-readable INC-YYYY-NNNN code."""
    year = datetime.datetime.now(datetime.UTC).year
    suffix = secrets.randbelow(9000) + 1000
    return f"INC-{year}-{suffix}"


def generate_notice_number() -> str:
    """Generate human-readable VN-YYYY-NNNN code."""
    year = datetime.datetime.now(datetime.UTC).year
    suffix = secrets.randbelow(9000) + 1000
    return f"VN-{year}-{suffix}"


def generate_appeal_number() -> str:
    """Generate human-readable APL-YYYY-NNNN code."""
    year = datetime.datetime.now(datetime.UTC).year
    suffix = secrets.randbelow(9000) + 1000
    return f"APL-{year}-{suffix}"


def create_incident(  # noqa: PLR0913, PLR0917
    incident_type: str,
    description: str,
    severity: str = IncidentSeverity.LOW.value,
    status: str = IncidentStatus.REPORTED.value,
    unit_id: str | None = None,
    tenant_id: str | None = None,
    reported_by: str = "resident",
    reporter_name: str | None = None,
    location: str | None = None,
    incident_date: str | None = None,
    action_taken: str | None = None,
    resolution_notes: str | None = None,
) -> dict[str, Any]:
    """Create a new incident report."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        inc_id = f"inc_{secrets.token_hex(6)}"
        incident_number = generate_incident_number()
        now = datetime.datetime.now(datetime.UTC).isoformat()
        date_str = incident_date or now

        cursor.execute(
            """
            INSERT INTO community_incidents (
                id, incident_number, incident_type, severity, status,
                unit_id, tenant_id, reported_by, reporter_name,
                incident_date, location, description, action_taken,
                resolution_notes, resolved_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inc_id,
                incident_number,
                incident_type,
                severity,
                status,
                unit_id,
                tenant_id,
                reported_by,
                reporter_name,
                date_str,
                location,
                description,
                action_taken,
                resolution_notes,
                now if status == IncidentStatus.RESOLVED.value else None,
                now,
                now,
            ),
        )
        conn.commit()
        return get_incident(inc_id)  # type: ignore[return-value]
    finally:
        conn.close()


def get_incident(incident_id: str) -> dict[str, Any] | None:
    """Retrieve an incident by ID or incident_number."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, incident_number, incident_type, severity, status,
                   unit_id, tenant_id, reported_by, reporter_name,
                   incident_date, location, description, action_taken,
                   resolution_notes, resolved_at, created_at, updated_at
            FROM community_incidents
            WHERE id = ? OR incident_number = ?
            """,
            (incident_id, incident_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "incident_number": row[1],
            "incident_type": row[2],
            "severity": row[3],
            "status": row[4],
            "unit_id": row[5],
            "tenant_id": row[6],
            "reported_by": row[7],
            "reporter_name": row[8],
            "incident_date": row[9],
            "location": row[10],
            "description": row[11],
            "action_taken": row[12],
            "resolution_notes": row[13],
            "resolved_at": row[14],
            "created_at": row[15],
            "updated_at": row[16],
        }
    finally:
        conn.close()


def list_incidents(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    incident_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List community incidents with optional filtering and search."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        query = (
            "SELECT id, incident_number, incident_type, severity, status, "
            "unit_id, tenant_id, reported_by, reporter_name, incident_date, "
            "location, description, action_taken, resolution_notes, resolved_at, "
            "created_at, updated_at FROM community_incidents WHERE 1=1"
        )
        params: list[Any] = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if incident_type:
            query += " AND incident_type = ?"
            params.append(incident_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if status:
            query += " AND status = ?"
            params.append(status)
        if search:
            query += " AND (description LIKE ? OR location LIKE ? OR incident_number LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])

        count_query = f"SELECT COUNT(*) FROM ({query})"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        items = [
            {
                "id": r[0],
                "incident_number": r[1],
                "incident_type": r[2],
                "severity": r[3],
                "status": r[4],
                "unit_id": r[5],
                "tenant_id": r[6],
                "reported_by": r[7],
                "reporter_name": r[8],
                "incident_date": r[9],
                "location": r[10],
                "description": r[11],
                "action_taken": r[12],
                "resolution_notes": r[13],
                "resolved_at": r[14],
                "created_at": r[15],
                "updated_at": r[16],
            }
            for r in rows
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


def update_incident(  # noqa: PLR0912, PLR0913, PLR0917
    incident_id: str,
    incident_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    location: str | None = None,
    description: str | None = None,
    action_taken: str | None = None,
    resolution_notes: str | None = None,
) -> dict[str, Any] | None:
    """Update incident record."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        existing = get_incident(incident_id)
        if not existing:
            return None

        fields: list[str] = []
        params: list[Any] = []
        now = datetime.datetime.now(datetime.UTC).isoformat()

        if incident_type is not None:
            fields.append("incident_type = ?")
            params.append(incident_type)
        if severity is not None:
            fields.append("severity = ?")
            params.append(severity)
        if status is not None:
            fields.append("status = ?")
            params.append(status)
            if status == IncidentStatus.RESOLVED.value and not existing.get("resolved_at"):
                fields.append("resolved_at = ?")
                params.append(now)
        if location is not None:
            fields.append("location = ?")
            params.append(location)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if action_taken is not None:
            fields.append("action_taken = ?")
            params.append(action_taken)
        if resolution_notes is not None:
            fields.append("resolution_notes = ?")
            params.append(resolution_notes)

        if not fields:
            return existing

        fields.append("updated_at = ?")
        params.append(now)
        params.append(existing["id"])

        cursor.execute(
            f"UPDATE community_incidents SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        conn.commit()
        return get_incident(existing["id"])
    finally:
        conn.close()


def delete_incident(incident_id: str) -> bool:
    """Delete an incident record."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        existing = get_incident(incident_id)
        if not existing:
            return False
        cursor.execute("DELETE FROM community_incidents WHERE id = ?", (existing["id"],))
        conn.commit()
        return True
    finally:
        conn.close()


def create_violation_notice(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    violation_type: str,
    remedy_instructions: str,
    incident_id: str | None = None,
    notice_type: str = NoticeType.COURTESY_WARNING.value,
    status: str = ViolationStatus.ISSUED.value,
    cure_days: int = DEFAULT_CURE_DAYS,
    fine_amount: float = 0.0,
    charge_to_ledger: bool = False,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a new formal violation notice."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        notice_id = f"viol_{secrets.token_hex(6)}"
        notice_number = generate_notice_number()
        now_dt = datetime.datetime.now(datetime.UTC)
        now = now_dt.isoformat()
        cure_deadline = (now_dt + datetime.timedelta(days=cure_days)).isoformat()

        cursor.execute(
            """
            INSERT INTO violation_notices (
                id, notice_number, incident_id, tenant_id, unit_id,
                violation_type, notice_type, status, issued_at,
                cure_deadline, fine_amount, fine_charged_to_ledger,
                remedy_instructions, notes, cured_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notice_id,
                notice_number,
                incident_id,
                tenant_id,
                unit_id,
                violation_type,
                notice_type,
                status,
                now,
                cure_deadline,
                float(fine_amount),
                1 if (charge_to_ledger and fine_amount > 0) else 0,
                remedy_instructions,
                notes,
                None,
                now,
                now,
            ),
        )

        # If linked to an incident, mark incident status as NOTICE_ISSUED
        if incident_id:
            cursor.execute(
                "UPDATE community_incidents SET status = ?, updated_at = ? WHERE id = ?",
                (IncidentStatus.NOTICE_ISSUED.value, now, incident_id),
            )

        conn.commit()
        return get_violation_notice(notice_id)  # type: ignore[return-value]
    finally:
        conn.close()


def get_violation_notice(notice_id: str) -> dict[str, Any] | None:
    """Retrieve violation notice by ID or notice_number."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, notice_number, incident_id, tenant_id, unit_id,
                   violation_type, notice_type, status, issued_at,
                   cure_deadline, fine_amount, fine_charged_to_ledger,
                   remedy_instructions, notes, cured_at, created_at, updated_at
            FROM violation_notices
            WHERE id = ? OR notice_number = ?
            """,
            (notice_id, notice_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "notice_number": row[1],
            "incident_id": row[2],
            "tenant_id": row[3],
            "unit_id": row[4],
            "violation_type": row[5],
            "notice_type": row[6],
            "status": row[7],
            "issued_at": row[8],
            "cure_deadline": row[9],
            "fine_amount": float(row[10]),
            "fine_charged_to_ledger": bool(row[11]),
            "remedy_instructions": row[12],
            "notes": row[13],
            "cured_at": row[14],
            "created_at": row[15],
            "updated_at": row[16],
        }
    finally:
        conn.close()


def list_violation_notices(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    violation_type: str | None = None,
    notice_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List violation notices with filters and pagination."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        query = (
            "SELECT id, notice_number, incident_id, tenant_id, unit_id, "
            "violation_type, notice_type, status, issued_at, cure_deadline, "
            "fine_amount, fine_charged_to_ledger, remedy_instructions, notes, "
            "cured_at, created_at, updated_at FROM violation_notices WHERE 1=1"
        )
        params: list[Any] = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if violation_type:
            query += " AND violation_type = ?"
            params.append(violation_type)
        if notice_type:
            query += " AND notice_type = ?"
            params.append(notice_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        if search:
            query += " AND (remedy_instructions LIKE ? OR notes LIKE ? OR notice_number LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])

        count_query = f"SELECT COUNT(*) FROM ({query})"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        items = [
            {
                "id": r[0],
                "notice_number": r[1],
                "incident_id": r[2],
                "tenant_id": r[3],
                "unit_id": r[4],
                "violation_type": r[5],
                "notice_type": r[6],
                "status": r[7],
                "issued_at": r[8],
                "cure_deadline": r[9],
                "fine_amount": float(r[10]),
                "fine_charged_to_ledger": bool(r[11]),
                "remedy_instructions": r[12],
                "notes": r[13],
                "cured_at": r[14],
                "created_at": r[15],
                "updated_at": r[16],
            }
            for r in rows
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


def update_violation_notice(  # noqa: PLR0912, PLR0913, PLR0917
    notice_id: str,
    status: str | None = None,
    cure_deadline: str | None = None,
    fine_amount: float | None = None,
    fine_charged_to_ledger: bool | None = None,
    remedy_instructions: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update violation notice."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        existing = get_violation_notice(notice_id)
        if not existing:
            return None

        fields: list[str] = []
        params: list[Any] = []
        now = datetime.datetime.now(datetime.UTC).isoformat()

        if status is not None:
            fields.append("status = ?")
            params.append(status)
            if status == ViolationStatus.CURED.value and not existing.get("cured_at"):
                fields.append("cured_at = ?")
                params.append(now)
        if cure_deadline is not None:
            fields.append("cure_deadline = ?")
            params.append(cure_deadline)
        if fine_amount is not None:
            fields.append("fine_amount = ?")
            params.append(float(fine_amount))
        if fine_charged_to_ledger is not None:
            fields.append("fine_charged_to_ledger = ?")
            params.append(1 if fine_charged_to_ledger else 0)
        if remedy_instructions is not None:
            fields.append("remedy_instructions = ?")
            params.append(remedy_instructions)
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)

        if not fields:
            return existing

        fields.append("updated_at = ?")
        params.append(now)
        params.append(existing["id"])

        cursor.execute(
            f"UPDATE violation_notices SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        conn.commit()
        return get_violation_notice(existing["id"])
    finally:
        conn.close()


def delete_violation_notice(notice_id: str) -> bool:
    """Delete a violation notice."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        existing = get_violation_notice(notice_id)
        if not existing:
            return False
        cursor.execute("DELETE FROM violation_notices WHERE id = ?", (existing["id"],))
        conn.commit()
        return True
    finally:
        conn.close()


def create_violation_appeal(
    notice_id: str,
    tenant_id: str,
    unit_id: str,
    reason: str,
) -> dict[str, Any]:
    """Submit an appeal against a violation notice."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        appeal_id = f"appeal_{secrets.token_hex(6)}"
        appeal_number = generate_appeal_number()
        now = datetime.datetime.now(datetime.UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO violation_appeals (
                id, appeal_number, notice_id, tenant_id, unit_id,
                status, reason, submitted_at, reviewed_by,
                decision_notes, adjusted_fine_amount, decided_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                appeal_id,
                appeal_number,
                notice_id,
                tenant_id,
                unit_id,
                AppealStatus.SUBMITTED.value,
                reason,
                now,
                None,
                None,
                None,
                None,
                now,
                now,
            ),
        )

        # Mark notice status as APPEALED
        cursor.execute(
            "UPDATE violation_notices SET status = ?, updated_at = ? WHERE id = ?",
            (ViolationStatus.APPEALED.value, now, notice_id),
        )

        conn.commit()
        return get_violation_appeal(appeal_id)  # type: ignore[return-value]
    finally:
        conn.close()


def get_violation_appeal(appeal_id: str) -> dict[str, Any] | None:
    """Retrieve an appeal by ID or appeal_number."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, appeal_number, notice_id, tenant_id, unit_id,
                   status, reason, submitted_at, reviewed_by,
                   decision_notes, adjusted_fine_amount, decided_at,
                   created_at, updated_at
            FROM violation_appeals
            WHERE id = ? OR appeal_number = ?
            """,
            (appeal_id, appeal_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "appeal_number": row[1],
            "notice_id": row[2],
            "tenant_id": row[3],
            "unit_id": row[4],
            "status": row[5],
            "reason": row[6],
            "submitted_at": row[7],
            "reviewed_by": row[8],
            "decision_notes": row[9],
            "adjusted_fine_amount": float(row[10]) if row[10] is not None else None,
            "decided_at": row[11],
            "created_at": row[12],
            "updated_at": row[13],
        }
    finally:
        conn.close()


def list_violation_appeals(  # noqa: PLR0913, PLR0917
    notice_id: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List appeals with filters."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        query = (
            "SELECT id, appeal_number, notice_id, tenant_id, unit_id, "
            "status, reason, submitted_at, reviewed_by, decision_notes, "
            "adjusted_fine_amount, decided_at, created_at, updated_at "
            "FROM violation_appeals WHERE 1=1"
        )
        params: list[Any] = []

        if notice_id:
            query += " AND notice_id = ?"
            params.append(notice_id)
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        count_query = f"SELECT COUNT(*) FROM ({query})"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        items = [
            {
                "id": r[0],
                "appeal_number": r[1],
                "notice_id": r[2],
                "tenant_id": r[3],
                "unit_id": r[4],
                "status": r[5],
                "reason": r[6],
                "submitted_at": r[7],
                "reviewed_by": r[8],
                "decision_notes": r[9],
                "adjusted_fine_amount": float(r[10]) if r[10] is not None else None,
                "decided_at": r[11],
                "created_at": r[12],
                "updated_at": r[13],
            }
            for r in rows
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


def update_violation_appeal(  # noqa: PLR0912, PLR0913
    appeal_id: str,
    status: str | None = None,
    reviewed_by: str | None = None,
    decision_notes: str | None = None,
    adjusted_fine_amount: float | None = None,
) -> dict[str, Any] | None:
    """Review or decide on an appeal."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        existing = get_violation_appeal(appeal_id)
        if not existing:
            return None

        fields: list[str] = []
        params: list[Any] = []
        now = datetime.datetime.now(datetime.UTC).isoformat()

        if status is not None:
            fields.append("status = ?")
            params.append(status)
            if status in (
                AppealStatus.WAIVED.value,
                AppealStatus.UPHELD.value,
                AppealStatus.REDUCED.value,
            ):
                fields.append("decided_at = ?")
                params.append(now)
        if reviewed_by is not None:
            fields.append("reviewed_by = ?")
            params.append(reviewed_by)
        if decision_notes is not None:
            fields.append("decision_notes = ?")
            params.append(decision_notes)
        if adjusted_fine_amount is not None:
            fields.append("adjusted_fine_amount = ?")
            params.append(float(adjusted_fine_amount))

        if not fields:
            return existing

        fields.append("updated_at = ?")
        params.append(now)
        params.append(existing["id"])

        cursor.execute(
            f"UPDATE violation_appeals SET {', '.join(fields)} WHERE id = ?",
            params,
        )

        # Update notice status if decision reached
        if status == AppealStatus.WAIVED.value:
            cursor.execute(
                "UPDATE violation_notices SET status = ?, fine_amount = 0.0, updated_at = ? "
                "WHERE id = ?",
                (ViolationStatus.CLOSED.value, now, existing["notice_id"]),
            )
        elif status == AppealStatus.UPHELD.value:
            cursor.execute(
                "UPDATE violation_notices SET status = ?, updated_at = ? WHERE id = ?",
                (ViolationStatus.ISSUED.value, now, existing["notice_id"]),
            )
        elif status == AppealStatus.REDUCED.value and adjusted_fine_amount is not None:
            cursor.execute(
                "UPDATE violation_notices SET status = ?, fine_amount = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    ViolationStatus.ISSUED.value,
                    float(adjusted_fine_amount),
                    now,
                    existing["notice_id"],
                ),
            )

        conn.commit()
        return get_violation_appeal(existing["id"])
    finally:
        conn.close()


def delete_violation_appeal(appeal_id: str) -> bool:
    """Delete an appeal record."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()
        existing = get_violation_appeal(appeal_id)
        if not existing:
            return False
        cursor.execute("DELETE FROM violation_appeals WHERE id = ?", (existing["id"],))
        conn.commit()
        return True
    finally:
        conn.close()


def get_incident_metrics_summary() -> dict[str, Any]:
    """Aggregate portfolio-wide incident and violation metrics."""
    conn = db_utils.get_db_connection()
    try:
        init_incidents_db(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM community_incidents")
        total_incidents = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM community_incidents "
            "WHERE status IN ('reported', 'under_investigation')"
        )
        active_incidents = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM violation_notices")
        total_violations = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM violation_notices WHERE status IN ('issued', 'escalated')"
        )
        open_violations = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM violation_notices WHERE status = 'cured'"
        )
        cured_violations = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(fine_amount), 0) FROM violation_notices")
        total_fines_assessed = float(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM violation_appeals")
        total_appeals = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM violation_appeals WHERE status IN ('submitted', 'under_review')"
        )
        pending_appeals = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM violation_appeals WHERE status = 'waived'"
        )
        appeals_waived = cursor.fetchone()[0]

        return {
            "total_incidents": total_incidents,
            "active_incidents": active_incidents,
            "total_violations": total_violations,
            "open_violations": open_violations,
            "cured_violations": cured_violations,
            "total_fines_assessed": total_fines_assessed,
            "total_appeals": total_appeals,
            "pending_appeals": pending_appeals,
            "appeals_waived": appeals_waived,
        }
    finally:
        conn.close()
