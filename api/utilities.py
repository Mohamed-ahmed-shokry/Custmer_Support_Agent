"""Database schema, models, CRUD helpers, anomaly detection, and metrics for utility submetering."""

from __future__ import annotations

import datetime
import secrets
import sqlite3
from datetime import UTC
from enum import StrEnum
from typing import Any

from api import db_utils

# Constants
MIN_SEEDED_METERS = 3
ANOMALY_SPIKE_RATIO = 1.5  # 50% above baseline flags anomaly
DEFAULT_ELECTRIC_RATE = 0.15  # $0.15 per kWh
DEFAULT_WATER_RATE = 0.009  # $0.009 per Gallon ($9 per 1,000 gal)
DEFAULT_GAS_RATE = 1.25  # $1.25 per Therm
DEFAULT_SEWER_TRASH_RATE = 45.00  # $45.00 flat split


class UtilityMeterType(StrEnum):
    ELECTRICITY = "electricity"
    WATER = "water"
    GAS = "gas"
    SEWER = "sewer"
    TRASH = "trash"


class MeterStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAULTY = "faulty"


class ReadingSource(StrEnum):
    SMART_METER_TELEMETRY = "smart_meter_telemetry"
    MANUAL_AUDIT = "manual_audit"
    RESIDENT_SELF_REPORT = "resident_self_report"
    UTILITY_PROVIDER = "utility_provider"


class UtilityInvoiceStatus(StrEnum):
    PENDING = "pending"
    POSTED_TO_LEDGER = "posted_to_ledger"
    PAID = "paid"
    DISPUTED = "disputed"


METER_UNITS_OF_MEASURE: dict[str, str] = {
    UtilityMeterType.ELECTRICITY: "kWh",
    UtilityMeterType.WATER: "gallons",
    UtilityMeterType.GAS: "therms",
    UtilityMeterType.SEWER: "units",
    UtilityMeterType.TRASH: "units",
}

DEFAULT_METER_RATES: dict[str, float] = {
    UtilityMeterType.ELECTRICITY: DEFAULT_ELECTRIC_RATE,
    UtilityMeterType.WATER: DEFAULT_WATER_RATE,
    UtilityMeterType.GAS: DEFAULT_GAS_RATE,
    UtilityMeterType.SEWER: 25.00,
    UtilityMeterType.TRASH: 20.00,
}


def _generate_meter_serial(meter_type: str, unit_id: str) -> str:
    prefix_map: dict[str, str] = {
        UtilityMeterType.ELECTRICITY: "EL",
        UtilityMeterType.WATER: "WTR",
        UtilityMeterType.GAS: "GAS",
        UtilityMeterType.SEWER: "SWR",
        UtilityMeterType.TRASH: "TSH",
    }
    pfx = prefix_map.get(meter_type, "MTR")
    u_clean = unit_id.replace("unit_", "").upper()
    rand = secrets.token_hex(2).upper()
    return f"{pfx}-{u_clean}-{rand}"


def _generate_invoice_number(billing_month: str) -> str:
    clean_m = billing_month.replace("-", "")
    rand = secrets.token_hex(2).upper()
    return f"UTIL-{clean_m}-{rand}"


