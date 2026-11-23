"""Prospective leasing CRM, property tours, rental applications, and applicant screening engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils, webhooks


class LeadSource(StrEnum):
    ZILLOW = "zillow"
    APARTMENTS_COM = "apartments_com"
    WEBSITE = "website"
    WALK_IN = "walk_in"
    REFERRAL = "referral"
    BROKER = "broker"


class ProspectStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TOUR_SCHEDULED = "tour_scheduled"
    TOURED = "toured"
    APPLIED = "applied"
    APPROVED = "approved"
    LEASED = "leased"
    LOST = "lost"


class TourType(StrEnum):
    IN_PERSON = "in_person"
    VIRTUAL = "virtual"
    SELF_GUIDED = "self_guided"


class TourStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class ApplicationStatus(StrEnum):
    SUBMITTED = "submitted"
    SCREENING = "screening"
    APPROVED = "approved"
    CONDITIONALLY_APPROVED = "conditionally_approved"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"


class BackgroundCheckStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FLAGGED = "flagged"
    FAILED = "failed"


MIN_SEEDED_PROSPECTS = 2
MIN_INCOME_RATIO = 3.0
CONDITIONAL_INCOME_RATIO = 2.5
MIN_CREDIT_SCORE = 650
CONDITIONAL_CREDIT_SCORE = 600
DEFAULT_APPLICATION_FEE = 55.0


def _generate_prospect_id() -> str:
    return f"prs_{secrets.token_hex(4)}"


def _generate_tour_id() -> str:
    return f"tur_{secrets.token_hex(4)}"


def _generate_application_id() -> str:
    return f"app_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _today_str() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m-%d")


def init_leasing_crm_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize SQLite tables, indexes, and deterministic seed data for leasing CRM."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS leasing_prospects (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                lead_source TEXT NOT NULL DEFAULT 'website',
                stage TEXT NOT NULL DEFAULT 'new',
                desired_unit_id TEXT REFERENCES units(id) ON DELETE SET NULL,
                desired_bedrooms INTEGER NOT NULL DEFAULT 1,
                max_budget REAL NOT NULL DEFAULT 2500.0,
                target_move_in_date TEXT,
                assigned_agent TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS property_tours (
                id TEXT PRIMARY KEY,
                prospect_id TEXT NOT NULL REFERENCES leasing_prospects(id) ON DELETE CASCADE,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                tour_type TEXT NOT NULL DEFAULT 'in_person',
                scheduled_date TEXT NOT NULL,
                scheduled_time TEXT NOT NULL DEFAULT '14:00',
                leasing_agent TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'scheduled',
                feedback_rating INTEGER,
                feedback_notes TEXT NOT NULL DEFAULT '',
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rental_applications (
                id TEXT PRIMARY KEY,
                prospect_id TEXT NOT NULL REFERENCES leasing_prospects(id) ON DELETE CASCADE,
                unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                monthly_income REAL NOT NULL,
                target_rent REAL NOT NULL,
                income_to_rent_ratio REAL NOT NULL DEFAULT 0.0,
                credit_score INTEGER,
                background_status TEXT NOT NULL DEFAULT 'pending',
                eviction_history_clear INTEGER NOT NULL DEFAULT 1,
                recommended_decision TEXT NOT NULL DEFAULT 'pending',
                status TEXT NOT NULL DEFAULT 'submitted',
                application_fee REAL NOT NULL DEFAULT 55.0,
                fee_paid INTEGER NOT NULL DEFAULT 1,
                desired_move_in_date TEXT,
                lease_term_months INTEGER NOT NULL DEFAULT 12,
                decision_notes TEXT NOT NULL DEFAULT '',
                decided_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_leasing_prospects_stage ON leasing_prospects(stage)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_leasing_tours_unit_status "
            "ON property_tours(unit_id, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_leasing_apps_unit_status "
            "ON rental_applications(unit_id, status)"
        )

        _seed_leasing_data(cursor)
        conn.commit()
    finally:
        if close_conn:
            conn.close()


def _seed_leasing_data(cursor: sqlite3.Cursor) -> None:
    """Seed initial leasing prospects, scheduled tour, and rental application if empty."""
    cursor.execute("SELECT COUNT(*) FROM leasing_prospects")
    if cursor.fetchone()[0] >= MIN_SEEDED_PROSPECTS:
        return

    cursor.execute("SELECT id, monthly_rent FROM units LIMIT 2")
    units = cursor.fetchall()
    if not units:
        return

    now_iso = _now_iso()
    tour_date = (datetime.datetime.now(UTC) + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    move_in_date = (datetime.datetime.now(UTC) + datetime.timedelta(days=21)).strftime("%Y-%m-%d")

    u1_id = units[0][0]
    u1_rent = float(units[0][1] or 2200.0)
    cursor.execute(
        """
        INSERT OR IGNORE INTO leasing_prospects (
            id, full_name, email, phone, lead_source, stage, desired_unit_id,
            desired_bedrooms, max_budget, target_move_in_date, assigned_agent,
            notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "prs_seed_01",
            "Maya Lin",
            "maya.lin@example.com",
            "555-0191",
            LeadSource.ZILLOW.value,
            ProspectStage.TOUR_SCHEDULED.value,
            u1_id,
            2,
            2800.0,
            move_in_date,
            "Jordan Ellis",
            "Looking for quiet top-floor unit with EV charging.",
            now_iso,
            now_iso,
        ),
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO property_tours (
            id, prospect_id, unit_id, tour_type, scheduled_date, scheduled_time,
            leasing_agent, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "tur_seed_01",
            "prs_seed_01",
            u1_id,
            TourType.IN_PERSON.value,
            tour_date,
            "14:30",
            "Jordan Ellis",
            TourStatus.SCHEDULED.value,
            now_iso,
            now_iso,
        ),
    )

    u2_id = units[1][0] if len(units) > 1 else u1_id
    u2_rent = float(units[1][1] or 1950.0) if len(units) > 1 else u1_rent
    cursor.execute(
        """
        INSERT OR IGNORE INTO leasing_prospects (
            id, full_name, email, phone, lead_source, stage, desired_unit_id,
            desired_bedrooms, max_budget, target_move_in_date, assigned_agent,
            notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "prs_seed_02",
            "Devon Brooks",
            "devon.brooks@example.com",
            "555-0192",
            LeadSource.REFERRAL.value,
            ProspectStage.APPLIED.value,
            u2_id,
            1,
            2400.0,
            move_in_date,
            "Jordan Ellis",
            "Referred by current resident; income verified via paystubs.",
            now_iso,
            now_iso,
        ),
    )
    income_ratio = round(7200.0 / u2_rent, 2) if u2_rent > 0 else 0.0
    cursor.execute(
        """
        INSERT OR IGNORE INTO rental_applications (
            id, prospect_id, unit_id, monthly_income, target_rent, income_to_rent_ratio,
            credit_score, background_status, eviction_history_clear, recommended_decision,
            status, application_fee, fee_paid, desired_move_in_date, lease_term_months,
            decision_notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "app_seed_01",
            "prs_seed_02",
            u2_id,
            7200.0,
            u2_rent,
            income_ratio,
            735,
            BackgroundCheckStatus.PASSED.value,
            1,
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.SCREENING.value,
            DEFAULT_APPLICATION_FEE,
            1,
            move_in_date,
            12,
            "Meets 3.0x income and 650+ credit thresholds.",
            now_iso,
            now_iso,
        ),
    )


