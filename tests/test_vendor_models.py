"""Tests for the vendor Pydantic request/response schemas."""

from __future__ import annotations

import pytest
from api import db_utils, vendors
from api.pydantic_models import (
    VendorCreateRequest,
    VendorDispatchCompleteRequest,
    VendorDispatchItem,
    VendorDispatchListResponse,
    VendorDispatchRequest,
    VendorDispatchResponse,
    VendorItem,
    VendorListResponse,
    VendorMetricsResponse,
    VendorResponse,
    VendorUpdateRequest,
)
from pydantic import ValidationError


def test_vendor_create_request_normalizes_fields():
    req = VendorCreateRequest(id=" vnd_x ", name="  Acme  ", trade="HVAC", status="Inactive")
    assert req.id == "vnd_x"
    assert req.name == "Acme"
    assert req.trade == "hvac"
    assert req.status == "inactive"


def test_vendor_create_request_defaults_and_rejections():
    req = VendorCreateRequest(name="Acme")
    assert req.id is None
    assert req.trade == "general"
    assert req.status == "active"
    assert req.hourly_rate is None
    with pytest.raises(ValidationError):
        VendorCreateRequest(name="")
    with pytest.raises(ValidationError):
        VendorCreateRequest(name="Acme", trade="astrology")
    with pytest.raises(ValidationError):
        VendorCreateRequest(name="Acme", status="retired")
    with pytest.raises(ValidationError):
        VendorCreateRequest(name="Acme", hourly_rate=-1)
    with pytest.raises(ValidationError):
        VendorCreateRequest(name="Acme", id="bad id!")


def test_vendor_item_defaults():
    item = VendorItem(id="vnd_1", name="Acme")
    assert item.trade == "general"
    assert item.hourly_rate is None


def test_vendor_update_request_partial_and_validation():
    req = VendorUpdateRequest(trade=" Plumbing ", status="Inactive")
    assert req.trade == "plumbing"
    assert req.status == "inactive"
    assert req.name is None
    assert VendorUpdateRequest().model_dump(exclude_none=True) == {}
    with pytest.raises(ValidationError):
        VendorUpdateRequest(name=" ")
    with pytest.raises(ValidationError):
        VendorUpdateRequest(trade="astrology")
    with pytest.raises(ValidationError):
        VendorUpdateRequest(status="retired")


def test_vendor_response_wrappers():
    resp = VendorResponse(vendor=VendorItem(id="vnd_1", name="Acme"))
    assert resp.vendor.id == "vnd_1"
    listing = VendorListResponse(items=[resp.vendor], total=1)
    assert listing.limit == 50  # noqa: PLR2004
    assert listing.offset == 0


def test_vendor_dispatch_request_validation():
    req = VendorDispatchRequest(vendor_id="vnd_1", agreed_cost=120, scheduled_date="2026-11-03")
    assert req.agreed_cost == 120.0  # noqa: PLR2004
    with pytest.raises(ValidationError):
        VendorDispatchRequest(vendor_id="")
    with pytest.raises(ValidationError):
        VendorDispatchRequest(vendor_id="vnd_1", agreed_cost=-1)


def test_vendor_dispatch_complete_request_rating_bounds():
    assert VendorDispatchCompleteRequest(rating=1).rating == 1
    assert VendorDispatchCompleteRequest(rating=5).rating == 5  # noqa: PLR2004
    assert VendorDispatchCompleteRequest().rating is None
    with pytest.raises(ValidationError):
        VendorDispatchCompleteRequest(rating=0)
    with pytest.raises(ValidationError):
        VendorDispatchCompleteRequest(rating=6)
    with pytest.raises(ValidationError):
        VendorDispatchCompleteRequest(final_cost=-0.01)


def test_vendor_dispatch_response_wrappers():
    item = VendorDispatchItem(
        id="vdp_1", vendor_id="vnd_1", work_order_id="wo_1", dispatched_at="2026-10-21T00:00:00"
    )
    assert item.status == "dispatched"
    assert VendorDispatchResponse(dispatch=item).dispatch.id == "vdp_1"
    assert VendorDispatchListResponse(items=[item], total=1).total == 1


def test_vendor_metrics_response_accepts_engine_output(monkeypatch, tmp_path):
    monkeypatch.setattr(db_utils, "DB_NAME", str(tmp_path / "metrics.db"))
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_work_orders()
    vendors.create_vendors()
    metrics = VendorMetricsResponse(**vendors.get_vendor_summary_metrics())
    assert metrics.total_vendors == 3  # noqa: PLR2004
    assert len(metrics.vendors) == 3  # noqa: PLR2004
    assert metrics.average_rating is None
    assert VendorMetricsResponse().vendors == []
