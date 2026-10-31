"""Community Amenity Reservations & Common Area Bookings Engine.

Provides amenity catalog configuration, conflict-free booking reservations,
fee calculations, usage metrics, and webhook dispatching.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from typing import Any

from api import db_utils

VALID_AMENITY_CATEGORIES = {
    "clubhouse",
    "rooftop",
    "bbq_pavilion",
    "guest_suite",
    "fitness_studio",
    "poolside_cabana",
    "conference_room",
    "other",
}
DEFAULT_AMENITY_CATEGORY = "clubhouse"

VALID_RESERVATION_STATUSES = {
    "pending",
    "confirmed",
    "cancelled",
    "completed",
}
DEFAULT_RESERVATION_STATUS = "confirmed"

MAX_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 1000
MAX_RULES_LENGTH = 2000
MAX_NOTES_LENGTH = 2000
MAX_HOUR_OF_DAY = 23
MIN_DURATION_HOURS = 0.5
SECONDS_PER_HOUR = 3600.0

_CREATE_AMENITIES_TABLE = (
    "CREATE TABLE IF NOT EXISTS amenities ("
    "id TEXT PRIMARY KEY, "
    "name TEXT NOT NULL, "
    "category TEXT NOT NULL DEFAULT 'clubhouse', "
    "description TEXT NOT NULL DEFAULT '', "
    "capacity INTEGER NOT NULL DEFAULT 20, "
    "hourly_rate REAL NOT NULL DEFAULT 0.0, "
    "deposit_amount REAL NOT NULL DEFAULT 0.0, "
    "opening_hour INTEGER NOT NULL DEFAULT 8, "
    "closing_hour INTEGER NOT NULL DEFAULT 22, "
    "is_active INTEGER NOT NULL DEFAULT 1, "
    "rules TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_AMENITIES_CATEGORY_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_amenities_category ON amenities(category)"
)

_CREATE_RESERVATIONS_TABLE = (
    "CREATE TABLE IF NOT EXISTS amenity_reservations ("
    "id TEXT PRIMARY KEY, "
    "amenity_id TEXT NOT NULL, "
    "tenant_id TEXT NOT NULL, "
    "unit_id TEXT NOT NULL, "
    "start_time TEXT NOT NULL, "
    "end_time TEXT NOT NULL, "
    "attendees_count INTEGER NOT NULL DEFAULT 1, "
    "status TEXT NOT NULL DEFAULT 'confirmed', "
    "total_fee REAL NOT NULL DEFAULT 0.0, "
    "deposit_paid REAL NOT NULL DEFAULT 0.0, "
    "notes TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "FOREIGN KEY (amenity_id) REFERENCES amenities(id))"
)
_CREATE_RESERVATIONS_AMENITY_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_reservations_amenity ON amenity_reservations(amenity_id)"
)
_CREATE_RESERVATIONS_TENANT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_reservations_tenant ON amenity_reservations(tenant_id)"
)
_CREATE_RESERVATIONS_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_reservations_status ON amenity_reservations(status)"
)
_CREATE_RESERVATIONS_TIMES_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_reservations_times "
    "ON amenity_reservations(start_time, end_time)"
)

DEFAULT_SEEDED_AMENITIES: list[dict[str, Any]] = [
    {
        "id": "amenity_clubhouse",
        "name": "Grand Community Clubhouse",
        "category": "clubhouse",
        "description": "Spacious community lounge with full kitchen and fireplace.",
        "capacity": 50,
        "hourly_rate": 25.0,
        "deposit_amount": 100.0,
        "opening_hour": 9,
        "closing_hour": 23,
        "is_active": 1,
        "rules": "No smoking. Clean up kitchen after use. Quiet hours begin at 10 PM.",
    },
    {
        "id": "amenity_rooftop",
        "name": "Skyline Rooftop Terrace",
        "category": "rooftop",
        "description": "Panoramic outdoor deck with luxury lounge seating and fire pits.",
        "capacity": 30,
        "hourly_rate": 35.0,
        "deposit_amount": 150.0,
        "opening_hour": 10,
        "closing_hour": 22,
        "is_active": 1,
        "rules": "Maximum 30 guests. No glassware allowed outdoors. Fire pits off at 10 PM.",
    },
    {
        "id": "amenity_bbq",
        "name": "Courtyard BBQ Pavilion",
        "category": "bbq_pavilion",
        "description": "Covered grilling arbor featuring stainless steel gas grills.",
        "capacity": 20,
        "hourly_rate": 15.0,
        "deposit_amount": 50.0,
        "opening_hour": 11,
        "closing_hour": 21,
        "is_active": 1,
        "rules": "Turn off gas valves after cooking. Scrape grill grates with wire brush.",
    },
    {
        "id": "amenity_guest_suite",
        "name": "Executive Guest Suite",
        "category": "guest_suite",
        "description": "Fully furnished 1-bedroom hospitality suite with private bath.",
        "capacity": 4,
        "hourly_rate": 20.0,
        "deposit_amount": 100.0,
        "opening_hour": 8,
        "closing_hour": 23,
        "is_active": 1,
        "rules": "Check-in at 2 PM, check-out at 11 AM. No pets permitted in guest suite.",
    },
    {
        "id": "amenity_fitness",
        "name": "Wellness Yoga & Fitness Studio",
        "category": "fitness_studio",
        "description": "Private studio with hardwood floors, mirror wall, and mats.",
        "capacity": 15,
        "hourly_rate": 10.0,
        "deposit_amount": 25.0,
        "opening_hour": 6,
        "closing_hour": 22,
        "is_active": 1,
        "rules": "Athletic footwear only. Wipe down mats and equipment after sessions.",
    },
]

DEFAULT_SEEDED_RESERVATIONS: list[dict[str, Any]] = [
    {
        "id": "res_001_clubhouse",
        "amenity_id": "amenity_clubhouse",
        "tenant_id": "tenant_1",
        "unit_id": "101",
        "start_time": "2026-11-05T18:00:00Z",
        "end_time": "2026-11-05T21:00:00Z",
        "attendees_count": 15,
        "status": "confirmed",
        "total_fee": 75.0,
        "deposit_paid": 100.0,
        "notes": "Sarah Jenkins resident book club gathering",
    },
    {
        "id": "res_002_bbq",
        "amenity_id": "amenity_bbq",
        "tenant_id": "tenant_2",
        "unit_id": "204",
        "start_time": "2026-11-06T12:00:00Z",
        "end_time": "2026-11-06T15:00:00Z",
        "attendees_count": 8,
        "status": "confirmed",
        "total_fee": 45.0,
        "deposit_paid": 50.0,
        "notes": "Marcus Vance family afternoon cookout",
    },
]


def create_amenities_tables() -> None:
    """Create amenities and amenity_reservations tables and indices if they do not exist."""
    with closing(db_utils.get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(_CREATE_AMENITIES_TABLE)
        cursor.execute(_CREATE_AMENITIES_CATEGORY_INDEX)
        cursor.execute(_CREATE_RESERVATIONS_TABLE)
        cursor.execute(_CREATE_RESERVATIONS_AMENITY_INDEX)
        cursor.execute(_CREATE_RESERVATIONS_TENANT_INDEX)
        cursor.execute(_CREATE_RESERVATIONS_STATUS_INDEX)
        cursor.execute(_CREATE_RESERVATIONS_TIMES_INDEX)


def seed_default_amenities_if_empty() -> None:
    """Seed initial demo amenities and reservations if tables are empty."""
    create_amenities_tables()
    with closing(db_utils.get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM amenities")
        row = cursor.fetchone()
        amenity_count = row[0] if row else 0

        if amenity_count == 0:
            now_str = datetime.now(UTC).isoformat()
            for am in DEFAULT_SEEDED_AMENITIES:
                cursor.execute(
                    "INSERT INTO amenities ("
                    "id, name, category, description, capacity, hourly_rate, deposit_amount, "
                    "opening_hour, closing_hour, is_active, rules, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        am["id"],
                        am["name"],
                        am["category"],
                        am["description"],
                        am["capacity"],
                        am["hourly_rate"],
                        am["deposit_amount"],
                        am["opening_hour"],
                        am["closing_hour"],
                        am["is_active"],
                        am["rules"],
                        now_str,
                        now_str,
                    ),
                )

        cursor.execute("SELECT COUNT(*) FROM amenity_reservations")
        res_row = cursor.fetchone()
        res_count = res_row[0] if res_row else 0
        if res_count == 0:
            now_str = datetime.now(UTC).isoformat()
            for res in DEFAULT_SEEDED_RESERVATIONS:
                cursor.execute(
                    "INSERT INTO amenity_reservations ("
                    "id, amenity_id, tenant_id, unit_id, start_time, end_time, attendees_count, "
                    "status, total_fee, deposit_paid, notes, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        res["id"],
                        res["amenity_id"],
                        res["tenant_id"],
                        res["unit_id"],
                        res["start_time"],
                        res["end_time"],
                        res["attendees_count"],
                        res["status"],
                        res["total_fee"],
                        res["deposit_paid"],
                        res["notes"],
                        now_str,
                        now_str,
                    ),
                )


def create_amenity(  # noqa: PLR0913, PLR0917
    amenity_id: str,
    name: str,
    category: str = DEFAULT_AMENITY_CATEGORY,
    description: str = "",
    capacity: int = 20,
    hourly_rate: float = 0.0,
    deposit_amount: float = 0.0,
    opening_hour: int = 8,
    closing_hour: int = 22,
    is_active: bool = True,
    rules: str = "",
) -> dict[str, Any]:
    """Create a new community amenity record."""
    create_amenities_tables()
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("Amenity name cannot be empty")
    if len(cleaned_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Amenity name exceeds maximum length of {MAX_NAME_LENGTH}")

    cat = category.strip().lower()
    if cat not in VALID_AMENITY_CATEGORIES:
        cats = sorted(VALID_AMENITY_CATEGORIES)
        raise ValueError(f"Invalid category '{category}'. Valid: {cats}")

    if capacity <= 0:
        raise ValueError("Capacity must be greater than zero")
    if hourly_rate < 0.0:
        raise ValueError("Hourly rate cannot be negative")
    if deposit_amount < 0.0:
        raise ValueError("Deposit amount cannot be negative")
    if (
        not (0 <= opening_hour <= MAX_HOUR_OF_DAY)
        or not (0 <= closing_hour <= MAX_HOUR_OF_DAY)
        or opening_hour >= closing_hour
    ):
        raise ValueError("Invalid operating hours: opening_hour must precede closing_hour (0-23)")

    now_str = datetime.now(UTC).isoformat()
    with closing(db_utils.get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO amenities ("
            "id, name, category, description, capacity, hourly_rate, deposit_amount, "
            "opening_hour, closing_hour, is_active, rules, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                amenity_id,
                cleaned_name,
                cat,
                description.strip()[:MAX_DESCRIPTION_LENGTH],
                capacity,
                round(float(hourly_rate), 2),
                round(float(deposit_amount), 2),
                opening_hour,
                closing_hour,
                1 if is_active else 0,
                rules.strip()[:MAX_RULES_LENGTH],
                now_str,
                now_str,
            ),
        )

    res = get_amenity(amenity_id)
    if not res:
        raise RuntimeError("Failed to retrieve created amenity")
    return res


def get_amenity(amenity_id: str) -> dict[str, Any] | None:
    """Retrieve an amenity by ID."""
    create_amenities_tables()
    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, category, description, capacity, hourly_rate, deposit_amount, "
            "opening_hour, closing_hour, is_active, rules, created_at, updated_at "
            "FROM amenities WHERE id = ?",
            (amenity_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "description": row[3],
            "capacity": row[4],
            "hourly_rate": float(row[5]),
            "deposit_amount": float(row[6]),
            "opening_hour": row[7],
            "closing_hour": row[8],
            "is_active": bool(row[9]),
            "rules": row[10],
            "created_at": row[11],
            "updated_at": row[12],
        }


def list_amenities(
    category: str | None = None,
    is_active: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List amenities with optional filtering."""
    create_amenities_tables()
    query = (
        "SELECT id, name, category, description, capacity, hourly_rate, deposit_amount, "
        "opening_hour, closing_hour, is_active, rules, created_at, updated_at "
        "FROM amenities WHERE 1=1"
    )
    params: list[Any] = []
    if category:
        query += " AND category = ?"
        params.append(category.strip().lower())
    if is_active is not None:
        query += " AND is_active = ?"
        params.append(1 if is_active else 0)

    query += " ORDER BY name ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "category": r[2],
                "description": r[3],
                "capacity": r[4],
                "hourly_rate": float(r[5]),
                "deposit_amount": float(r[6]),
                "opening_hour": r[7],
                "closing_hour": r[8],
                "is_active": bool(r[9]),
                "rules": r[10],
                "created_at": r[11],
                "updated_at": r[12],
            }
            for r in rows
        ]