def init_utilities_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize database tables for utility submetering, meter readings, and invoices."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS utility_meters (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL,
                meter_type TEXT NOT NULL DEFAULT 'electricity',
                serial_number TEXT UNIQUE NOT NULL,
                unit_of_measure TEXT NOT NULL DEFAULT 'kWh',
                rate_per_unit REAL NOT NULL DEFAULT 0.15,
                status TEXT NOT NULL DEFAULT 'active',
                installation_date TEXT NOT NULL,
                last_reading_value REAL NOT NULL DEFAULT 0.0,
                last_reading_date TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS utility_readings (
                id TEXT PRIMARY KEY,
                meter_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                reading_value REAL NOT NULL,
                previous_reading_value REAL NOT NULL DEFAULT 0.0,
                consumption REAL NOT NULL DEFAULT 0.0,
                rate_per_unit REAL NOT NULL DEFAULT 0.15,
                cost REAL NOT NULL DEFAULT 0.0,
                billing_period_start TEXT NOT NULL,
                billing_period_end TEXT NOT NULL,
                reading_date TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'smart_meter_telemetry',
                is_anomaly INTEGER NOT NULL DEFAULT 0,
                anomaly_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (meter_id) REFERENCES utility_meters(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS utility_invoices (
                id TEXT PRIMARY KEY,
                invoice_number TEXT UNIQUE NOT NULL,
                unit_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                billing_month TEXT NOT NULL,
                electricity_amount REAL NOT NULL DEFAULT 0.0,
                water_amount REAL NOT NULL DEFAULT 0.0,
                gas_amount REAL NOT NULL DEFAULT 0.0,
                sewer_trash_amount REAL NOT NULL DEFAULT 0.0,
                total_amount REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'pending',
                ledger_transaction_id TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (unit_id) REFERENCES units(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_util_meters_unit ON utility_meters(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_util_meters_type ON utility_meters(meter_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_util_readings_meter ON utility_readings(meter_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_util_readings_unit ON utility_readings(unit_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_util_readings_anomaly ON utility_readings(is_anomaly)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_util_invoices_tenant ON utility_invoices(tenant_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_util_invoices_month ON utility_invoices(billing_month)"
        )

        # Seed initial default data if table is empty
        cursor.execute("SELECT COUNT(*) FROM utility_meters")
        cnt = cursor.fetchone()[0]
        if cnt < MIN_SEEDED_METERS:
            _seed_default_utilities(cursor)

        conn.commit()
    finally:
        if close_conn:
            conn.close()


def _seed_default_utilities(cursor: sqlite3.Cursor) -> None:
    now_str = datetime.datetime.now(UTC).isoformat()
    first_of_month = datetime.datetime.now(UTC).strftime("%Y-%m-01")

    # Seed meters for unit_PH1 (Elena Rostova, Horizon Tower)
    seed_meters = [
        (
            "mtr_ph1_elec",
            "unit_PH1",
            UtilityMeterType.ELECTRICITY,
            "EL-PH1-901",
            "kWh",
            0.15,
            MeterStatus.ACTIVE,
            "2026-01-01",
            480.0,
            first_of_month,
            "Smart digital submeter installed in penthouse electrical riser",
            now_str,
            now_str,
        ),
        (
            "mtr_ph1_water",
            "unit_PH1",
            UtilityMeterType.WATER,
            "WTR-PH1-402",
            "gallons",
            0.009,
            MeterStatus.ACTIVE,
            "2026-01-01",
            3200.0,
            first_of_month,
            "Ultrasonic cold & hot water submeter",
            now_str,
            now_str,
        ),
        (
            "mtr_ph1_gas",
            "unit_PH1",
            UtilityMeterType.GAS,
            "GAS-PH1-105",
            "therms",
            1.25,
            MeterStatus.ACTIVE,
            "2026-01-01",
            35.0,
            first_of_month,
            "Penthouse fireplace and gourmet range gas submeter",
            now_str,
            now_str,
        ),
        (
            "mtr_101_elec",
            "unit_101",
            UtilityMeterType.ELECTRICITY,
            "EL-101-301",
            "kWh",
            0.15,
            MeterStatus.ACTIVE,
            "2026-01-01",
            310.0,
            first_of_month,
            "Standard unit electric submeter",
            now_str,
            now_str,
        ),
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO utility_meters (
            id, unit_id, meter_type, serial_number, unit_of_measure, rate_per_unit,
            status, installation_date, last_reading_value, last_reading_date,
            notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        seed_meters,
    )

    # Seed historical & anomaly readings
    seed_readings = [
        (
            "rdg_ph1_elec_01",
            "mtr_ph1_elec",
            "unit_PH1",
            480.0,
            0.0,
            480.0,
            0.15,
            72.00,
            "2026-10-01",
            "2026-10-31",
            first_of_month,
            ReadingSource.SMART_METER_TELEMETRY,
            0,
            "",
            now_str,
        ),
        (
            "rdg_ph1_water_01",
            "mtr_ph1_water",
            "unit_PH1",
            3200.0,
            1500.0,
            1700.0,
            0.009,
            15.30,
            "2026-10-01",
            "2026-10-31",
            first_of_month,
            ReadingSource.SMART_METER_TELEMETRY,
            1,
            (
                "Consumption spike detected: 1,700 gallons exceeds prior 900-gal baseline "
                "by 88%. Continuous flow indicates possible master bathroom toilet flapper leak."
            ),
            now_str,
        ),
        (
            "rdg_ph1_gas_01",
            "mtr_ph1_gas",
            "unit_PH1",
            35.0,
            0.0,
            35.0,
            1.25,
            43.75,
            "2026-10-01",
            "2026-10-31",
            first_of_month,
            ReadingSource.SMART_METER_TELEMETRY,
            0,
            "",
            now_str,
        ),
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO utility_readings (
            id, meter_id, unit_id, reading_value, previous_reading_value, consumption,
            rate_per_unit, cost, billing_period_start, billing_period_end, reading_date,
            source, is_anomaly, anomaly_notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        seed_readings,
    )

    # Seed utility invoice
    seed_invoices = [
        (
            "util_inv_ph1_2026_11",
            "UTIL-202611-PH1",
            "unit_PH1",
            "tenant_3",
            "2026-11",
            72.00,
            15.30,
            43.75,
            45.00,
            176.05,
            UtilityInvoiceStatus.POSTED_TO_LEDGER,
            "tx_seed_util_ph1",
            "November 2026 submetered utility statement posted to resident rent ledger.",
            now_str,
            now_str,
        )
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO utility_invoices (
            id, invoice_number, unit_id, tenant_id, billing_month, electricity_amount,
            water_amount, gas_amount, sewer_trash_amount, total_amount, status,
            ledger_transaction_id, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        seed_invoices,
    )


# ---------------------------------------------------------------------------
# Meter CRUD Operations
# ---------------------------------------------------------------------------


def create_utility_meter(
    payload: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Register a new submeter for a property unit."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()

        meter_id = payload.get("id") or f"mtr_{secrets.token_hex(4)}"
        unit_id = payload["unit_id"]
        meter_type = payload.get("meter_type", UtilityMeterType.ELECTRICITY)
        serial = payload.get("serial_number") or _generate_meter_serial(meter_type, unit_id)
        unit_of_measure = payload.get(
            "unit_of_measure", METER_UNITS_OF_MEASURE.get(meter_type, "units")
        )
        rate = float(payload.get("rate_per_unit", DEFAULT_METER_RATES.get(meter_type, 0.15)))
        status = payload.get("status", MeterStatus.ACTIVE)
        install_date = payload.get(
            "installation_date", datetime.datetime.now(UTC).strftime("%Y-%m-%d")
        )
        last_val = float(payload.get("last_reading_value", 0.0))
        last_date = payload.get("last_reading_date")
        notes = payload.get("notes", "")
        now_str = datetime.datetime.now(UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO utility_meters (
                id, unit_id, meter_type, serial_number, unit_of_measure, rate_per_unit,
                status, installation_date, last_reading_value, last_reading_date,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meter_id,
                unit_id,
                meter_type,
                serial,
                unit_of_measure,
                rate,
                status,
                install_date,
                last_val,
                last_date,
                notes,
                now_str,
                now_str,
            ),
        )
        conn.commit()
        return get_utility_meter(meter_id, conn)  # type: ignore[return-value]
    finally:
        if close_conn:
            conn.close()


def get_utility_meter(
    meter_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve submeter details by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id, m.unit_id, m.meter_type, m.serial_number, m.unit_of_measure,
                   m.rate_per_unit, m.status, m.installation_date, m.last_reading_value,
                   m.last_reading_date, m.notes, m.created_at, m.updated_at,
                   COALESCE(u.unit_number, '') as unit_number,
                   COALESCE(u.building_name, '') as building_name
            FROM utility_meters m
            LEFT JOIN units u ON m.unit_id = u.id
            WHERE m.id = ?
            """,
            (meter_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "unit_id": row[1],
            "meter_type": row[2],
            "serial_number": row[3],
            "unit_of_measure": row[4],
            "rate_per_unit": row[5],
            "status": row[6],
            "installation_date": row[7],
            "last_reading_value": row[8],
            "last_reading_date": row[9],
            "notes": row[10],
            "created_at": row[11],
            "updated_at": row[12],
            "unit_number": row[13],
            "building_name": row[14],
        }
    finally:
        if close_conn:
            conn.close()


def list_utility_meters(
    unit_id: str | None = None,
    meter_type: str | None = None,
    status: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List submeters with optional unit, type, and status filtering."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()
        query = """
            SELECT m.id, m.unit_id, m.meter_type, m.serial_number, m.unit_of_measure,
                   m.rate_per_unit, m.status, m.installation_date, m.last_reading_value,
                   m.last_reading_date, m.notes, m.created_at, m.updated_at,
                   COALESCE(u.unit_number, '') as unit_number,
                   COALESCE(u.building_name, '') as building_name
            FROM utility_meters m
            LEFT JOIN units u ON m.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []
        if unit_id:
            query += " AND m.unit_id = ?"
            params.append(unit_id)
        if meter_type:
            query += " AND m.meter_type = ?"
            params.append(meter_type)
        if status:
            query += " AND m.status = ?"
            params.append(status)

        query += " ORDER BY m.meter_type ASC, m.unit_id ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "unit_id": r[1],
                "meter_type": r[2],
                "serial_number": r[3],
                "unit_of_measure": r[4],
                "rate_per_unit": r[5],
                "status": r[6],
                "installation_date": r[7],
                "last_reading_value": r[8],
                "last_reading_date": r[9],
                "notes": r[10],
                "created_at": r[11],
                "updated_at": r[12],
                "unit_number": r[13],
                "building_name": r[14],
            }
            for r in rows
        ]
    finally:
        if close_conn:
            conn.close()


def update_utility_meter(
    meter_id: str, updates: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Update submeter configuration, rate, or operational status."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()

        fields: list[str] = []
        values: list[Any] = []
        allowed = {"status", "rate_per_unit", "notes", "last_reading_value", "last_reading_date"}
        for k, v in updates.items():
            if k in allowed:
                fields.append(f"{k} = ?")
                values.append(v)

        if not fields:
            return get_utility_meter(meter_id, conn)

        fields.append("updated_at = ?")
        values.append(datetime.datetime.now(UTC).isoformat())
        values.append(meter_id)

        cursor.execute(f"UPDATE utility_meters SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        return get_utility_meter(meter_id, conn)
    finally:
        if close_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Meter Readings & Anomaly Engine
# ---------------------------------------------------------------------------


def record_meter_reading(
    payload: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Record a meter reading, calculate consumption delta, and evaluate anomaly triggers."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()

        meter_id = payload["meter_id"]
        meter = get_utility_meter(meter_id, conn)
        if not meter:
            raise ValueError(f"Meter not found with ID {meter_id}")

        unit_id = meter["unit_id"]
        reading_val = float(payload["reading_value"])
        prev_default = meter.get("last_reading_value", 0.0)
        prev_val = float(payload.get("previous_reading_value", prev_default))
        consumption = max(0.0, reading_val - prev_val)
        rate = float(payload.get("rate_per_unit", meter["rate_per_unit"]))
        cost = round(consumption * rate, 2)

        start_date = payload.get(
            "billing_period_start", datetime.datetime.now(UTC).strftime("%Y-%m-01")
        )
        end_date = payload.get(
            "billing_period_end", datetime.datetime.now(UTC).strftime("%Y-%m-%d")
        )
        reading_date = payload.get("reading_date", datetime.datetime.now(UTC).strftime("%Y-%m-%d"))
        source = payload.get("source", ReadingSource.SMART_METER_TELEMETRY)

        # Automated Anomaly Detection: check historical average consumption for this meter
        cursor.execute(
            """
            SELECT AVG(consumption), COUNT(*)
            FROM utility_readings
            WHERE meter_id = ? AND is_anomaly = 0
            """,
            (meter_id,),
        )
        avg_row = cursor.fetchone()
        avg_hist = avg_row[0] if (avg_row and avg_row[0] is not None) else 0.0
        hist_count = avg_row[1] if avg_row else 0

        is_anomaly = False
        anomaly_notes = payload.get("anomaly_notes", "")

        # Flag anomaly if consumption exceeds 1.5x historical average (when baseline exists)
        if hist_count >= 1 and avg_hist > 0.0 and consumption >= avg_hist * ANOMALY_SPIKE_RATIO:
            is_anomaly = True
            pct_surge = round(((consumption - avg_hist) / avg_hist) * 100, 1)
            mtype = meter["meter_type"].title()
            u_meas = meter["unit_of_measure"]
            anomaly_notes = (
                f"Consumption spike detected: {consumption:.1f} {u_meas} "
                f"exceeds historical average ({avg_hist:.1f} {u_meas}) by {pct_surge}%. "
                f"Potential {mtype} leak or equipment malfunction."
            )

        reading_id = payload.get("id") or f"rdg_{secrets.token_hex(4)}"
        now_str = datetime.datetime.now(UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO utility_readings (
                id, meter_id, unit_id, reading_value, previous_reading_value, consumption,
                rate_per_unit, cost, billing_period_start, billing_period_end, reading_date,
                source, is_anomaly, anomaly_notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading_id,
                meter_id,
                unit_id,
                reading_val,
                prev_val,
                consumption,
                rate,
                cost,
                start_date,
                end_date,
                reading_date,
                source,
                1 if is_anomaly else 0,
                anomaly_notes,
                now_str,
            ),
        )

        # Update last reading on meter
        cursor.execute(
            """
            UPDATE utility_meters
            SET last_reading_value = ?, last_reading_date = ?, updated_at = ?
            WHERE id = ?
            """,
            (reading_val, reading_date, now_str, meter_id),
        )

        conn.commit()
        return get_meter_reading(reading_id, conn)  # type: ignore[return-value]
    finally:
        if close_conn:
            conn.close()


def get_meter_reading(
    reading_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve reading record by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.id, r.meter_id, r.unit_id, r.reading_value, r.previous_reading_value,
                   r.consumption, r.rate_per_unit, r.cost, r.billing_period_start,
                   r.billing_period_end, r.reading_date, r.source, r.is_anomaly,
                   r.anomaly_notes, r.created_at,
                   m.meter_type, m.serial_number, m.unit_of_measure,
                   COALESCE(u.unit_number, '') as unit_number
            FROM utility_readings r
            JOIN utility_meters m ON r.meter_id = m.id
            LEFT JOIN units u ON r.unit_id = u.id
            WHERE r.id = ?
            """,
            (reading_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "meter_id": row[1],
            "unit_id": row[2],
            "reading_value": row[3],
            "previous_reading_value": row[4],
            "consumption": row[5],
            "rate_per_unit": row[6],
            "cost": row[7],
            "billing_period_start": row[8],
            "billing_period_end": row[9],
            "reading_date": row[10],
            "source": row[11],
            "is_anomaly": bool(row[12]),
            "anomaly_notes": row[13],
            "created_at": row[14],
            "meter_type": row[15],
            "serial_number": row[16],
            "unit_of_measure": row[17],
            "unit_number": row[18],
        }
    finally:
        if close_conn:
            conn.close()


def list_meter_readings(
    meter_id: str | None = None,
    unit_id: str | None = None,
    is_anomaly: bool | None = None,
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List recent meter readings with filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()
        query = """
            SELECT r.id, r.meter_id, r.unit_id, r.reading_value, r.previous_reading_value,
                   r.consumption, r.rate_per_unit, r.cost, r.billing_period_start,
                   r.billing_period_end, r.reading_date, r.source, r.is_anomaly,
                   r.anomaly_notes, r.created_at,
                   m.meter_type, m.serial_number, m.unit_of_measure,
                   COALESCE(u.unit_number, '') as unit_number
            FROM utility_readings r
            JOIN utility_meters m ON r.meter_id = m.id
            LEFT JOIN units u ON r.unit_id = u.id
            WHERE 1=1
        """
        params: list[Any] = []
        if meter_id:
            query += " AND r.meter_id = ?"
            params.append(meter_id)
        if unit_id:
            query += " AND r.unit_id = ?"
            params.append(unit_id)
        if is_anomaly is not None:
            query += " AND r.is_anomaly = ?"
            params.append(1 if is_anomaly else 0)

        query += " ORDER BY r.reading_date DESC, r.created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "meter_id": r[1],
                "unit_id": r[2],
                "reading_value": r[3],
                "previous_reading_value": r[4],
                "consumption": r[5],
                "rate_per_unit": r[6],
                "cost": r[7],
                "billing_period_start": r[8],
                "billing_period_end": r[9],
                "reading_date": r[10],
                "source": r[11],
                "is_anomaly": bool(r[12]),
                "anomaly_notes": r[13],
                "created_at": r[14],
                "meter_type": r[15],
                "serial_number": r[16],
                "unit_of_measure": r[17],
                "unit_number": r[18],
            }
            for r in rows
        ]
    finally:
        if close_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Utility Invoices & Ledger Posting
# ---------------------------------------------------------------------------


def create_utility_invoice(
    payload: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Generate a monthly utility invoice statement for a resident unit."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()

        invoice_id = payload.get("id") or f"util_inv_{secrets.token_hex(4)}"
        unit_id = payload["unit_id"]
        tenant_id = payload["tenant_id"]
        month = payload.get("billing_month", datetime.datetime.now(UTC).strftime("%Y-%m"))
        inv_num = payload.get("invoice_number") or _generate_invoice_number(month)

        elec = float(payload.get("electricity_amount", 0.0))
        water = float(payload.get("water_amount", 0.0))
        gas = float(payload.get("gas_amount", 0.0))
        sewer_trash = float(payload.get("sewer_trash_amount", DEFAULT_SEWER_TRASH_RATE))
        total = round(elec + water + gas + sewer_trash, 2)

        status = payload.get("status", UtilityInvoiceStatus.PENDING)
        notes = payload.get("notes", "")
        now_str = datetime.datetime.now(UTC).isoformat()

        cursor.execute(
            """
            INSERT INTO utility_invoices (
                id, invoice_number, unit_id, tenant_id, billing_month, electricity_amount,
                water_amount, gas_amount, sewer_trash_amount, total_amount, status,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                inv_num,
                unit_id,
                tenant_id,
                month,
                elec,
                water,
                gas,
                sewer_trash,
                total,
                status,
                notes,
                now_str,
                now_str,
            ),
        )
        conn.commit()
        return get_utility_invoice(invoice_id, conn)  # type: ignore[return-value]
    finally:
        if close_conn:
            conn.close()


def get_utility_invoice(
    invoice_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Retrieve utility invoice statement by ID."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT i.id, i.invoice_number, i.unit_id, i.tenant_id, i.billing_month,
                   i.electricity_amount, i.water_amount, i.gas_amount, i.sewer_trash_amount,
                   i.total_amount, i.status, i.ledger_transaction_id, i.notes,
                   i.created_at, i.updated_at,
                   COALESCE(u.unit_number, '') as unit_number,
                   TRIM(COALESCE(t.first_name, '') || ' ' ||
                        COALESCE(t.last_name, '')) as tenant_name
            FROM utility_invoices i
            LEFT JOIN units u ON i.unit_id = u.id
            LEFT JOIN tenants t ON i.tenant_id = t.id
            WHERE i.id = ?
            """,
            (invoice_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "invoice_number": row[1],
            "unit_id": row[2],
            "tenant_id": row[3],
            "billing_month": row[4],
            "electricity_amount": row[5],
            "water_amount": row[6],
            "gas_amount": row[7],
            "sewer_trash_amount": row[8],
            "total_amount": row[9],
            "status": row[10],
            "ledger_transaction_id": row[11],
            "notes": row[12],
            "created_at": row[13],
            "updated_at": row[14],
            "unit_number": row[15],
            "tenant_name": row[16],
        }
    finally:
        if close_conn:
            conn.close()


def list_utility_invoices(
    unit_id: str | None = None,
    tenant_id: str | None = None,
    billing_month: str | None = None,
    status: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List utility invoices with filters."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()
        query = """
            SELECT i.id, i.invoice_number, i.unit_id, i.tenant_id, i.billing_month,
                   i.electricity_amount, i.water_amount, i.gas_amount, i.sewer_trash_amount,
                   i.total_amount, i.status, i.ledger_transaction_id, i.notes,
                   i.created_at, i.updated_at,
                   COALESCE(u.unit_number, '') as unit_number,
                   TRIM(COALESCE(t.first_name, '') || ' ' ||
                        COALESCE(t.last_name, '')) as tenant_name
            FROM utility_invoices i
            LEFT JOIN units u ON i.unit_id = u.id
            LEFT JOIN tenants t ON i.tenant_id = t.id
            WHERE 1=1
        """
        params: list[Any] = []
        if unit_id:
            query += " AND i.unit_id = ?"
            params.append(unit_id)
        if tenant_id:
            query += " AND i.tenant_id = ?"
            params.append(tenant_id)
        if billing_month:
            query += " AND i.billing_month = ?"
            params.append(billing_month)
        if status:
            query += " AND i.status = ?"
            params.append(status)

        query += " ORDER BY i.billing_month DESC, i.created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "invoice_number": r[1],
                "unit_id": r[2],
                "tenant_id": r[3],
                "billing_month": r[4],
                "electricity_amount": r[5],
                "water_amount": r[6],
                "gas_amount": r[7],
                "sewer_trash_amount": r[8],
                "total_amount": r[9],
                "status": r[10],
                "ledger_transaction_id": r[11],
                "notes": r[12],
                "created_at": r[13],
                "updated_at": r[14],
                "unit_number": r[15],
                "tenant_name": r[16],
            }
            for r in rows
        ]
    finally:
        if close_conn:
            conn.close()


def update_utility_invoice(
    invoice_id: str, updates: dict[str, Any], conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    """Update invoice status or notes."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()

        fields: list[str] = []
        values: list[Any] = []
        allowed = {"status", "notes", "ledger_transaction_id"}
        for k, v in updates.items():
            if k in allowed:
                fields.append(f"{k} = ?")
                values.append(v)

        if not fields:
            return get_utility_invoice(invoice_id, conn)

        fields.append("updated_at = ?")
        values.append(datetime.datetime.now(UTC).isoformat())
        values.append(invoice_id)

        cursor.execute(f"UPDATE utility_invoices SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        return get_utility_invoice(invoice_id, conn)
    finally:
        if close_conn:
            conn.close()


def post_utility_invoice_to_ledger(
    invoice_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Post an unpaid/pending utility invoice as a resident rent ledger charge."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        invoice = get_utility_invoice(invoice_id, conn)
        if not invoice:
            raise ValueError(f"Utility invoice not found with ID {invoice_id}")

        if invoice["status"] == UtilityInvoiceStatus.POSTED_TO_LEDGER and invoice.get(
            "ledger_transaction_id"
        ):
            return invoice

        # Post charge to billing_transactions
        tx_id = f"tx_util_{secrets.token_hex(4)}"
        desc = f"Submetered Utilities Statement ({invoice['billing_month']})"
        now_str = datetime.datetime.now(UTC).isoformat()
        today_str = datetime.datetime.now(UTC).strftime("%Y-%m-%d")

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO billing_transactions (
                id, tenant_id, unit_id, type, amount, status, due_date,
                description, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 'charge', ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (
                tx_id,
                invoice["tenant_id"],
                invoice["unit_id"],
                invoice["total_amount"],
                today_str,
                desc,
                f"Generated from utility invoice {invoice['invoice_number']}",
                now_str,
                now_str,
            ),
        )

        # Update tenant balance
        cursor.execute(
            "UPDATE tenants SET balance_due = balance_due + ? WHERE id = ?",
            (invoice["total_amount"], invoice["tenant_id"]),
        )

        # Update invoice status
        cursor.execute(
            """
            UPDATE utility_invoices
            SET status = 'posted_to_ledger', ledger_transaction_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (tx_id, now_str, invoice_id),
        )
        conn.commit()
        return get_utility_invoice(invoice_id, conn)  # type: ignore[return-value]
    finally:
        if close_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Summaries & Metrics Aggregation
# ---------------------------------------------------------------------------


def get_unit_utilities_summary(
    unit_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Get active meters, latest readings, anomalies, and current billing for a unit."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        meters = list_utility_meters(unit_id=unit_id, conn=conn)
        recent_readings = list_meter_readings(unit_id=unit_id, limit=10, conn=conn)
        invoices = list_utility_invoices(unit_id=unit_id, conn=conn)

        anomalies = [r for r in recent_readings if r.get("is_anomaly")]

        latest_elec = next(
            (r for r in recent_readings if r.get("meter_type") == UtilityMeterType.ELECTRICITY),
            None,
        )
        latest_water = next(
            (r for r in recent_readings if r.get("meter_type") == UtilityMeterType.WATER), None
        )
        latest_gas = next(
            (r for r in recent_readings if r.get("meter_type") == UtilityMeterType.GAS), None
        )

        return {
            "unit_id": unit_id,
            "meters_count": len(meters),
            "meters": meters,
            "has_anomaly": len(anomalies) > 0,
            "anomalies": anomalies,
            "latest_electricity_kwh": latest_elec.get("consumption", 0.0) if latest_elec else 0.0,
            "latest_water_gallons": latest_water.get("consumption", 0.0) if latest_water else 0.0,
            "latest_gas_therms": latest_gas.get("consumption", 0.0) if latest_gas else 0.0,
            "latest_invoice": invoices[0] if invoices else None,
        }
    finally:
        if close_conn:
            conn.close()


def get_tenant_utilities_summary(
    tenant_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Get utility telemetry, active meters, and invoice history for a resident."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT unit_id FROM tenants WHERE id = ?", (tenant_id,))
        row = cursor.fetchone()
        unit_id = row[0] if row else None
        if not unit_id:
            return {
                "tenant_id": tenant_id,
                "unit_id": None,
                "meters_count": 0,
                "meters": [],
                "has_anomaly": False,
                "anomalies": [],
                "latest_electricity_kwh": 0.0,
                "latest_water_gallons": 0.0,
                "latest_gas_therms": 0.0,
                "latest_invoice": None,
            }

        res = get_unit_utilities_summary(unit_id, conn)
        res["tenant_id"] = tenant_id
        return res
    finally:
        if close_conn:
            conn.close()


def get_utility_metrics_summary(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Aggregated utility submetering and conservation metrics."""
    close_conn = False
    if conn is None:
        conn = db_utils.get_db_connection()
        close_conn = True

    try:
        init_utilities_db(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM utility_meters")
        total_meters = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM utility_meters WHERE status = 'active'")
        active_meters = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM utility_readings")
        total_readings = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM utility_readings WHERE is_anomaly = 1")
        total_anomalies = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COALESCE(SUM(consumption), 0.0)
            FROM utility_readings r
            JOIN utility_meters m ON r.meter_id = m.id
            WHERE m.meter_type = 'electricity'
            """
        )
        total_kwh = round(cursor.fetchone()[0], 1)

        cursor.execute(
            """
            SELECT COALESCE(SUM(consumption), 0.0)
            FROM utility_readings r
            JOIN utility_meters m ON r.meter_id = m.id
            WHERE m.meter_type = 'water'
            """
        )
        total_gallons = round(cursor.fetchone()[0], 1)

        cursor.execute("SELECT COALESCE(SUM(total_amount), 0.0) FROM utility_invoices")
        total_billed = round(cursor.fetchone()[0], 2)

        cursor.execute(
            """
            SELECT COALESCE(SUM(total_amount), 0.0)
            FROM utility_invoices
            WHERE status = 'posted_to_ledger' OR status = 'paid'
            """
        )
        total_posted = round(cursor.fetchone()[0], 2)

        return {
            "total_meters": total_meters,
            "active_meters": active_meters,
            "total_readings": total_readings,
            "total_anomalies": total_anomalies,
            "total_kwh": total_kwh,
            "total_gallons": total_gallons,
            "total_billed": total_billed,
            "total_posted": total_posted,
        }
    finally:
        if close_conn:
            conn.close()
