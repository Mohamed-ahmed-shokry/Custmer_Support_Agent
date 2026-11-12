"""Unit tests for tenant and property context grounding engine and macro variable resolution."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from api import (
    access_control,
    amenities,
    announcements,
    db_utils,
    incidents,
    move_logistics,
    packages,
    parking,
    pets,
    vendors,
)
from api.macros import render_template
from api.tenant_context import (
    build_tenant_rag_context,
    extract_tenant_macro_variables,
    format_currency,
    inject_tenant_context_into_prompt,
)


@pytest.fixture(autouse=True)
def setup_temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Fixture providing an isolated temporary database for each test."""
    db_file = tmp_path / "test_tenant_context.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_file))
    with closing(sqlite3.connect(str(db_file))) as conn:
        conn.row_factory = sqlite3.Row
    db_utils.create_application_logs()
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_work_orders()
    db_utils.create_billing_transactions()
    db_utils.create_lease_renewals()
    db_utils.create_inspections()
    vendors.create_vendors()
    packages.init_packages()
    parking.init_parking_db()
    pets.init_pets_db()
    access_control.init_access_control_db()
    incidents.init_incidents_db()
    announcements.init_announcements_db()
    db_utils.create_session_labels()
    db_utils.migrate_session_labels()
    yield


def test_format_currency():
    """Verify standard USD currency formatting and edge cases."""
    assert format_currency(None) == "$0.00"
    assert format_currency(0) == "$0.00"
    assert format_currency(1850) == "$1,850.00"
    assert format_currency(2450.75) == "$2,450.75"
    assert format_currency(1234567.89) == "$1,234,567.89"


def test_build_tenant_rag_context_empty():
    """Verify that build_tenant_rag_context returns empty string when no profile is found."""
    assert build_tenant_rag_context() == ""
    assert build_tenant_rag_context(tenant_id="non_existent") == ""
    assert build_tenant_rag_context(unit_id="non_existent") == ""
    assert build_tenant_rag_context(session_id="empty-session") == ""


def test_build_tenant_rag_context_with_tenant_and_unit():
    """Verify structured Markdown grounding block for pre-seeded tenant_1 and unit_101."""
    block = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in block
    assert "Resident Name: Sarah Connor" in block
    assert "Email: sarah.connor@example.com" in block
    assert "Phone: +1-555-0199" in block
    assert "Unit: 101" in block
    assert "Building: Building A" in block
    assert "Floor: 1" in block
    assert "Type: Apartment" in block
    assert "Lease Term: 2026-01-01 to 2026-12-31 (Status: active)" in block
    assert "Monthly Rent: $1,450.00 | Current Balance Due: $0.00" in block
    assert "Property Amenities & Access:" in block
    assert "- Parking Spot: P-12" in block
    assert "- Gate / Access Code: #1010" in block
    assert "- Trash Pickup: Tuesday" in block
    assert "Emergency Contact: John Connor (+1-555-0198)" in block
    assert "Tenant Account Notes: Prefers email notifications for routine maintenance." in block
    assert "[END RESIDENT & PROPERTY UNIT PROFILE]" in block
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" in block
    assert "[wo_101] Kitchen faucet leaking constantly" in block
    assert "Status: scheduled" in block
    assert "[END ACTIVE MAINTENANCE WORK ORDERS]" in block