def update_amenity(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    amenity_id: str,
    name: str | None = None,
    category: str | None = None,
    description: str | None = None,
    capacity: int | None = None,
    hourly_rate: float | None = None,
    deposit_amount: float | None = None,
    opening_hour: int | None = None,
    closing_hour: int | None = None,
    is_active: bool | None = None,
    rules: str | None = None,
) -> dict[str, Any] | None:
    """Update an existing amenity."""
    current = get_amenity(amenity_id)
    if not current:
        return None

    updates: list[str] = []
    params: list[Any] = []

    if name is not None:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Amenity name cannot be empty")
        updates.append("name = ?")
        params.append(cleaned_name[:MAX_NAME_LENGTH])

    if category is not None:
        cat = category.strip().lower()
        if cat not in VALID_AMENITY_CATEGORIES:
            cats = sorted(VALID_AMENITY_CATEGORIES)
            raise ValueError(f"Invalid category '{category}'. Valid: {cats}")
        updates.append("category = ?")
        params.append(cat)

    if description is not None:
        updates.append("description = ?")
        params.append(description.strip()[:MAX_DESCRIPTION_LENGTH])

    if capacity is not None:
        if capacity <= 0:
            raise ValueError("Capacity must be greater than zero")
        updates.append("capacity = ?")
        params.append(capacity)

    if hourly_rate is not None:
        if hourly_rate < 0.0:
            raise ValueError("Hourly rate cannot be negative")
        updates.append("hourly_rate = ?")
        params.append(round(float(hourly_rate), 2))

    if deposit_amount is not None:
        if deposit_amount < 0.0:
            raise ValueError("Deposit amount cannot be negative")
        updates.append("deposit_amount = ?")
        params.append(round(float(deposit_amount), 2))

    if opening_hour is not None or closing_hour is not None:
        op = opening_hour if opening_hour is not None else current["opening_hour"]
        cl = closing_hour if closing_hour is not None else current["closing_hour"]
        if (
            not (0 <= op <= MAX_HOUR_OF_DAY)
            or not (0 <= cl <= MAX_HOUR_OF_DAY)
            or op >= cl
        ):
            raise ValueError(
                "Invalid operating hours: opening_hour must precede closing_hour (0-23)"
            )
        if opening_hour is not None:
            updates.append("opening_hour = ?")
            params.append(opening_hour)
        if closing_hour is not None:
            updates.append("closing_hour = ?")
            params.append(closing_hour)

    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)

    if rules is not None:
        updates.append("rules = ?")
        params.append(rules.strip()[:MAX_RULES_LENGTH])

    if not updates:
        return current

    updates.append("updated_at = ?")
    params.append(datetime.now(UTC).isoformat())
    params.append(amenity_id)

    query = f"UPDATE amenities SET {', '.join(updates)} WHERE id = ?"
    with closing(db_utils.get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(query, params)

    return get_amenity(amenity_id)


def check_reservation_conflict(
    amenity_id: str,
    start_time: str,
    end_time: str,
    exclude_reservation_id: str | None = None,
) -> bool:
    """Return True if an overlapping active reservation exists for the given amenity."""
    create_amenities_tables()
    query = (
        "SELECT COUNT(*) FROM amenity_reservations "
        "WHERE amenity_id = ? "
        "AND status IN ('pending', 'confirmed') "
        "AND start_time < ? AND end_time > ?"
    )
    params: list[Any] = [amenity_id, end_time, start_time]
    if exclude_reservation_id:
        query += " AND id != ?"
        params.append(exclude_reservation_id)

    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return bool(row and row[0] > 0)


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Helper to parse ISO datetime string."""
    clean_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(clean_str)


def calculate_reservation_fees(
    amenity_id: str,
    start_time: str,
    end_time: str,
) -> tuple[float, float]:
    """Calculate (total_fee, deposit_required) given amenity rate and duration."""
    amenity = get_amenity(amenity_id)
    if not amenity:
        raise ValueError(f"Amenity with id '{amenity_id}' not found")

    dt_start = _parse_iso_datetime(start_time)
    dt_end = _parse_iso_datetime(end_time)
    if dt_end <= dt_start:
        raise ValueError("Reservation end_time must be after start_time")

    duration_seconds = (dt_end - dt_start).total_seconds()
    duration_hours = max(MIN_DURATION_HOURS, duration_seconds / SECONDS_PER_HOUR)
    total_fee = round(duration_hours * amenity["hourly_rate"], 2)
    deposit_amount = round(amenity["deposit_amount"], 2)
    return total_fee, deposit_amount


def create_reservation(  # noqa: PLR0913, PLR0917
    reservation_id: str,
    amenity_id: str,
    tenant_id: str,
    unit_id: str,
    start_time: str,
    end_time: str,
    attendees_count: int = 1,
    status: str = DEFAULT_RESERVATION_STATUS,
    notes: str = "",
) -> dict[str, Any]:
    """Create a new amenity reservation with conflict check and auto-calculated fees."""
    create_amenities_tables()
    amenity = get_amenity(amenity_id)
    if not amenity:
        raise ValueError(f"Amenity '{amenity_id}' not found")
    if not amenity["is_active"]:
        raise ValueError(f"Amenity '{amenity['name']}' is currently inactive for reservations")

    if attendees_count > amenity["capacity"]:
        raise ValueError(
            f"Attendees count ({attendees_count}) exceeds amenity capacity ({amenity['capacity']})"
        )

    st_dt = _parse_iso_datetime(start_time)
    end_dt = _parse_iso_datetime(end_time)
    if end_dt <= st_dt:
        raise ValueError("Reservation end_time must be strictly after start_time")

    if check_reservation_conflict(amenity_id, start_time, end_time):
        raise ValueError(
            f"Amenity '{amenity['name']}' is already reserved during this time interval"
        )

    st = status.strip().lower()
    if st not in VALID_RESERVATION_STATUSES:
        statuses = sorted(VALID_RESERVATION_STATUSES)
        raise ValueError(f"Invalid status '{status}'. Valid: {statuses}")

    total_fee, deposit_amount = calculate_reservation_fees(amenity_id, start_time, end_time)
    now_str = datetime.now(UTC).isoformat()

    with closing(db_utils.get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO amenity_reservations ("
            "id, amenity_id, tenant_id, unit_id, start_time, end_time, attendees_count, "
            "status, total_fee, deposit_paid, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reservation_id,
                amenity_id,
                tenant_id.strip(),
                unit_id.strip(),
                start_time,
                end_time,
                attendees_count,
                st,
                total_fee,
                deposit_amount,
                notes.strip()[:MAX_NOTES_LENGTH],
                now_str,
                now_str,
            ),
        )

    res = get_reservation(reservation_id)
    if not res:
        raise RuntimeError("Failed to retrieve created reservation")
    return res


def get_reservation(reservation_id: str) -> dict[str, Any] | None:
    """Retrieve an amenity reservation by ID with joined amenity details."""
    create_amenities_tables()
    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT r.id, r.amenity_id, r.tenant_id, r.unit_id, r.start_time, r.end_time, "
            "r.attendees_count, r.status, r.total_fee, r.deposit_paid, r.notes, "
            "r.created_at, r.updated_at, a.name, a.category, a.hourly_rate "
            "FROM amenity_reservations r "
            "JOIN amenities a ON r.amenity_id = a.id "
            "WHERE r.id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "amenity_id": row[1],
            "tenant_id": row[2],
            "unit_id": row[3],
            "start_time": row[4],
            "end_time": row[5],
            "attendees_count": row[6],
            "status": row[7],
            "total_fee": float(row[8]),
            "deposit_paid": float(row[9]),
            "notes": row[10],
            "created_at": row[11],
            "updated_at": row[12],
            "amenity_name": row[13],
            "amenity_category": row[14],
            "amenity_hourly_rate": float(row[15]),
        }


def list_reservations(
    amenity_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List reservations with optional filters."""
    create_amenities_tables()
    query = (
        "SELECT r.id, r.amenity_id, r.tenant_id, r.unit_id, r.start_time, r.end_time, "
        "r.attendees_count, r.status, r.total_fee, r.deposit_paid, r.notes, "
        "r.created_at, r.updated_at, a.name, a.category, a.hourly_rate "
        "FROM amenity_reservations r "
        "JOIN amenities a ON r.amenity_id = a.id "
        "WHERE 1=1"
    )
    params: list[Any] = []
    if amenity_id:
        query += " AND r.amenity_id = ?"
        params.append(amenity_id)
    if tenant_id:
        query += " AND r.tenant_id = ?"
        params.append(tenant_id)
    if status:
        query += " AND r.status = ?"
        params.append(status.strip().lower())

    query += " ORDER BY r.start_time DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "amenity_id": r[1],
                "tenant_id": r[2],
                "unit_id": r[3],
                "start_time": r[4],
                "end_time": r[5],
                "attendees_count": r[6],
                "status": r[7],
                "total_fee": float(r[8]),
                "deposit_paid": float(r[9]),
                "notes": r[10],
                "created_at": r[11],
                "updated_at": r[12],
                "amenity_name": r[13],
                "amenity_category": r[14],
                "amenity_hourly_rate": float(r[15]),
            }
            for r in rows
        ]


