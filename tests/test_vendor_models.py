"""Tests for the vendor Pydantic request/response schemas."""

from __future__ import annotations

import pytest
from api.pydantic_models import VendorCreateRequest, VendorItem
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
