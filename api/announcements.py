"""Database schema, CRUD operations, announcements, alerts, and concierge engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from enum import StrEnum
from typing import Any

from api import db_utils

# Constants
DEFAULT_ANNOUNCEMENT_EXPIRY_DAYS = 30
MIN_SEEDED_ANNOUNCEMENTS = 2
MIN_SEEDED_CONCIERGE = 1


class AnnouncementCategory(StrEnum):
    GENERAL_NOTICE = "general_notice"
    EMERGENCY_ALERT = "emergency_alert"
    MAINTENANCE_ADVISORY = "maintenance_advisory"
    AMENITY_UPDATE = "amenity_update"
    POLICY_REMINDER = "policy_reminder"
    COMMUNITY_EVENT = "community_event"
    WEATHER_WARNING = "weather_warning"


class AnnouncementPriority(StrEnum):
    INFO = "info"
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL_EMERGENCY = "critical_emergency"


class AnnouncementScope(StrEnum):
    PORTFOLIO_WIDE = "portfolio_wide"
    BUILDING = "building"
    FLOOR = "floor"
    UNIT_SPECIFIC = "unit_specific"


class AnnouncementStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ConciergeType(StrEnum):
    DRY_CLEANING = "dry_cleaning"
    PACKAGE_HOLD = "package_hold"
    SERVICE_ENTRY_PERMISSION = "service_entry_permission"
    GUEST_ESCORT = "guest_escort"
    KEY_CHECKOUT = "key_checkout"
    SPECIAL_ASSISTANCE = "special_assistance"
    MOVE_IN_COORDINATION = "move_in_coordination"
    OTHER = "other"


class ConciergeStatus(StrEnum):
    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


def _generate_announcement_number(is_emergency: bool = False) -> str:
    """Generate human-readable announcement tracking number."""
    prefix = "EMG" if is_emergency else "ANN"
    year = datetime.datetime.now(datetime.UTC).year
    suffix = secrets.token_hex(2).upper()
    return f"{prefix}-{year}-{suffix}"


def _generate_concierge_number() -> str:
    """Generate human-readable concierge tracking number."""
    year = datetime.datetime.now(datetime.UTC).year
    suffix = secrets.token_hex(2).upper()
    return f"CON-{year}-{suffix}"


def init_announcements_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize community announcements, acknowledgments, and concierge tables."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        cursor = conn.cursor()

        # 1. Community Announcements table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS community_announcements (
                id TEXT PRIMARY KEY,
                announcement_number TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'portfolio_wide',
                target_building TEXT,
                target_floor TEXT,
                target_unit_id TEXT REFERENCES units(id) ON DELETE SET NULL,
                author_name TEXT NOT NULL DEFAULT 'Property Management',
                is_pinned INTEGER NOT NULL DEFAULT 0,
                require_acknowledgment INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'published',
                published_at TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_announcements_status ON community_announcements(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ann_cat ON community_announcements(category)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ann_prio ON community_announcements(priority)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ann_tunit ON community_announcements(target_unit_id)"
        )

        # 2. Announcement Acknowledgments table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS announcement_acknowledgments (
                id TEXT PRIMARY KEY,
                announcement_id TEXT NOT NULL REFERENCES
                    community_announcements(id) ON DELETE CASCADE,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                unit_id TEXT REFERENCES units(id) ON DELETE SET NULL,
                channel TEXT NOT NULL DEFAULT 'chat_session',
                acknowledged_at TEXT NOT NULL,
                notes TEXT,
                UNIQUE(announcement_id, tenant_id)
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ann_ack_aid ON "
            "announcement_acknowledgments(announcement_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ann_ack_tid ON announcement_acknowledgments(tenant_id)"
        )

        # 3. Resident Concierge Requests table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS concierge_requests (
                id TEXT PRIMARY KEY,
                request_number TEXT UNIQUE NOT NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                request_type TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'normal',
                instructions TEXT NOT NULL,
                preferred_date TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',
                assigned_staff TEXT,
                fulfillment_notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_concierge_tenant_id ON concierge_requests(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_concierge_unit_id ON concierge_requests(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_concierge_status ON concierge_requests(status)"
        )

        conn.commit()
        _seed_default_announcements(conn)
    finally:
        if should_close:
            conn.close()


def _seed_default_announcements(conn: sqlite3.Connection) -> None:
    """Seed sample community announcements and concierge request if empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM community_announcements")
    row = cursor.fetchone()
    ann_count = row[0] if row else 0

    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
    future_iso = (
        datetime.datetime.now(datetime.UTC)
        + datetime.timedelta(days=DEFAULT_ANNOUNCEMENT_EXPIRY_DAYS)
    ).isoformat()

    if ann_count < MIN_SEEDED_ANNOUNCEMENTS:
        # 1. Maintenance advisory
        cursor.execute(
            """
            INSERT OR IGNORE INTO community_announcements (
                id, announcement_number, title, content, category, priority, scope,
                target_building, target_floor, target_unit_id, author_name, is_pinned,
                require_acknowledgment, status, published_at, expires_at, created_at, updated_at
            ) VALUES (
                'ann_seed_01', 'ANN-2026-101', 'Scheduled Penthouse Elevator Modernization',
                ?, 'maintenance_advisory', 'normal', 'building', 'North Tower', 'Penthouse',
                'unit_PH1', 'Property Operations', 1, 0, 'published', ?, ?, ?, ?
            )
            """,
            (
                "North tower penthouse elevator will undergo routine hydraulic maintenance "
                "on Wednesday from 10 AM to 2 PM.",
                now_iso,
                future_iso,
                now_iso,
                now_iso,
            ),
        )

        # 2. Urgent freeze advisory
        cursor.execute(
            """
            INSERT OR IGNORE INTO community_announcements (
                id, announcement_number, title, content, category, priority, scope,
                target_building, target_floor, target_unit_id, author_name, is_pinned,
                require_acknowledgment, status, published_at, expires_at, created_at, updated_at
            ) VALUES (
                'ann_seed_02', 'EMG-2026-005', 'Severe Cold Weather & Pipe Freeze Advisory',
                ?, 'emergency_alert', 'urgent', 'portfolio_wide', NULL, NULL,
                NULL, 'Lead Property Manager', 1, 1, 'published', ?, ?, ?, ?
            )
            """,
            (
                "Sub-zero temperatures expected this weekend. Please maintain thermostat at "
                "68F or above and open under-sink cabinets.",
                now_iso,
                future_iso,
                now_iso,
                now_iso,
            ),
        )

        # 3. Seed acknowledgment for Elena Rostova on EMG-2026-005
        cursor.execute(
            """
            INSERT OR IGNORE INTO announcement_acknowledgments (
                id, announcement_id, tenant_id, unit_id, channel, acknowledged_at, notes
            ) VALUES (
                'ack_seed_01', 'ann_seed_02', 'tenant_3', 'unit_PH1',
                'chat_session', ?, 'Resident confirmed heating protocol followed'
            )
            """,
            (now_iso,),
        )

    # Seed concierge request for Elena Rostova if empty
    cursor.execute("SELECT COUNT(*) FROM concierge_requests")
    row_c = cursor.fetchone()
    con_count = row_c[0] if row_c else 0

    if con_count < MIN_SEEDED_CONCIERGE:
        cursor.execute(
            """
            INSERT OR IGNORE INTO concierge_requests (
                id, request_number, tenant_id, unit_id, request_type, priority,
                instructions, preferred_date, status, assigned_staff,
                fulfillment_notes, created_at, updated_at
            ) VALUES (
                'con_seed_01', 'CON-2026-042', 'tenant_3', 'unit_PH1', 'dry_cleaning',
                'normal', 'Eco Cleaners garment bag left with front desk for Monday pickup',
                ?, 'in_progress', 'Concierge Marcus',
                'Bag tagged and logged with valet dispatch', ?, ?
            )
            """,
            (now_iso[:10], now_iso, now_iso),
        )

    conn.commit()


