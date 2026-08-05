"""Tests for carrier gateway utilities."""
from __future__ import annotations

import pytest

from app.carriers import build_gateway_email, get_carrier, list_carriers


def test_get_carrier_verizon():
    carrier = get_carrier("verizon")
    assert carrier is not None
    assert carrier.display_name == "Verizon"
    assert carrier.sms_gateway == "vtext.com"


def test_get_carrier_case_insensitive():
    assert get_carrier("ATT") == get_carrier("att")


def test_get_carrier_unknown():
    assert get_carrier("nonexistent") is None


def test_build_gateway_email():
    result = build_gateway_email("2025551234", "att")
    assert result == "2025551234@txt.att.net"


def test_build_gateway_email_unknown_carrier():
    result = build_gateway_email("2025551234", "fakecarrier")
    assert result is None


def test_list_carriers_sorted():
    carriers = list_carriers()
    names = [c.display_name for c in carriers]
    assert names == sorted(names)


def test_all_carriers_have_sms_gateway():
    for carrier in list_carriers():
        assert carrier.sms_gateway, f"Carrier {carrier.key} missing sms_gateway"
