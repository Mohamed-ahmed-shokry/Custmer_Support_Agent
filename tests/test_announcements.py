"""Unit tests for community announcements, emergency alerts, and concierge engine."""

import sqlite3

import pytest
from api import announcements


@pytest.fixture
def memory_db():
    """In-memory SQLite database connection with announcements schema."""
    conn = sqlite3.connect(":memory:")
    # Initialize tenants and units tables for FK references
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS units (
            id TEXT PRIMARY KEY,
            unit_number TEXT NOT NULL,
            floor INTEGER,
            building TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            unit_id TEXT REFERENCES units(id)
        )
        """
    )
    cursor.execute(
        "INSERT INTO units (id, unit_number, building) VALUES ('unit_PH1', 'PH1', 'North Tower')"
    )
    cursor.execute(
        "INSERT INTO tenants (id, first_name, last_name, unit_id) "
        "VALUES ('tenant_3', 'Elena', 'Rostova', 'unit_PH1')"
    )
    conn.commit()

    # Initialize announcements DB
    announcements.init_announcements_db(conn)
    yield conn
    conn.close()


def test_init_announcements_db_seeds_defaults(memory_db):
    """Verify schema initialization seeds default announcements, acks, and requests."""
    cursor = memory_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM community_announcements")
    ann_count = cursor.fetchone()[0]
    expected_min_ann = 2
    assert ann_count >= expected_min_ann

    cursor.execute("SELECT COUNT(*) FROM announcement_acknowledgments")
    ack_count = cursor.fetchone()[0]
    expected_min_ack = 1
    assert ack_count >= expected_min_ack

    cursor.execute("SELECT COUNT(*) FROM concierge_requests")
    con_count = cursor.fetchone()[0]
    expected_min_con = 1
    assert con_count >= expected_min_con


def test_create_and_get_announcement(memory_db):
    """Test creating and retrieving an announcement."""
    ann = announcements.create_announcement(
        title="Pool Closure for Annual Resurfacing",
        content="The lap pool and spa will be closed next Monday through Wednesday.",
        category=announcements.AnnouncementCategory.AMENITY_UPDATE,
        priority=announcements.AnnouncementPriority.NORMAL,
        scope=announcements.AnnouncementScope.PORTFOLIO_WIDE,
        author_name="Facilities Team",
        is_pinned=True,
        require_acknowledgment=False,
        conn=memory_db,
    )

    assert ann["id"].startswith("ann_")
    assert ann["announcement_number"].startswith("ANN-")
    assert ann["title"] == "Pool Closure for Annual Resurfacing"
    assert ann["category"] == "amenity_update"
    assert ann["priority"] == "normal"
    assert ann["is_pinned"] is True
    assert ann["require_acknowledgment"] is False
    assert ann["status"] == "published"

    fetched = announcements.get_announcement(ann["id"], conn=memory_db)
    assert fetched is not None
    assert fetched["id"] == ann["id"]
    assert fetched["title"] == ann["title"]


def test_update_and_delete_announcement(memory_db):
    """Test updating and deleting an announcement."""
    ann = announcements.create_announcement(
        title="Fire Alarm Inspection",
        content="Annual alarm audio tests will occur tomorrow.",
        category=announcements.AnnouncementCategory.MAINTENANCE_ADVISORY,
        priority=announcements.AnnouncementPriority.URGENT,
        require_acknowledgment=True,
        conn=memory_db,
    )

    updated = announcements.update_announcement(
        ann["id"],
        title="Fire Alarm Inspection (Rescheduled)",
        priority="critical_emergency",
        status="published",
        conn=memory_db,
    )
    assert updated is not None
    assert updated["title"] == "Fire Alarm Inspection (Rescheduled)"
    assert updated["priority"] == "critical_emergency"

    # Delete
    deleted = announcements.delete_announcement(ann["id"], conn=memory_db)
    assert deleted is True
    assert announcements.get_announcement(ann["id"], conn=memory_db) is None


def test_list_announcements_and_tenant_filters(memory_db):
    """Test filtering announcements by category, priority, and tenant scope."""
    # Create unit specific announcement for Elena
    announcements.create_announcement(
        title="Penthouse Terrace Window Wash",
        content="Exterior window cleaning team will access the roof terrace.",
        category=announcements.AnnouncementCategory.MAINTENANCE_ADVISORY,
        priority=announcements.AnnouncementPriority.NORMAL,
        scope=announcements.AnnouncementScope.UNIT_SPECIFIC,
        target_unit_id="unit_PH1",
        conn=memory_db,
    )

    # List filtered by category
    maint_list = announcements.list_announcements(
        category=announcements.AnnouncementCategory.MAINTENANCE_ADVISORY,
        conn=memory_db,
    )
    expected_maint = 2
    assert maint_list["total"] >= expected_maint

    # List tenant announcements
    tenant_ann = announcements.list_tenant_announcements(
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        conn=memory_db,
    )
    expected_min_tenant_ann = 3
    assert tenant_ann["total"] >= expected_min_tenant_ann

    # Check is_acknowledged flag
    freeze_advisory = next(
        (a for a in tenant_ann["items"] if a["announcement_number"] == "EMG-2026-005"),
        None,
    )
    assert freeze_advisory is not None
    assert freeze_advisory["is_acknowledged"] is True


def test_acknowledge_announcement_lifecycle(memory_db):
    """Test recording resident acknowledgment of an emergency alert."""
    ann = announcements.create_announcement(
        title="Boiler Outage Alert",
        content="Hot water temporarily interrupted due to pump replacement.",
        category=announcements.AnnouncementCategory.EMERGENCY_ALERT,
        priority=announcements.AnnouncementPriority.URGENT,
        require_acknowledgment=True,
        conn=memory_db,
    )

    assert announcements.has_tenant_acknowledged(ann["id"], "tenant_3", conn=memory_db) is False

    ack = announcements.acknowledge_announcement(
        announcement_id=ann["id"],
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        channel="chat_session",
        notes="Understood, will check back at 3 PM",
        conn=memory_db,
    )
    assert ack["announcement_id"] == ann["id"]
    assert ack["tenant_id"] == "tenant_3"
    assert ack["channel"] == "chat_session"

    assert announcements.has_tenant_acknowledged(ann["id"], "tenant_3", conn=memory_db) is True

    acks = announcements.get_announcement_acknowledgments(ann["id"], conn=memory_db)
    expected_count = 1
    assert len(acks) == expected_count


def test_concierge_requests_lifecycle(memory_db):
    """Test submitting, updating, and fulfilling a resident concierge request."""
    req = announcements.create_concierge_request(
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        request_type=announcements.ConciergeType.PACKAGE_HOLD,
        priority=announcements.AnnouncementPriority.URGENT,
        instructions="Please hold oversized wine shipment in climate control room until Friday",
        preferred_date="2026-11-20",
        assigned_staff="Concierge Marcus",
        conn=memory_db,
    )

    assert req["id"].startswith("con_")
    assert req["request_number"].startswith("CON-")
    assert req["request_type"] == "package_hold"
    assert req["status"] == "submitted"

    # Update to fulfilled
    updated = announcements.update_concierge_request(
        req["id"],
        status=announcements.ConciergeStatus.FULFILLED,
        fulfillment_notes="Package stored in temperature-controlled locker A-4",
        conn=memory_db,
    )
    assert updated is not None
    assert updated["status"] == "fulfilled"
    assert "locker A-4" in str(updated["fulfillment_notes"])

    # List requests for tenant
    tenant_reqs = announcements.list_tenant_concierge_requests("tenant_3", conn=memory_db)
    expected_min_reqs = 2
    assert tenant_reqs["total"] >= expected_min_reqs

    # Delete request
    deleted = announcements.delete_concierge_request(req["id"], conn=memory_db)
    assert deleted is True
    assert announcements.get_concierge_request(req["id"], conn=memory_db) is None


def test_announcements_metrics_summary(memory_db):
    """Test aggregate portfolio metrics computation."""
    metrics = announcements.get_announcements_metrics_summary(conn=memory_db)
    min_expected = 2
    assert metrics["total_announcements"] >= min_expected
    assert metrics["published_announcements"] >= min_expected
    assert metrics["active_emergency_alerts"] >= 1
    assert metrics["total_acknowledgments"] >= 1
    assert metrics["total_concierge_requests"] >= 1