# ==============================================================================
# Announcement Operations
# ==============================================================================


def create_announcement(  # noqa: PLR0913, PLR0917
    title: str,
    content: str,
    category: str = AnnouncementCategory.GENERAL_NOTICE,
    priority: str = AnnouncementPriority.NORMAL,
    scope: str = AnnouncementScope.PORTFOLIO_WIDE,
    target_building: str | None = None,
    target_floor: str | None = None,
    target_unit_id: str | None = None,
    author_name: str = "Property Management",
    is_pinned: bool = False,
    require_acknowledgment: bool = False,
    expires_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Publish a new community announcement or emergency building alert."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()

        ann_id = f"ann_{secrets.token_hex(8)}"
        is_emergency = priority in (
            AnnouncementPriority.URGENT,
            AnnouncementPriority.CRITICAL_EMERGENCY,
        ) or category == AnnouncementCategory.EMERGENCY_ALERT
        ann_number = _generate_announcement_number(is_emergency)
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO community_announcements (
                id, announcement_number, title, content, category, priority, scope,
                target_building, target_floor, target_unit_id, author_name, is_pinned,
                require_acknowledgment, status, published_at, expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?, ?, ?)
            """,
            (
                ann_id,
                ann_number,
                title.strip(),
                content.strip(),
                str(category),
                str(priority),
                str(scope),
                target_building.strip() if target_building else None,
                target_floor.strip() if target_floor else None,
                target_unit_id.strip() if target_unit_id else None,
                author_name.strip() if author_name else "Property Management",
                1 if is_pinned else 0,
                1 if require_acknowledgment else 0,
                now_iso,
                expires_at,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()



        return get_announcement(ann_id, conn=conn) or {}
    finally:
        if should_close:
            conn.close()


def get_announcement(
    announcement_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve an announcement by its ID or tracking number."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, announcement_number, title, content, category, priority, scope,
                   target_building, target_floor, target_unit_id, author_name, is_pinned,
                   require_acknowledgment, status, published_at, expires_at, created_at, updated_at
            FROM community_announcements
            WHERE id = ? OR announcement_number = ?
            """,
            (announcement_id, announcement_id),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "announcement_number": row[1],
            "title": row[2],
            "content": row[3],
            "category": row[4],
            "priority": row[5],
            "scope": row[6],
            "target_building": row[7],
            "target_floor": row[8],
            "target_unit_id": row[9],
            "author_name": row[10],
            "is_pinned": bool(row[11]),
            "require_acknowledgment": bool(row[12]),
            "status": row[13],
            "published_at": row[14],
            "expires_at": row[15],
            "created_at": row[16],
            "updated_at": row[17],
        }
    finally:
        if should_close:
            conn.close()


