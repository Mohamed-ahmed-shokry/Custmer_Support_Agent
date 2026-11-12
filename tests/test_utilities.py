"""Unit tests for the utility submetering and consumption anomaly engine."""

# ruff: noqa: PLR2004, E501

import sqlite3

import pytest
from api.utilities import (
    MeterStatus,
    ReadingSource,
    UtilityInvoiceStatus,
    UtilityMeterType,
    create_utility_invoice,
    create_utility_meter,
    get_meter_reading,
    get_tenant_utilities_summary,
    get_unit_utilities_summary,
    get_utility_meter,
    get_utility_metrics_summary,
    init_utilities_db,
    list_meter_readings,
    list_utility_invoices,
    list_utility_meters,
    post_utility_invoice_to_ledger,
    record_meter_reading,
    update_utility_invoice,
    update_utility_meter,
)


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS units (
            id TEXT PRIMARY KEY,
            unit_number TEXT NOT NULL,
            property_name TEXT NOT NULL DEFAULT 'Horizon Tower',
            building_name TEXT NOT NULL DEFAULT 'Horizon Tower',
            floor INTEGER DEFAULT 1,
            rent REAL DEFAULT 2000.0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            unit_id TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '555-0100',
            status TEXT NOT NULL DEFAULT 'active',
            balance_due REAL NOT NULL DEFAULT 0.0,
            FOREIGN KEY (unit_id) REFERENCES units(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_transactions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            due_date TEXT NOT NULL,
            description TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (unit_id) REFERENCES units(id)
        )
        """
    )

    cursor.execute(
        """
        INSERT INTO units (id, unit_number, property_name, building_name, floor, rent)
        VALUES ('unit_PH1', 'PH1', 'Horizon Tower', 'Horizon Tower', 25, 4500.0)
        """
    )
    cursor.execute(
        """
        INSERT INTO tenants (id, unit_id, first_name, last_name, email, phone, status, balance_due)
        VALUES ('tenant_3', 'unit_PH1', 'Elena', 'Rostova', 'elena@example.com', '555-0103', 'active', 0.0)
        """
    )
    cursor.execute(
        """
        INSERT INTO units (id, unit_number, property_name, building_name, floor, rent)
        VALUES ('unit_101', '101', 'Horizon Tower', 'Horizon Tower', 1, 2200.0)
        """
    )
    cursor.execute(
        """
        INSERT INTO tenants (id, unit_id, first_name, last_name, email, phone, status, balance_due)
        VALUES ('tenant_1', 'unit_101', 'Marcus', 'Vance', 'marcus@example.com', '555-0101', 'active', 0.0)
        """
    )
    conn.commit()

    init_utilities_db(conn)
    yield conn
    conn.close()


def test_init_utilities_db_seeds_defaults(memory_db):
    meters = list_utility_meters(conn=memory_db)
    assert len(meters) >= 3

    # Verify seed meter for unit_PH1
    ph1_elec = get_utility_meter("mtr_ph1_elec", conn=memory_db)
    assert ph1_elec is not None
    assert ph1_elec["unit_id"] == "unit_PH1"
    assert ph1_elec["meter_type"] == UtilityMeterType.ELECTRICITY
    assert ph1_elec["rate_per_unit"] == 0.15

    # Verify seed anomaly reading for water
    readings = list_meter_readings(meter_id="mtr_ph1_water", conn=memory_db)
    assert len(readings) >= 1
    assert readings[0]["is_anomaly"] is True
    assert "toilet" in readings[0]["anomaly_notes"].lower()

    # Verify seed invoice
    invoices = list_utility_invoices(unit_id="unit_PH1", conn=memory_db)
    assert len(invoices) >= 1
    assert invoices[0]["status"] == UtilityInvoiceStatus.POSTED_TO_LEDGER


def test_create_and_update_utility_meter(memory_db):
    payload = {
        "unit_id": "unit_PH1",
        "meter_type": UtilityMeterType.WATER,
        "serial_number": "WTR-TEST-999",
        "unit_of_measure": "gallons",
        "rate_per_unit": 0.01,
        "status": MeterStatus.ACTIVE,
        "notes": "Secondary balcony irrigation meter",
    }
    meter = create_utility_meter(payload, conn=memory_db)
    assert meter["id"].startswith("mtr_")
    assert meter["serial_number"] == "WTR-TEST-999"
    assert meter["rate_per_unit"] == 0.01

    # Update meter rate and status
    updated = update_utility_meter(
        meter["id"], {"rate_per_unit": 0.012, "status": MeterStatus.INACTIVE}, conn=memory_db
    )
    assert updated is not None
    assert updated["rate_per_unit"] == 0.012
    assert updated["status"] == MeterStatus.INACTIVE


def test_record_meter_reading_and_anomaly_detection(memory_db):
    # Normal reading
    rdg_payload = {
        "meter_id": "mtr_ph1_elec",
        "reading_value": 550.0,
        "previous_reading_value": 480.0,
        "billing_period_start": "2026-11-01",
        "billing_period_end": "2026-11-15",
        "reading_date": "2026-11-15",
        "source": ReadingSource.SMART_METER_TELEMETRY,
    }
    rdg = record_meter_reading(rdg_payload, conn=memory_db)
    assert rdg["consumption"] == 70.0
    assert rdg["cost"] == round(70.0 * 0.15, 2)
    assert rdg["is_anomaly"] is False

    # Check that meter last_reading_value is updated
    mtr = get_utility_meter("mtr_ph1_elec", conn=memory_db)
    assert mtr["last_reading_value"] == 550.0

    # Surge reading that triggers anomaly (> 1.5x baseline)
    surge_payload = {
        "meter_id": "mtr_ph1_elec",
        "reading_value": 1500.0,
        "previous_reading_value": 550.0,
        "billing_period_start": "2026-11-16",
        "billing_period_end": "2026-11-30",
        "reading_date": "2026-11-30",
        "source": ReadingSource.SMART_METER_TELEMETRY,
    }
    surge_rdg = record_meter_reading(surge_payload, conn=memory_db)
    assert surge_rdg["consumption"] == 950.0
    assert surge_rdg["is_anomaly"] is True
    assert "Consumption spike detected" in surge_rdg["anomaly_notes"]

    # Verify get_meter_reading
    fetched = get_meter_reading(surge_rdg["id"], conn=memory_db)
    assert fetched is not None
    assert fetched["consumption"] == 950.0


def test_utility_invoice_lifecycle_and_ledger_posting(memory_db):
    inv_payload = {
        "unit_id": "unit_PH1",
        "tenant_id": "tenant_3",
        "billing_month": "2026-12",
        "electricity_amount": 85.00,
        "water_amount": 22.50,
        "gas_amount": 35.00,
        "sewer_trash_amount": 45.00,
        "notes": "December 2026 statement",
    }
    invoice = create_utility_invoice(inv_payload, conn=memory_db)
    assert invoice["total_amount"] == 187.50
    assert invoice["status"] == UtilityInvoiceStatus.PENDING

    # Update invoice note
    updated_inv = update_utility_invoice(
        invoice["id"], {"notes": "Updated statement notes"}, conn=memory_db
    )
    assert updated_inv["notes"] == "Updated statement notes"

    # Post invoice to resident ledger
    posted = post_utility_invoice_to_ledger(invoice["id"], conn=memory_db)
    assert posted["status"] == UtilityInvoiceStatus.POSTED_TO_LEDGER
    assert posted["ledger_transaction_id"] is not None

    # Verify tenant balance was updated
    cursor = memory_db.cursor()
    cursor.execute("SELECT balance_due FROM tenants WHERE id = 'tenant_3'")
    assert cursor.fetchone()[0] == 187.50

    # Idempotent posting
    reposted = post_utility_invoice_to_ledger(invoice["id"], conn=memory_db)
    assert reposted["ledger_transaction_id"] == posted["ledger_transaction_id"]


def test_summaries_and_metrics(memory_db):
    unit_summary = get_unit_utilities_summary("unit_PH1", conn=memory_db)
    assert unit_summary["unit_id"] == "unit_PH1"
    assert unit_summary["meters_count"] >= 3
    assert unit_summary["has_anomaly"] is True
    assert len(unit_summary["anomalies"]) >= 1

    tenant_summary = get_tenant_utilities_summary("tenant_3", conn=memory_db)
    assert tenant_summary["tenant_id"] == "tenant_3"
    assert tenant_summary["unit_id"] == "unit_PH1"
    assert tenant_summary["has_anomaly"] is True

    metrics = get_utility_metrics_summary(conn=memory_db)
    assert metrics["total_meters"] >= 3
    assert metrics["active_meters"] >= 3
    assert metrics["total_anomalies"] >= 1
    assert metrics["total_billed"] > 0