def _row_to_prospect(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "phone": row["phone"] or "",
        "lead_source": row["lead_source"],
        "stage": row["stage"],
        "desired_unit_id": row["desired_unit_id"],
        "desired_bedrooms": int(row["desired_bedrooms"]),
        "max_budget": round(float(row["max_budget"]), 2),
        "target_move_in_date": row["target_move_in_date"],
        "assigned_agent": row["assigned_agent"] or "",
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_tour(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "prospect_id": row["prospect_id"],
        "unit_id": row["unit_id"],
        "tour_type": row["tour_type"],
        "scheduled_date": row["scheduled_date"],
        "scheduled_time": row["scheduled_time"],
        "leasing_agent": row["leasing_agent"] or "",
        "status": row["status"],
        "feedback_rating": (
            int(row["feedback_rating"]) if row["feedback_rating"] is not None else None
        ),
        "feedback_notes": row["feedback_notes"] or "",
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_application(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "prospect_id": row["prospect_id"],
        "unit_id": row["unit_id"],
        "monthly_income": round(float(row["monthly_income"]), 2),
        "target_rent": round(float(row["target_rent"]), 2),
        "income_to_rent_ratio": round(float(row["income_to_rent_ratio"]), 2),
        "credit_score": int(row["credit_score"]) if row["credit_score"] is not None else None,
        "background_status": row["background_status"],
        "eviction_history_clear": bool(row["eviction_history_clear"]),
        "recommended_decision": row["recommended_decision"],
        "status": row["status"],
        "application_fee": round(float(row["application_fee"]), 2),
        "fee_paid": bool(row["fee_paid"]),
        "desired_move_in_date": row["desired_move_in_date"],
        "lease_term_months": int(row["lease_term_months"]),
        "decision_notes": row["decision_notes"] or "",
        "decided_at": row["decided_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_prospect(  # noqa: PLR0913
    full_name: str,
    email: str,
    *,
    phone: str = "",
    lead_source: str = LeadSource.WEBSITE.value,
    desired_unit_id: str | None = None,
    desired_bedrooms: int = 1,
    max_budget: float = 2500.0,
    target_move_in_date: str | None = None,
    assigned_agent: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Create a new prospective renter lead."""
    if not full_name or not full_name.strip():
        raise ValueError("full_name is required")
    if not email or "@" not in email:
        raise ValueError("Valid email is required")
    if max_budget <= 0:
        raise ValueError("max_budget must be greater than 0")
    if lead_source not in {s.value for s in LeadSource}:
        raise ValueError(f"Invalid lead_source '{lead_source}'")

    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        if desired_unit_id:
            cursor.execute("SELECT id FROM units WHERE id = ?", (desired_unit_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Unit '{desired_unit_id}' not found")

        pid = _generate_prospect_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO leasing_prospects (
                id, full_name, email, phone, lead_source, stage, desired_unit_id,
                desired_bedrooms, max_budget, target_move_in_date, assigned_agent,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                full_name.strip(),
                email.strip().lower(),
                phone.strip(),
                lead_source,
                ProspectStage.NEW.value,
                desired_unit_id,
                max(0, int(desired_bedrooms)),
                round(float(max_budget), 2),
                target_move_in_date,
                assigned_agent.strip(),
                notes.strip(),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM leasing_prospects WHERE id = ?", (pid,))
        record = _row_to_prospect(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("leasing.prospect_created", record)
    return record


def get_prospect(prospect_id: str) -> dict[str, Any] | None:
    """Retrieve a single leasing prospect by ID."""
    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leasing_prospects WHERE id = ?", (prospect_id,))
        row = cursor.fetchone()
        return _row_to_prospect(row) if row else None
    finally:
        conn.close()


def list_prospects(
    stage: str | None = None,
    lead_source: str | None = None,
    desired_unit_id: str | None = None,
) -> list[dict[str, Any]]:
    """List leasing prospects with optional filters."""
    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM leasing_prospects WHERE 1=1"
        params: list[Any] = []
        if stage:
            query += " AND stage = ?"
            params.append(stage)
        if lead_source:
            query += " AND lead_source = ?"
            params.append(lead_source)
        if desired_unit_id:
            query += " AND desired_unit_id = ?"
            params.append(desired_unit_id)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        return [_row_to_prospect(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def update_prospect(prospect_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update mutable fields on a leasing prospect."""
    allowed = {
        "phone",
        "stage",
        "desired_unit_id",
        "desired_bedrooms",
        "max_budget",
        "target_move_in_date",
        "assigned_agent",
        "notes",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if "stage" in filtered and filtered["stage"] not in {s.value for s in ProspectStage}:
        raise ValueError(f"Invalid prospect stage '{filtered['stage']}'")
    if "max_budget" in filtered and float(filtered["max_budget"]) <= 0:
        raise ValueError("max_budget must be greater than 0")

    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leasing_prospects WHERE id = ?", (prospect_id,))
        existing = cursor.fetchone()
        if existing is None:
            return None
        if not filtered:
            return _row_to_prospect(existing)

        filtered["updated_at"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        params = list(filtered.values()) + [prospect_id]
        cursor.execute(f"UPDATE leasing_prospects SET {set_clause} WHERE id = ?", params)
        conn.commit()
        cursor.execute("SELECT * FROM leasing_prospects WHERE id = ?", (prospect_id,))
        return _row_to_prospect(cursor.fetchone())
    finally:
        conn.close()


def schedule_tour(  # noqa: PLR0913
    prospect_id: str,
    unit_id: str,
    scheduled_date: str,
    *,
    scheduled_time: str = "14:00",
    tour_type: str = TourType.IN_PERSON.value,
    leasing_agent: str = "",
) -> dict[str, Any]:
    """Schedule a property tour for a prospect and advance prospect stage."""
    if tour_type not in {t.value for t in TourType}:
        raise ValueError(f"Invalid tour_type '{tour_type}'")
    if not scheduled_date or not scheduled_date.strip():
        raise ValueError("scheduled_date is required")

    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM leasing_prospects WHERE id = ?", (prospect_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Prospect '{prospect_id}' not found")
        cursor.execute("SELECT id FROM units WHERE id = ?", (unit_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Unit '{unit_id}' not found")

        tid = _generate_tour_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO property_tours (
                id, prospect_id, unit_id, tour_type, scheduled_date, scheduled_time,
                leasing_agent, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid,
                prospect_id,
                unit_id,
                tour_type,
                scheduled_date.strip(),
                scheduled_time.strip(),
                leasing_agent.strip(),
                TourStatus.SCHEDULED.value,
                now_iso,
                now_iso,
            ),
        )
        cursor.execute(
            """
            UPDATE leasing_prospects
            SET stage = ?, desired_unit_id = COALESCE(desired_unit_id, ?), updated_at = ?
            WHERE id = ? AND stage IN ('new', 'contacted')
            """,
            (ProspectStage.TOUR_SCHEDULED.value, unit_id, now_iso, prospect_id),
        )
        conn.commit()
        cursor.execute("SELECT * FROM property_tours WHERE id = ?", (tid,))
        tour = _row_to_tour(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("leasing.tour_scheduled", tour)
    return tour


def list_tours(
    prospect_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List scheduled and past property tours with optional filters."""
    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM property_tours WHERE 1=1"
        params: list[Any] = []
        if prospect_id:
            query += " AND prospect_id = ?"
            params.append(prospect_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY scheduled_date ASC, scheduled_time ASC"
        cursor.execute(query, params)
        return [_row_to_tour(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def complete_tour(
    tour_id: str,
    *,
    feedback_rating: int | None = None,
    feedback_notes: str = "",
    no_show: bool = False,
) -> dict[str, Any] | None:
    """Mark a property tour completed or no-show and update prospect stage."""
    max_rating = 5
    if feedback_rating is not None and not (1 <= feedback_rating <= max_rating):
        raise ValueError("feedback_rating must be between 1 and 5")

    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM property_tours WHERE id = ?", (tour_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        now_iso = _now_iso()
        next_status = TourStatus.NO_SHOW.value if no_show else TourStatus.COMPLETED.value
        cursor.execute(
            """
            UPDATE property_tours
            SET status = ?, feedback_rating = ?, feedback_notes = ?,
                completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_status, feedback_rating, feedback_notes.strip(), now_iso, now_iso, tour_id),
        )
        if not no_show:
            cursor.execute(
                """
                UPDATE leasing_prospects
                SET stage = ?, updated_at = ?
                WHERE id = ? AND stage IN ('new', 'contacted', 'tour_scheduled')
                """,
                (ProspectStage.TOURED.value, now_iso, row["prospect_id"]),
            )
        conn.commit()
        cursor.execute("SELECT * FROM property_tours WHERE id = ?", (tour_id,))
        updated = _row_to_tour(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("leasing.tour_completed", updated)
    return updated


def cancel_tour(tour_id: str) -> dict[str, Any] | None:
    """Cancel a scheduled property tour."""
    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM property_tours WHERE id = ?", (tour_id,))
        if cursor.fetchone() is None:
            return None
        now_iso = _now_iso()
        cursor.execute(
            "UPDATE property_tours SET status = ?, updated_at = ? WHERE id = ?",
            (TourStatus.CANCELLED.value, now_iso, tour_id),
        )
        conn.commit()
        cursor.execute("SELECT * FROM property_tours WHERE id = ?", (tour_id,))
        return _row_to_tour(cursor.fetchone())
    finally:
        conn.close()


def evaluate_screening(
    income_ratio: float,
    credit_score: int | None,
    background_status: str,
    eviction_history_clear: bool,
) -> str:
    """Compute automated underwriting recommendation from income, credit, and background."""
    if not eviction_history_clear or background_status == BackgroundCheckStatus.FAILED.value:
        return ApplicationStatus.DENIED.value
    if credit_score is None or background_status == BackgroundCheckStatus.PENDING.value:
        return ApplicationStatus.SCREENING.value
    if (
        income_ratio >= MIN_INCOME_RATIO
        and credit_score >= MIN_CREDIT_SCORE
        and background_status == BackgroundCheckStatus.PASSED.value
    ):
        return ApplicationStatus.APPROVED.value
    if (
        income_ratio >= CONDITIONAL_INCOME_RATIO
        and credit_score >= CONDITIONAL_CREDIT_SCORE
        and background_status in (
            BackgroundCheckStatus.PASSED.value,
            BackgroundCheckStatus.FLAGGED.value,
        )
    ):
        return ApplicationStatus.CONDITIONALLY_APPROVED.value
    return ApplicationStatus.DENIED.value


def submit_application(  # noqa: PLR0913
    prospect_id: str,
    unit_id: str,
    monthly_income: float,
    *,
    target_rent: float | None = None,
    credit_score: int | None = None,
    desired_move_in_date: str | None = None,
    lease_term_months: int = 12,
    application_fee: float = DEFAULT_APPLICATION_FEE,
    fee_paid: bool = True,
) -> dict[str, Any]:
    """Submit a formal rental application for a prospect and unit."""
    if monthly_income <= 0:
        raise ValueError("monthly_income must be greater than 0")
    if lease_term_months <= 0:
        raise ValueError("lease_term_months must be greater than 0")
    min_credit, max_credit = 300, 850
    if credit_score is not None and not (min_credit <= credit_score <= max_credit):
        raise ValueError("credit_score must be between 300 and 850")

    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM leasing_prospects WHERE id = ?", (prospect_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Prospect '{prospect_id}' not found")
        cursor.execute("SELECT id, monthly_rent FROM units WHERE id = ?", (unit_id,))
        unit_row = cursor.fetchone()
        if unit_row is None:
            raise ValueError(f"Unit '{unit_id}' not found")

        resolved_rent = (
            round(float(target_rent), 2)
            if target_rent is not None and target_rent > 0
            else round(float(unit_row["monthly_rent"] or 2000.0), 2)
        )
        ratio = round(float(monthly_income) / resolved_rent, 2) if resolved_rent > 0 else 0.0
        rec = evaluate_screening(ratio, credit_score, BackgroundCheckStatus.PENDING.value, True)

        aid = _generate_application_id()
        now_iso = _now_iso()
        cursor.execute(
            """
            INSERT INTO rental_applications (
                id, prospect_id, unit_id, monthly_income, target_rent, income_to_rent_ratio,
                credit_score, background_status, eviction_history_clear, recommended_decision,
                status, application_fee, fee_paid, desired_move_in_date, lease_term_months,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                prospect_id,
                unit_id,
                round(float(monthly_income), 2),
                resolved_rent,
                ratio,
                credit_score,
                BackgroundCheckStatus.PENDING.value,
                1,
                rec,
                ApplicationStatus.SUBMITTED.value,
                round(float(application_fee), 2),
                1 if fee_paid else 0,
                desired_move_in_date,
                int(lease_term_months),
                now_iso,
                now_iso,
            ),
        )
        cursor.execute(
            """
            UPDATE leasing_prospects
            SET stage = ?, desired_unit_id = ?, updated_at = ?
            WHERE id = ? AND stage NOT IN ('approved', 'leased')
            """,
            (ProspectStage.APPLIED.value, unit_id, now_iso, prospect_id),
        )
        conn.commit()
        cursor.execute("SELECT * FROM rental_applications WHERE id = ?", (aid,))
        app_record = _row_to_application(cursor.fetchone())
    finally:
        conn.close()

    webhooks.dispatch_event("leasing.application_submitted", app_record)
    return app_record


def get_application(application_id: str) -> dict[str, Any] | None:
    """Retrieve a single rental application by ID."""
    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rental_applications WHERE id = ?", (application_id,))
        row = cursor.fetchone()
        return _row_to_application(row) if row else None
    finally:
        conn.close()


def list_applications(
    prospect_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List rental applications with optional filters."""
    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        query = "SELECT * FROM rental_applications WHERE 1=1"
        params: list[Any] = []
        if prospect_id:
            query += " AND prospect_id = ?"
            params.append(prospect_id)
        if unit_id:
            query += " AND unit_id = ?"
            params.append(unit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        return [_row_to_application(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def screen_application(
    application_id: str,
    *,
    credit_score: int,
    background_status: str = BackgroundCheckStatus.PASSED.value,
    eviction_history_clear: bool = True,
    decision_notes: str = "",
) -> dict[str, Any] | None:
    """Record credit and background screening results and compute recommendation."""
    min_credit, max_credit = 300, 850
    if not (min_credit <= credit_score <= max_credit):
        raise ValueError("credit_score must be between 300 and 850")
    if background_status not in {b.value for b in BackgroundCheckStatus}:
        raise ValueError(f"Invalid background_status '{background_status}'")

    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rental_applications WHERE id = ?", (application_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        ratio = float(row["income_to_rent_ratio"])
        rec = evaluate_screening(ratio, credit_score, background_status, eviction_history_clear)
        now_iso = _now_iso()
        cursor.execute(
            """
            UPDATE rental_applications
            SET credit_score = ?, background_status = ?, eviction_history_clear = ?,
                recommended_decision = ?, status = ?, decision_notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                int(credit_score),
                background_status,
                1 if eviction_history_clear else 0,
                rec,
                ApplicationStatus.SCREENING.value,
                decision_notes.strip(),
                now_iso,
                application_id,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM rental_applications WHERE id = ?", (application_id,))
        return _row_to_application(cursor.fetchone())
    finally:
        conn.close()


def decide_application(
    application_id: str,
    decision: str,
    *,
    decision_notes: str = "",
) -> dict[str, Any] | None:
    """Approve, conditionally approve, deny, or withdraw a rental application."""
    valid_decisions = {
        ApplicationStatus.APPROVED.value,
        ApplicationStatus.CONDITIONALLY_APPROVED.value,
        ApplicationStatus.DENIED.value,
        ApplicationStatus.WITHDRAWN.value,
    }
    if decision not in valid_decisions:
        raise ValueError(f"Invalid application decision '{decision}'")

    conn = db_utils.get_db_connection()
    try:
        init_leasing_crm_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rental_applications WHERE id = ?", (application_id,))
        row = cursor.fetchone()
        if row is None:
            return None

        now_iso = _now_iso()
        cursor.execute(
            """
            UPDATE rental_applications
            SET status = ?, decision_notes = ?, decided_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (decision, decision_notes.strip(), now_iso, now_iso, application_id),
        )
        if decision in (
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.CONDITIONALLY_APPROVED.value,
        ):
            cursor.execute(
                "UPDATE leasing_prospects SET stage = ?, updated_at = ? WHERE id = ?",
                (ProspectStage.APPROVED.value, now_iso, row["prospect_id"]),
            )
        elif decision == ApplicationStatus.DENIED.value:
            cursor.execute(
                "UPDATE leasing_prospects SET stage = ?, updated_at = ? WHERE id = ?",
                (ProspectStage.LOST.value, now_iso, row["prospect_id"]),
            )
        conn.commit()
        cursor.execute("SELECT * FROM rental_applications WHERE id = ?", (application_id,))
        updated = _row_to_application(cursor.fetchone())
    finally:
        conn.close()

    if decision in (
        ApplicationStatus.APPROVED.value,
        ApplicationStatus.CONDITIONALLY_APPROVED.value,
    ):
        webhooks.dispatch_event("leasing.application_approved", updated)
    elif decision == ApplicationStatus.DENIED.value:
        webhooks.dispatch_event("leasing.application_denied", updated)
    return updated