def update_announcement(  # noqa: PLR0912, PLR0913, PLR0917
    announcement_id: str,
    title: str | None = None,
    content: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    scope: str | None = None,
    status: str | None = None,
    is_pinned: bool | None = None,
    expires_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update announcement fields."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        existing = get_announcement(announcement_id, conn=conn)
        if not existing:
            return None

        updates: list[str] = []
        params: list[Any] = []

        if title is not None:
            updates.append("title = ?")
            params.append(title.strip())
        if content is not None:
            updates.append("content = ?")
            params.append(content.strip())
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if scope is not None:
            updates.append("scope = ?")
            params.append(scope)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if is_pinned is not None:
            updates.append("is_pinned = ?")
            params.append(1 if is_pinned else 0)
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(expires_at)

        if not updates:
            return existing

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        updates.append("updated_at = ?")
        params.append(now_iso)

        params.append(existing["id"])
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE community_announcements SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

        return get_announcement(existing["id"], conn=conn)
    finally:
        if should_close:
            conn.close()


def delete_announcement(
    announcement_id: str, conn: sqlite3.Connection | None = None
) -> bool:
    """Delete an announcement record and its acknowledgments."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM community_announcements WHERE id = ? OR announcement_number = ?",
            (announcement_id, announcement_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if should_close:
            conn.close()


def list_announcements(  # noqa: PLR0913, PLR0917
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    scope: str | None = None,
    target_unit_id: str | None = None,
    pinned_first: bool = True,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """List announcements matching optional filters."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()

        where_clauses: list[str] = []
        params: list[Any] = []

        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if category:
            where_clauses.append("category = ?")
            params.append(category)
        if priority:
            where_clauses.append("priority = ?")
            params.append(priority)
        if scope:
            where_clauses.append("scope = ?")
            params.append(scope)
        if target_unit_id:
            where_clauses.append(
                "(target_unit_id = ? OR scope = 'portfolio_wide')"
            )
            params.append(target_unit_id)

        where_sql = (
            f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        )

        cursor.execute(
            f"SELECT COUNT(*) FROM community_announcements {where_sql}", params
        )
        row = cursor.fetchone()
        total = row[0] if row else 0

        order_by = (
            "ORDER BY is_pinned DESC, published_at DESC"
            if pinned_first
            else "ORDER BY published_at DESC"
        )
        query = f"""
            SELECT id, announcement_number, title, content, category, priority, scope,
                   target_building, target_floor, target_unit_id, author_name, is_pinned,
                   require_acknowledgment, status, published_at, expires_at, created_at, updated_at
            FROM community_announcements
            {where_sql}
            {order_by}
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, [*params, limit, offset])
        rows = cursor.fetchall()

        items = [
            {
                "id": r[0],
                "announcement_number": r[1],
                "title": r[2],
                "content": r[3],
                "category": r[4],
                "priority": r[5],
                "scope": r[6],
                "target_building": r[7],
                "target_floor": r[8],
                "target_unit_id": r[9],
                "author_name": r[10],
                "is_pinned": bool(r[11]),
                "require_acknowledgment": bool(r[12]),
                "status": r[13],
                "published_at": r[14],
                "expires_at": r[15],
                "created_at": r[16],
                "updated_at": r[17],
            }
            for r in rows
        ]

        return {"total": total, "items": items, "limit": limit, "offset": offset}
    finally:
        if should_close:
            conn.close()


def list_tenant_announcements(
    tenant_id: str,
    unit_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Retrieve all published announcements applicable to a resident/unit."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()

        if unit_id:
            cursor.execute(
                """
                SELECT id, announcement_number, title, content, category, priority, scope,
                       target_building, target_floor, target_unit_id, author_name, is_pinned,
                       require_acknowledgment, status, published_at, expires_at,
                       created_at, updated_at
                FROM community_announcements
                WHERE status = 'published' AND (scope = 'portfolio_wide' OR target_unit_id = ?)
                ORDER BY is_pinned DESC, published_at DESC
                """,
                (unit_id,),
            )
        else:
            cursor.execute(
                """
                SELECT id, announcement_number, title, content, category, priority, scope,
                       target_building, target_floor, target_unit_id, author_name, is_pinned,
                       require_acknowledgment, status, published_at, expires_at,
                       created_at, updated_at
                FROM community_announcements
                WHERE status = 'published'
                ORDER BY is_pinned DESC, published_at DESC
                """
            )

        rows = cursor.fetchall()
        items = []
        for r in rows:
            ann_id = r[0]
            # Check if this resident acknowledged
            cursor.execute(
                (
                "SELECT acknowledged_at FROM announcement_acknowledgments "
                "WHERE announcement_id = ? AND tenant_id = ?"
            ),
                (ann_id, tenant_id),
            )
            ack_row = cursor.fetchone()
            items.append(
                {
                    "id": r[0],
                    "announcement_number": r[1],
                    "title": r[2],
                    "content": r[3],
                    "category": r[4],
                    "priority": r[5],
                    "scope": r[6],
                    "target_building": r[7],
                    "target_floor": r[8],
                    "target_unit_id": r[9],
                    "author_name": r[10],
                    "is_pinned": bool(r[11]),
                    "require_acknowledgment": bool(r[12]),
                    "status": r[13],
                    "published_at": r[14],
                    "expires_at": r[15],
                    "created_at": r[16],
                    "updated_at": r[17],
                    "is_acknowledged": bool(ack_row),
                    "acknowledged_at": ack_row[0] if ack_row else None,
                }
            )

        return {"total": len(items), "items": items}
    finally:
        if should_close:
            conn.close()


def acknowledge_announcement(  # noqa: PLR0913, PLR0917
    announcement_id: str,
    tenant_id: str,
    unit_id: str | None = None,
    channel: str = "chat_session",
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Record a resident's acknowledgment of a community announcement or alert."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        ann = get_announcement(announcement_id, conn=conn)
        if not ann:
            raise ValueError(f"Announcement '{announcement_id}' not found.")

        cursor = conn.cursor()
        ack_id = f"ack_{secrets.token_hex(8)}"
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()

        cursor.execute(
            """
            INSERT OR REPLACE INTO announcement_acknowledgments (
                id, announcement_id, tenant_id, unit_id, channel, acknowledged_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ack_id,
                ann["id"],
                tenant_id,
                unit_id,
                channel,
                now_iso,
                notes.strip() if notes else None,
            ),
        )
        conn.commit()



        return {
            "id": ack_id,
            "announcement_id": ann["id"],
            "announcement_number": ann["announcement_number"],
            "tenant_id": tenant_id,
            "unit_id": unit_id,
            "channel": channel,
            "acknowledged_at": now_iso,
            "notes": notes,
        }
    finally:
        if should_close:
            conn.close()


