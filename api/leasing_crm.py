"""Prospective leasing CRM, property tours, rental applications, and applicant screening engine."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum

from api import db_utils


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