def test_build_tenant_rag_context_from_session():
    """Verify resident grounding block resolved directly from linked session_id."""
    sid = "sess-rag-context"
    db_utils.insert_application_logs(sid, "When is rent due?", "First of month", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_2")

    block = build_tenant_rag_context(session_id=sid)
    assert "Resident Name: Marcus Vance" in block
    assert "Unit: 204" in block
    assert "Monthly Rent: $1,850.00 | Current Balance Due: $1,850.00" in block
    assert "- Parking Spot: P-24" in block
    assert "- Gate / Access Code: #2040" in block


def test_build_tenant_rag_context_unit_only():
    """Verify grounding block when only unit_id is provided without tenant."""
    block = build_tenant_rag_context(unit_id="unit_PH1")
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in block
    assert "Resident Name" not in block
    assert "Unit: PH1" in block
    assert "Building: Main Tower" in block
    assert "Floor: 12" in block
    assert "- Gate / Access Code: *9988" in block


def test_inject_tenant_context_into_prompt():
    """Verify prompt augmentation prepends resident context block."""
    raw_query = "What is my parking spot and access code?"

    # Unlinked session returns raw query unmodified
    unlinked = inject_tenant_context_into_prompt(raw_query, session_id="unlinked-sess")
    assert unlinked == raw_query

    # Linked session prepends resident context
    sid = "sess-inject-test"
    db_utils.insert_application_logs(sid, "Hi", "Hello", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    augmented = inject_tenant_context_into_prompt(raw_query, session_id=sid)
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in augmented
    assert "Resident Name: Sarah Connor" in augmented
    assert "Parking Spot: P-12" in augmented
    assert "Resident Inquiry / Question:\n" in augmented
    assert raw_query in augmented


def test_extract_tenant_macro_variables():
    """Verify macro variable dictionary extraction from tenant and unit profiles."""
    # From tenant_1 (with linked unit_101)
    vars_dict = extract_tenant_macro_variables(tenant_id="tenant_1")
    assert vars_dict["customer_name"] == "Sarah Connor"
    assert vars_dict["tenant_first_name"] == "Sarah"
    assert vars_dict["tenant_last_name"] == "Connor"
    assert vars_dict["tenant_email"] == "sarah.connor@example.com"
    assert vars_dict["tenant_phone"] == "+1-555-0199"
    assert vars_dict["unit_id"] == "101"
    assert vars_dict["unit_number"] == "101"
    assert vars_dict["building"] == "Building A"
    assert vars_dict["floor"] == "1"
    assert vars_dict["unit_type"] == "Apartment"
    assert vars_dict["monthly_rent"] == "$1,450.00"
    assert vars_dict["balance_due"] == "$0.00"
    assert vars_dict["lease_start"] == "2026-01-01"
    assert vars_dict["lease_end"] == "2026-12-31"
    assert vars_dict["lease_status"] == "active"
    assert vars_dict["parking_spot"] == "P-12"
    assert vars_dict["gate_code"] == "#1010"
    assert vars_dict["access_code"] == "#1010"
    assert vars_dict["trash_day"] == "Tuesday"
    assert vars_dict["emergency_contact_name"] == "John Connor"
    assert vars_dict["emergency_contact_phone"] == "+1-555-0198"
    assert vars_dict["open_work_orders_count"] == "1"
    assert vars_dict["latest_work_order_id"] == "wo_101"
    assert vars_dict["latest_work_order_title"] == "Kitchen faucet leaking constantly"
    assert vars_dict["latest_work_order_status"] == "scheduled"


def test_build_tenant_rag_context_work_orders_grounding():
    """Verify that open work orders are grounded and completed orders are omitted."""
    # tenant_2 has open work order wo_102
    block = build_tenant_rag_context(tenant_id="tenant_2")
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" in block
    assert "[wo_102] Living room AC blowing ambient air" in block
    assert "Priority: high" in block
    assert "Status: in_progress" in block

    # tenant_3 only has completed work order wo_103, so no active orders
    t3_block = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" not in t3_block

    # include_work_orders=False suppresses work orders block
    suppressed = build_tenant_rag_context(tenant_id="tenant_2", include_work_orders=False)
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_work_orders():
    """Verify macro template rendering with work order variables from linked session."""
    sid = "sess-macro-wo"
    db_utils.insert_application_logs(sid, "When is repair?", "Tomorrow", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Hi {customer_name}, you have {open_work_orders_count} open ticket: "
        "{latest_work_order_id} ({latest_work_order_title}) is "
        "currently {latest_work_order_status}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hi Sarah Connor, you have 1 open ticket:" in rendered
    assert "wo_101 (Kitchen faucet leaking constantly) is currently scheduled." in rendered


def test_render_template_with_session_tenant_resolution():
    """Verify render_template automatically resolves tenant placeholders from session_id."""
    sid = "sess-macro-render"
    db_utils.insert_application_logs(sid, "Payment question", "Details", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_2")

    template = (
        "Hello {customer_name}, your balance for unit {unit_id} is {balance_due}. "
        "Your assigned parking spot is {parking_spot} and gate code is {gate_code}."
    )

    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hello Marcus Vance" in rendered
    assert "unit 204 is $1,850.00" in rendered
    assert "parking spot is P-24" in rendered
    assert "gate code is #2040" in rendered


def test_render_template_overrides_tenant_variables():
    """Verify that explicitly passed variables take precedence over tenant profile defaults."""
    sid = "sess-macro-override"
    db_utils.insert_application_logs(sid, "Query", "Answer", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = "Resident {customer_name}, rent balance is {balance_due}."
    custom_vars = {"customer_name": "Ms. Sarah Connor, VIP", "balance_due": "$100.00"}

    rendered, unresolved = render_template(template, variables=custom_vars, session_id=sid)
    assert unresolved == []
    assert rendered == "Resident Ms. Sarah Connor, VIP, rent balance is $100.00."


def test_build_tenant_rag_context_billing_grounding():
    """Verify that billing ledger and payment history are grounded in RAG prompt context."""
    # tenant_1 has recorded ACH payment and zero balance
    t1_block = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[RESIDENT BILLING & PAYMENT LEDGER]" in t1_block
    assert "Current Balance Due: $0.00 | Monthly Rent: $1,450.00" in t1_block
    assert "Last Payment: $1,450.00 on 2026-10-01T09:30:00Z via ach (Ref: ACH-88412)" in t1_block
    assert "[END RESIDENT BILLING & PAYMENT LEDGER]" in t1_block

    # tenant_2 has overdue rent and late fee
    t2_block = build_tenant_rag_context(tenant_id="tenant_2")
    assert "[RESIDENT BILLING & PAYMENT LEDGER]" in t2_block
    assert "Overdue Amount:" in t2_block
    assert "overdue charge(s)" in t2_block

    # include_billing=False suppresses billing block
    suppressed = build_tenant_rag_context(tenant_id="tenant_1", include_billing=False)
    assert "[RESIDENT BILLING & PAYMENT LEDGER]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_billing_variables():
    """Verify macro template rendering with financial and billing variables."""
    sid = "sess-macro-billing"
    db_utils.insert_application_logs(sid, "Payment info", "Here is your statement", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Dear {customer_name}, your last payment of {last_payment_amount} "
        "was received on {last_payment_date} via {last_payment_method} "
        "(Ref: {last_payment_reference}). Overdue balance: {overdue_balance}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Dear Sarah Connor" in rendered
    assert "payment of $1,450.00" in rendered
    assert "via ach" in rendered
    assert "Overdue balance: $0.00" in rendered


def test_build_tenant_rag_context_renewals_grounding():
    """Verify that lease renewal offers and status are grounded in RAG prompt context."""
    # tenant_1 has offered renewal lr_101
    t1_block = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[LEASE RENEWAL OFFERS & AGREEMENTS]" in t1_block
    assert "[lr_101] Status: OFFERED" in t1_block
    assert "Current Rent: $1,450.00 -> Proposed Rent: $1,500.00" in t1_block
    assert "Incentive: $100.00" in t1_block
    assert "[END LEASE RENEWAL OFFERS & AGREEMENTS]" in t1_block

    # tenant_3 has signed renewal lr_103
    t3_block = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[LEASE RENEWAL OFFERS & AGREEMENTS]" in t3_block
    assert "[lr_103] Status: SIGNED" in t3_block
    assert "Signed By: Eleanor Vance" in t3_block

    # include_renewals=False suppresses renewals block
    suppressed = build_tenant_rag_context(tenant_id="tenant_1", include_renewals=False)
    assert "[LEASE RENEWAL OFFERS & AGREEMENTS]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_renewal_variables():
    """Verify macro template rendering with lease renewal variables."""
    sid = "sess-macro-renewal"
    db_utils.insert_application_logs(sid, "Renewal inquiry", "Here is your offer", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Hello {customer_name}, your renewal offer ({renewal_id}) is {renewal_status}. "
        "Proposed rent: {renewal_proposed_rent} for {renewal_term_months} months. "
        "Offer expires on {renewal_expires_at}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hello Sarah Connor" in rendered
    assert "renewal offer (lr_101) is offered" in rendered
    assert "Proposed rent: $1,500.00 for 12 months" in rendered
    assert "Offer expires on 2026-10-31" in rendered


def test_build_tenant_rag_context_inspections_grounding():
    """Verify that resident move-in/out inspections and deposit settlements are grounded."""
    # tenant_2 has scheduled pre-move-out inspection insp_102
    t2_block = build_tenant_rag_context(tenant_id="tenant_2")
    assert "[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" in t2_block
    assert "[insp_102] Type: PRE-MOVE-OUT" in t2_block
    assert "Status: SCHEDULED" in t2_block
    assert "Condition: GOOD" in t2_block
    assert "Inspector: Alex Rivera" in t2_block
    assert "Keys: PENDING" in t2_block
    assert "Kitchen:Oven & Stove(clean)" in t2_block
    assert "[END RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" in t2_block

    # tenant_3 has completed move-out inspection insp_103 with deductions
    t3_block = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" in t3_block
    assert "[insp_103] Type: MOVE-OUT" in t3_block
    assert "Status: COMPLETED" in t3_block
    assert "Condition: FAIR" in t3_block
    assert "Deductions: $150.00" in t3_block
    assert "Net Refund: $1,850.00" in t3_block
    assert "Keys: RETURNED" in t3_block
    assert "Living Room:Drywall(repair)" in t3_block

    # include_inspections=False suppresses inspection block
    suppressed = build_tenant_rag_context(tenant_id="tenant_2", include_inspections=False)
    assert "[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_inspection_variables():
    """Verify macro template rendering with inspection and deposit settlement variables."""
    sid = "sess-macro-inspection"
    db_utils.insert_application_logs(sid, "Inspection inquiry", "Here is your inspection", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    template = (
        "Dear {customer_name}, inspection {inspection_id} ({inspection_type}) "
        "is {inspection_status}. Total deductions: {inspection_deposit_deductions}, "
        "net refund: {inspection_deposit_refund}, keys: {key_return_status}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Dear Elena Rostova" in rendered
    assert "inspection insp_103 (move_out) is completed" in rendered
    assert "Total deductions: $150.00" in rendered
    assert "net refund: $1,850.00" in rendered
    assert "keys: returned" in rendered


def test_build_tenant_rag_context_vendor_dispatch_grounding():
    """Verify that assigned vendor details and dispatch status are grounded in prompt context."""
    # Dispatch tenant_1's work order wo_101 to a vendor
    v = vendors.create_vendor(
        name="Apex Plumbers",
        trade="plumbing",
        phone="555-0999",
        status="active",
    )
    vendors.dispatch_vendor(
        "wo_101",
        v["id"],
        agreed_cost=185.0,
        scheduled_date="2026-11-05",
    )

    t1_block = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" in t1_block
    assert "[wo_101] Kitchen faucet leaking constantly" in t1_block
    assert "Vendor: Apex Plumbers (plumbing) [Dispatch: dispatched]" in t1_block
    assert "Vendor Phone: 555-0999" in t1_block
    assert "Scheduled: 2026-11-05" in t1_block


def test_render_template_with_vendor_dispatch_variables():
    """Verify macro template rendering with vendor dispatch variables."""
    sid = "sess-macro-vendor"
    db_utils.insert_application_logs(sid, "Plumbing help", "Vendor dispatched", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    # Create vendor and dispatch to tenant_1's work order wo_101
    v = vendors.create_vendor(
        name="QuickFix HVAC & Plumbing",
        trade="plumbing",
        phone="555-0888",
        hourly_rate=95.0,
        status="active",
    )
    vendors.dispatch_vendor(
        "wo_101",
        v["id"],
        agreed_cost=190.0,
        scheduled_date="2026-11-06",
    )

    template = (
        "Hello {customer_name}, your request '{latest_work_order_title}' has been dispatched "
        "to {vendor_name} ({vendor_trade}). Status: {vendor_dispatch_status}. "
        "Contact: {vendor_phone}, Rate: {vendor_hourly_rate}, Agreed: {vendor_agreed_cost}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hello Sarah Connor" in rendered
    assert "Kitchen faucet leaking constantly" in rendered
    assert "QuickFix HVAC & Plumbing (plumbing)" in rendered
    assert "Status: dispatched" in rendered
    assert "Contact: 555-0888" in rendered
    assert "Rate: $95.00" in rendered
    assert "Agreed: $190.00" in rendered



def test_build_tenant_rag_context_with_packages():
    """Verify package deliveries are formatted into RAG prompt context."""
    # tenant_1 has pkg_seed_01 (delivered) and pkg_seed_03 (picked_up)
    ctx = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[RESIDENT PACKAGES & PARCEL DELIVERIES]" in ctx
    assert "Pending Locker Pickups: 1" in ctx
    assert "Amazon" in ctx
    assert "TBA309481029104" in ctx
    assert "Locker Bay 1 - Slot 04" in ctx
    assert "Pickup PIN: 482019" in ctx
    assert "[END RESIDENT PACKAGES & PARCEL DELIVERIES]" in ctx

    # Test include_packages=False omits the block
    ctx_without = build_tenant_rag_context(tenant_id="tenant_1", include_packages=False)
    assert "[RESIDENT PACKAGES & PARCEL DELIVERIES]" not in ctx_without


def test_extract_tenant_macro_variables_with_packages():
    """Verify package macro variables extraction from resident packages."""
    sid = "sess-pkg-test"
    db_utils.insert_application_logs(sid, "Where is my package?", "Checking locker", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    variables = extract_tenant_macro_variables(session_id=sid)
    assert variables["pending_packages_count"] == "1"
    assert variables["package_carrier"] == "Amazon"
    assert variables["package_tracking_number"] == "TBA309481029104"
    assert variables["package_status"] == "delivered"
    assert variables["package_pickup_pin"] == "482019"
    assert variables["package_location"] == "Locker Bay 1 - Slot 04"
    assert variables["package_delivered_at"] != ""


def test_render_template_with_package_variables():
    """Verify macro template rendering with package variables."""
    sid = "sess-pkg-render"
    db_utils.insert_application_logs(sid, "Locker PIN?", "Here is your PIN", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Hi {customer_name}, you have {pending_packages_count} package(s) ready for pickup! "
        "Carrier: {package_carrier}, Tracking: {package_tracking_number}, "
        "Locker: {package_location}, Secure PIN: {package_pickup_pin}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hi Sarah Connor" in rendered
    assert "you have 1 package(s) ready for pickup!" in rendered
    assert "Carrier: Amazon" in rendered
    assert "Tracking: TBA309481029104" in rendered
    assert "Locker: Locker Bay 1 - Slot 04" in rendered
    assert "Secure PIN: 482019" in rendered





def test_tenant_context_with_amenity_reservations():
    """Verify amenity reservations prompt context grounding."""
    amenities.create_amenities_tables()
    amenities.seed_default_amenities_if_empty()

    context = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[COMMUNITY AMENITY RESERVATIONS]" in context
    assert "Grand Community Clubhouse" in context
    assert "Total Fee: $75.00" in context
    assert "[END COMMUNITY AMENITY RESERVATIONS]" in context


def test_extract_tenant_macro_variables_with_amenities():
    """Verify amenity macro variables extraction from resident bookings."""
    amenities.create_amenities_tables()
    amenities.seed_default_amenities_if_empty()

    sid = "sess-amenity-test"
    db_utils.insert_application_logs(sid, "When is my reservation?", "Checking bookings", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    variables = extract_tenant_macro_variables(session_id=sid)
    assert variables["active_reservations_count"] == "1"
    assert variables["amenity_name"] == "Grand Community Clubhouse"
    assert variables["reservation_status"] == "confirmed"
    assert variables["reservation_fee"] == "$75.00"
    assert variables["reservation_deposit"] == "$100.00"


def test_render_template_with_amenity_variables():
    """Verify macro template rendering with amenity reservation variables."""
    amenities.create_amenities_tables()
    amenities.seed_default_amenities_if_empty()

    sid = "sess-amenity-render"
    db_utils.insert_application_logs(sid, "Confirm booking", "Confirming booking", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Hi {customer_name}, your booking for {amenity_name} is {reservation_status}. "
        "Fee: {reservation_fee}, Deposit: {reservation_deposit}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hi Sarah Connor" in rendered
    assert "Grand Community Clubhouse" in rendered
    assert "confirmed" in rendered
    assert "$75.00" in rendered
    assert "$100.00" in rendered



def test_build_tenant_rag_context_with_parking():
    """Verify prompt context building includes resident vehicles and parking passes."""
    parking.register_vehicle(
        tenant_id="tenant_1",
        unit_id="unit_101",
        license_plate="7XYZ890",
        make="Toyota",
        model="RAV4",
        color="Silver",
        year=2022,
        permit_number="PERM-101A",
    )
    parking.issue_visitor_pass(
        unit_id="unit_101",
        tenant_id="tenant_1",
        visitor_name="Guest Visitor",
        vehicle_plate="GUEST999",
        start_time="2026-11-02T10:00:00Z",
        end_time="2026-11-03T10:00:00Z",
    )

    rendered = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[RESIDENT VEHICLES & PARKING PASSES]" in rendered
    assert "Assigned Parking Spot(s): P-12" in rendered
    assert "Registered Household Vehicles: 1" in rendered
    assert "[7XYZ890] Silver Toyota RAV4" in rendered
    assert "Active Visitor Passes: 1" in rendered
    assert "Guest Visitor (Plate: GUEST999)" in rendered
    assert "[END RESIDENT VEHICLES & PARKING PASSES]" in rendered


def test_extract_tenant_macro_variables_with_parking():
    """Verify macro variable extraction for parking and vehicle details."""
    parking.register_vehicle(
        tenant_id="tenant_1",
        unit_id="unit_101",
        license_plate="7XYZ890",
        make="Toyota",
        model="RAV4",
        color="Silver",
        year=2022,
        permit_number="PERM-101A",
    )
    vpass = parking.issue_visitor_pass(
        unit_id="unit_101",
        tenant_id="tenant_1",
        visitor_name="Guest Visitor",
        vehicle_plate="GUEST999",
        start_time="2026-11-02T10:00:00Z",
        end_time="2026-11-03T10:00:00Z",
    )

    sid = "sess-parking-test"
    db_utils.insert_application_logs(sid, "Where do I park?", "Checking parking spot", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    variables = extract_tenant_macro_variables(session_id=sid)
    assert variables["assigned_parking_spot"] == "P-12"
    assert variables["parking_spot"] == "P-12"
    assert variables["parking_zone"] == "Garage Level 1"
    assert variables["vehicle_plate"] == "7XYZ890"
    assert variables["vehicle_make_model"] == "Toyota RAV4"
    assert variables["permit_number"] == "PERM-101A"
    assert variables["active_visitor_pass"] == "true"
    assert variables["visitor_pass_code"] == vpass["pass_code"]


def test_render_template_with_parking_variables():
    """Verify macro template rendering with parking and vehicle variables."""
    parking.register_vehicle(
        tenant_id="tenant_1",
        unit_id="unit_101",
        license_plate="7XYZ890",
        make="Toyota",
        model="RAV4",
        permit_number="PERM-101A",
    )

    sid = "sess-parking-render"
    db_utils.insert_application_logs(sid, "Parking info", "Providing parking info", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Hello {customer_name}, your assigned parking space is "
        "{assigned_parking_spot} in {parking_zone}. "
        "Vehicle registered: {vehicle_plate} ({vehicle_make_model}), Permit: {permit_number}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hello Sarah Connor" in rendered
    assert "assigned parking space is P-12" in rendered
    assert "Garage Level 1" in rendered
    assert "Vehicle registered: 7XYZ890 (Toyota RAV4)" in rendered
    assert "Permit: PERM-101A" in rendered


def test_build_tenant_rag_context_with_pets():
    """Verify prompt context building includes resident pets and animal policies."""
    # Seed tenant_3 has Barnaby
    rendered = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[RESIDENT PETS & ANIMAL POLICIES]" in rendered
    assert "Registered Household Pets: 1" in rendered
    assert "Barnaby" in rendered
    assert "Golden Retriever Mix" in rendered
    assert "RAB-2026-8812" in rendered
    assert (
        "Community Animal Policy: Rent: $35.00/mo | Deposit: $300.00 | Max Weight: 65.0 lbs"
        in rendered
    )


def test_extract_tenant_macro_variables_with_pets():
    """Verify macro variable extraction for pet details and policy terms."""
    sid = "sess-pet-test"
    db_utils.insert_application_logs(sid, "Pet inquiry", "Checking pet registration", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    variables = extract_tenant_macro_variables(session_id=sid)
    assert variables["registered_pets_count"] == "1"
    assert variables["pet_names"] == "Barnaby"
    assert variables["primary_pet_breed"] == "Golden Retriever Mix"
    assert variables["pet_rent_monthly"] == "$35.00"
    assert variables["pet_deposit_amount"] == "$300.00"
    assert variables["service_animal_verified"] == "false"


def test_render_template_with_pet_variables():
    """Verify macro template rendering with pet registry variables."""
    sid = "sess-pet-render"
    db_utils.insert_application_logs(sid, "Pet check", "Providing pet status", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    template = (
        "Hello {customer_name}, you have {registered_pets_count} registered pet(s): "
        "{pet_names} ({primary_pet_breed}). Monthly pet fee: {pet_rent_monthly}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Elena Rostova" in rendered
    assert "1 registered pet(s): Barnaby (Golden Retriever Mix)" in rendered
    assert "Monthly pet fee: $35.00" in rendered


def test_build_tenant_rag_context_with_access_control():
    """Verify prompt context building includes access credentials, guest passes, and intercom."""
    rendered = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[RESIDENTIAL ACCESS CREDENTIALS & GUEST PASSES]" in rendered
    assert "Active Access Credentials: 2 (Key Fobs: 1, Mobile Keys: 1)" in rendered
    assert "FOB-9042" in rendered
    assert "MOB-3319" in rendered
    assert "Active Guest Passes: 1" in rendered
    assert "Paws & Walk Dog Walker (Dog Walker) | Code: 618902" in rendered
    assert "Building Callbox / Intercom: Code: PH1" in rendered
    assert "Display: Rostova, E. | Forwarding Phone: +1-555-0199 | Buzzer: ENABLED" in rendered


def test_extract_tenant_macro_variables_with_access_control():
    """Verify macro variable extraction for key fobs, guest passes, and callbox."""
    sid = "sess-access-test"
    db_utils.insert_application_logs(sid, "Access query", "Checking fob access", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    variables = extract_tenant_macro_variables(session_id=sid)
    assert variables["active_fob_count"] == "1"
    assert variables["primary_fob_number"] == "FOB-9042"
    assert variables["guest_pass_code"] == "618902"
    assert variables["intercom_code"] == "PH1"
    assert variables["fob_replacement_fee"] == "$50.00"
    assert "main_lobby" in variables["access_zones"]


def test_render_template_with_access_control_variables():
    """Verify macro template rendering with access control variables."""
    sid = "sess-access-render"
    db_utils.insert_application_logs(sid, "Fob check", "Providing fob details", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    template = (
        "Hello {customer_name}, your active key fob is {primary_fob_number} and your "
        "intercom buzzer code is #{intercom_code}. Your visitor guest code is {guest_pass_code}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Elena Rostova" in rendered
    assert "active key fob is FOB-9042" in rendered
    assert "intercom buzzer code is #PH1" in rendered
    assert "visitor guest code is 618902" in rendered


def test_build_tenant_rag_context_with_incidents():
    """Verify that build_tenant_rag_context includes incidents and violation notices."""
    context = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[RESIDENTIAL INCIDENTS & COMMUNITY VIOLATIONS]" in context
    assert "Active Violation Notices: 1" in context
    assert "Courtesy Warning: Noise Complaint" in context
    assert "Open Community Incidents: 1" in context
    assert "Incident #INC-2026-101" in context
    assert "Active Appeals: 1" in context
    assert "Appeal #APL-2026-042" in context


def test_extract_tenant_macro_variables_with_incidents():
    """Verify macro variable extraction for community violations and appeals."""
    sid = "sess-incident-test"
    db_utils.insert_application_logs(sid, "Violation query", "Checking noise notice", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    variables = extract_tenant_macro_variables(session_id=sid)
    assert variables["active_violations_count"] == "1"
    assert variables["primary_violation_type"] == "Noise Complaint"
    assert variables["notice_type"] == "Courtesy Warning"
    assert variables["violation_fine_amount"] == "$0.00"
    assert variables["cure_deadline"] == "2026-11-12"
    assert variables["appeal_status"] == "under_review"
    assert variables["active_incidents_count"] == "1"


def test_render_template_with_incident_variables():
    """Verify macro template rendering with incident and violation variables."""
    sid = "sess-incident-render"
    db_utils.insert_application_logs(sid, "Violation check", "Providing notice details", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    template = (
        "Hello {customer_name}, you have {active_violations_count} active notice "
        "({notice_type}) for {primary_violation_type} with cure deadline {cure_deadline}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Elena Rostova" in rendered
    assert "1 active notice" in rendered
    assert "Courtesy Warning" in rendered
    assert "Noise Complaint" in rendered
    assert "cure deadline 2026-11-12" in rendered



def test_build_tenant_rag_context_with_announcements():
    """Verify announcements and concierge requests in RAG context block."""
    sid = "sess-ann-rag-test"
    db_utils.insert_application_logs(sid, "Weather query", "Checking freeze notice", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    block = build_tenant_rag_context(session_id=sid)
    assert "[COMMUNITY ANNOUNCEMENTS & ACTIVE BUILDING ALERTS]" in block
    assert "Active Announcements & Alerts:" in block
    assert "Severe Cold Weather & Pipe Freeze Advisory" in block
    assert "ACKNOWLEDGED" in block
    assert "Resident Concierge Requests:" in block
    assert "Eco Cleaners garment bag" in block


def test_extract_tenant_macro_variables_with_announcements():
    """Verify macro variable extraction for announcements and concierge requests."""
    sid = "sess-ann-macro-test"
    db_utils.insert_application_logs(sid, "Alert check", "Checking active notices", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    variables = extract_tenant_macro_variables(session_id=sid)
    expected_min_ann = 2
    assert int(variables["active_announcements_count"]) >= expected_min_ann
    assert variables["active_emergency_alerts_count"] == "1"
    assert "Severe Cold Weather" in variables["latest_alert_headline"]
    assert variables["latest_alert_priority"] == "URGENT"
    assert variables["alert_acknowledgment_status"] == "acknowledged"
    assert variables["concierge_requests_count"] == "1"


def test_render_template_with_announcement_variables():
    """Verify macro template rendering with announcement and alert variables."""
    sid = "sess-ann-render"
    db_utils.insert_application_logs(sid, "Notice check", "Providing building bulletin", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    template = (
        "Dear {customer_name}, please note active alert: {latest_alert_headline} "
        "(Priority: {latest_alert_priority}, Status: {alert_acknowledgment_status})."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Elena Rostova" in rendered
    assert "Severe Cold Weather & Pipe Freeze Advisory" in rendered
    assert "URGENT" in rendered
    assert "acknowledged" in rendered



def test_build_tenant_rag_context_with_move_logistics():
    """Verify move logistics and elevator reservations appear in RAG context."""
    sid = "sess-move-context-test"
    db_utils.insert_application_logs(sid, "Move query", "Need help moving in", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")
    move_logistics.init_move_logistics_db()

    block = build_tenant_rag_context(session_id=sid)
    assert "[MOVE-IN / MOVE-OUT LOGISTICS & ELEVATOR RESERVATIONS]" in block
    assert "Scheduled Moves & Transfers:" in block
    assert "Apex Elite Moving" in block
    assert "Freight Elevator Bookings:" in block
    assert "Freight Elevator #1" in block


def test_extract_tenant_macro_variables_with_move_logistics():
    """Verify move logistics macro variables are extracted accurately."""
    sid = "sess-move-macro-test"
    db_utils.insert_application_logs(sid, "Move macros", "Checking move macros", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")
    move_logistics.init_move_logistics_db()

    variables = extract_tenant_macro_variables(session_id=sid)
    assert variables["move_logistics_type"] == "Move In"
    assert variables["move_status"] == "SCHEDULED"
    assert "Dock Bay #2" in variables["loading_dock_status"]
    assert (
        "Freight Elevator #1" in variables.get("elevator_slot", "")
        or ":" in variables.get("elevator_slot", "")
    )
    assert "%" in variables["move_checklist_progress"]


def test_render_template_with_move_logistics_variables():
    """Verify macro template rendering with move logistics variables."""
    sid = "sess-move-render"
    db_utils.insert_application_logs(sid, "Move template", "Rendering move details", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")
    move_logistics.init_move_logistics_db()

    template = (
        "Hello {customer_name}, your {move_logistics_type} is scheduled on {move_date} "
        "(Status: {move_status}, Loading Dock: {loading_dock_status})."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Elena Rostova" in rendered
    assert "Move In" in rendered
    assert "SCHEDULED" in rendered
    assert "Dock Bay #2" in rendered