def get_announcement_acknowledgments(
    announcement_id: str, conn: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    """List all acknowledgments for an announcement."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, announcement_id, tenant_id, unit_id, channel, acknowledged_at, notes
            FROM announcement_acknowledgments
            WHERE announcement_id = ?
            ORDER BY acknowledged_at DESC
            """,
            (announcement_id,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "announcement_id": r[1],
                "tenant_id": r[2],
                "unit_id": r[3],
                "channel": r[4],
                "acknowledged_at": r[5],
                "notes": r[6],
            }
            for r in rows
        ]
    finally:
        if should_close:
            conn.close()


def has_tenant_acknowledged(
    announcement_id: str, tenant_id: str, conn: sqlite3.Connection | None = None
) -> bool:
    """Check whether a specific resident has acknowledged an announcement."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            (
            "SELECT 1 FROM announcement_acknowledgments WHERE announcement_id = ? AND tenant_id = ?"
        ),
            (announcement_id, tenant_id),
        )
        return cursor.fetchone() is not None
    finally:
        if should_close:
            conn.close()


# ==============================================================================
# Concierge Operations
# ==============================================================================


def create_concierge_request(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    unit_id: str,
    request_type: str = ConciergeType.OTHER,
    priority: str = AnnouncementPriority.NORMAL,
    instructions: str = "",
    preferred_date: str | None = None,
    assigned_staff: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Submit a new resident concierge service request."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()

        req_id = f"con_{secrets.token_hex(8)}"
        req_number = _generate_concierge_number()
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO concierge_requests (
                id, request_number, tenant_id, unit_id, request_type, priority,
                instructions, preferred_date, status, assigned_staff,
                fulfillment_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, NULL, ?, ?)
            """,
            (
                req_id,
                req_number,
                tenant_id.strip(),
                unit_id.strip(),
                str(request_type),
                str(priority),
                instructions.strip(),
                preferred_date,
                assigned_staff.strip() if assigned_staff else None,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()



        return get_concierge_request(req_id, conn=conn) or {}
    finally:
        if should_close:
            conn.close()


def get_concierge_request(
    request_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve a concierge request by its ID or tracking number."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, request_number, tenant_id, unit_id, request_type, priority,
                   instructions, preferred_date, status, assigned_staff,
                   fulfillment_notes, created_at, updated_at
            FROM concierge_requests
            WHERE id = ? OR request_number = ?
            """,
            (request_id, request_id),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "request_number": row[1],
            "tenant_id": row[2],
            "unit_id": row[3],
            "request_type": row[4],
            "priority": row[5],
            "instructions": row[6],
            "preferred_date": row[7],
            "status": row[8],
            "assigned_staff": row[9],
            "fulfillment_notes": row[10],
            "created_at": row[11],
            "updated_at": row[12],
        }
    finally:
        if should_close:
            conn.close()


def update_concierge_request(  # noqa: PLR0912, PLR0913, PLR0917
    request_id: str,
    status: str | None = None,
    assigned_staff: str | None = None,
    fulfillment_notes: str | None = None,
    instructions: str | None = None,
    priority: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update concierge request status or fulfillment notes."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        existing = get_concierge_request(request_id, conn=conn)
        if not existing:
            return None

        updates: list[str] = []
        params: list[Any] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if assigned_staff is not None:
            updates.append("assigned_staff = ?")
            params.append(assigned_staff.strip() if assigned_staff else None)
        if fulfillment_notes is not None:
            updates.append("fulfillment_notes = ?")
            params.append(fulfillment_notes.strip() if fulfillment_notes else None)
        if instructions is not None:
            updates.append("instructions = ?")
            params.append(instructions.strip())
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)

        if not updates:
            return existing

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        updates.append("updated_at = ?")
        params.append(now_iso)

        params.append(existing["id"])
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE concierge_requests SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()



        return get_concierge_request(existing["id"], conn=conn)
    finally:
        if should_close:
            conn.close()


def delete_concierge_request(
    request_id: str, conn: sqlite3.Connection | None = None
) -> bool:
    """Delete a concierge request."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM concierge_requests WHERE id = ? OR request_number = ?",
            (request_id, request_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if should_close:
            conn.close()


def list_concierge_requests(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    request_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """List concierge requests matching filters."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()

        where_clauses: list[str] = []
        params: list[Any] = []

        if tenant_id:
            where_clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if unit_id:
            where_clauses.append("unit_id = ?")
            params.append(unit_id)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if request_type:
            where_clauses.append("request_type = ?")
            params.append(request_type)

        where_sql = (
            f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        )

        cursor.execute(
            f"SELECT COUNT(*) FROM concierge_requests {where_sql}", params
        )
        row = cursor.fetchone()
        total = row[0] if row else 0

        query = f"""
            SELECT id, request_number, tenant_id, unit_id, request_type, priority,
                   instructions, preferred_date, status, assigned_staff,
                   fulfillment_notes, created_at, updated_at
            FROM concierge_requests
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, [*params, limit, offset])
        rows = cursor.fetchall()

        items = [
            {
                "id": r[0],
                "request_number": r[1],
                "tenant_id": r[2],
                "unit_id": r[3],
                "request_type": r[4],
                "priority": r[5],
                "instructions": r[6],
                "preferred_date": r[7],
                "status": r[8],
                "assigned_staff": r[9],
                "fulfillment_notes": r[10],
                "created_at": r[11],
                "updated_at": r[12],
            }
            for r in rows
        ]

        return {"total": total, "items": items, "limit": limit, "offset": offset}
    finally:
        if should_close:
            conn.close()


def list_tenant_concierge_requests(
    tenant_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """List all concierge requests for a specific tenant."""
    return list_concierge_requests(tenant_id=tenant_id, conn=conn)


# ==============================================================================
# Portfolio Metrics Summary
# ==============================================================================


def get_announcements_metrics_summary(
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Compute aggregate portfolio metrics for announcements, alerts, and concierge."""
    should_close = False
    if conn is None:
        conn = db_utils.get_db_connection()
        should_close = True

    try:
        init_announcements_db(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM community_announcements")
        row = cursor.fetchone()
        total_announcements = row[0] if row else 0

        cursor.execute(
            "SELECT COUNT(*) FROM community_announcements WHERE status = 'published'"
        )
        row = cursor.fetchone()
        published_announcements = row[0] if row else 0

        cursor.execute(
            """
            SELECT COUNT(*) FROM community_announcements
            WHERE status = 'published' AND (
                priority IN ('urgent', 'critical_emergency') OR category = 'emergency_alert'
            )
            """
        )
        row = cursor.fetchone()
        active_emergency_alerts = row[0] if row else 0

        cursor.execute("SELECT COUNT(*) FROM announcement_acknowledgments")
        row = cursor.fetchone()
        total_acknowledgments = row[0] if row else 0

        cursor.execute("SELECT COUNT(*) FROM concierge_requests")
        row = cursor.fetchone()
        total_concierge_requests = row[0] if row else 0

        cursor.execute(
            "SELECT COUNT(*) FROM concierge_requests WHERE status IN ('submitted', 'in_progress')"
        )
        row = cursor.fetchone()
        pending_concierge_requests = row[0] if row else 0

        cursor.execute(
            "SELECT COUNT(*) FROM concierge_requests WHERE status = 'fulfilled'"
        )
        row = cursor.fetchone()
        fulfilled_concierge_requests = row[0] if row else 0

        return {
            "total_announcements": total_announcements,
            "published_announcements": published_announcements,
            "active_emergency_alerts": active_emergency_alerts,
            "total_acknowledgments": total_acknowledgments,
            "total_concierge_requests": total_concierge_requests,
            "pending_concierge_requests": pending_concierge_requests,
            "fulfilled_concierge_requests": fulfilled_concierge_requests,
        }
    finally:
        if should_close:
            conn.close()