def update_reservation_status(
    reservation_id: str,
    status: str,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Transition reservation status and update notes."""
    create_amenities_tables()
    current = get_reservation(reservation_id)
    if not current:
        return None

    st = status.strip().lower()
    if st not in VALID_RESERVATION_STATUSES:
        statuses = sorted(VALID_RESERVATION_STATUSES)
        raise ValueError(f"Invalid status '{status}'. Valid: {statuses}")

    now_str = datetime.now(UTC).isoformat()
    updates = ["status = ?", "updated_at = ?"]
    params: list[Any] = [st, now_str]

    if notes is not None:
        updates.append("notes = ?")
        params.append(notes.strip()[:MAX_NOTES_LENGTH])

    params.append(reservation_id)
    query = f"UPDATE amenity_reservations SET {', '.join(updates)} WHERE id = ?"

    with closing(db_utils.get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(query, params)

    return get_reservation(reservation_id)


def delete_reservation(reservation_id: str) -> bool:
    """Delete a reservation by ID."""
    create_amenities_tables()
    with closing(db_utils.get_db_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM amenity_reservations WHERE id = ?", (reservation_id,))
        return cursor.rowcount > 0


def get_amenity_summary_metrics() -> dict[str, Any]:
    """Calculate summary metrics for amenities and bookings."""
    create_amenities_tables()
    with closing(db_utils.get_db_connection()) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM amenities WHERE is_active = 1")
        row = cursor.fetchone()
        active_amenities_count = row[0] if row else 0

        cursor.execute(
            "SELECT status, total_fee, deposit_paid, amenity_id FROM amenity_reservations"
        )
        rows = cursor.fetchall()

    total_reservations = len(rows)
    confirmed_count = 0
    pending_count = 0
    cancelled_count = 0
    completed_count = 0
    total_revenue = 0.0
    total_deposits_held = 0.0
    amenity_usage: dict[str, int] = {}

    for r_stat, fee, deposit, am_id in rows:
        st, flt_fee, flt_deposit = r_stat, float(fee), float(deposit)
        if st == "confirmed":
            confirmed_count += 1
            total_revenue += flt_fee
            total_deposits_held += flt_deposit
        elif st == "pending":
            pending_count += 1
        elif st == "cancelled":
            cancelled_count += 1
        elif st == "completed":
            completed_count += 1
            total_revenue += flt_fee

        amenity_usage[am_id] = amenity_usage.get(am_id, 0) + 1

    return {
        "active_amenities_count": active_amenities_count,
        "total_reservations": total_reservations,
        "confirmed_count": confirmed_count,
        "pending_count": pending_count,
        "cancelled_count": cancelled_count,
        "completed_count": completed_count,
        "total_revenue": round(total_revenue, 2),
        "total_deposits_held": round(total_deposits_held, 2),
        "amenity_usage_breakdown": amenity_usage,
    }
