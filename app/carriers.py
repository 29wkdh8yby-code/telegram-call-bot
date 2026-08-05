"""
Carrier SMS gateway configuration.

Each entry maps a carrier key to its human-readable name and
the SMTP-to-SMS email gateway domain.

Format: phone_number@gateway_domain

This file is the single place to update when carriers change their gateways.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class CarrierGateway:
    key: str
    display_name: str
    sms_gateway: str          # domain for SMS
    mms_gateway: str | None   # domain for MMS (optional)


# ---------------------------------------------------------------------------
# Carrier registry
# ---------------------------------------------------------------------------

CARRIERS: Dict[str, CarrierGateway] = {
    "verizon": CarrierGateway(
        key="verizon",
        display_name="Verizon",
        sms_gateway="vtext.com",
        mms_gateway="vzwpix.com",
    ),
    "att": CarrierGateway(
        key="att",
        display_name="AT&T",
        sms_gateway="txt.att.net",
        mms_gateway="mms.att.net",
    ),
    "tmobile": CarrierGateway(
        key="tmobile",
        display_name="T-Mobile",
        sms_gateway="tmomail.net",
        mms_gateway="tmomail.net",
    ),
    "metro": CarrierGateway(
        key="metro",
        display_name="Metro by T-Mobile",
        sms_gateway="mymetropcs.com",
        mms_gateway="mymetropcs.com",
    ),
    "boost": CarrierGateway(
        key="boost",
        display_name="Boost Mobile",
        sms_gateway="sms.myboostmobile.com",
        mms_gateway="myboostmobile.com",
    ),
    "cricket": CarrierGateway(
        key="cricket",
        display_name="Cricket Wireless",
        sms_gateway="sms.cricketwireless.net",
        mms_gateway="mms.cricketwireless.net",
    ),
    "uscellular": CarrierGateway(
        key="uscellular",
        display_name="US Cellular",
        sms_gateway="email.uscc.net",
        mms_gateway="mms.uscc.net",
    ),
    "consumer": CarrierGateway(
        key="consumer",
        display_name="Consumer Cellular",
        sms_gateway="mailmymobile.net",
        mms_gateway=None,
    ),
    "googlefi": CarrierGateway(
        key="googlefi",
        display_name="Google Fi",
        sms_gateway="msg.fi.google.com",
        mms_gateway="msg.fi.google.com",
    ),
    "sprint": CarrierGateway(
        key="sprint",
        display_name="Sprint (now T-Mobile)",
        sms_gateway="messaging.sprintpcs.com",
        mms_gateway="pm.sprint.com",
    ),
    "tracfone": CarrierGateway(
        key="tracfone",
        display_name="Tracfone",
        sms_gateway="mmst5.tracfone.com",
        mms_gateway=None,
    ),
    "straighttalk": CarrierGateway(
        key="straighttalk",
        display_name="Straight Talk",
        sms_gateway="vtext.com",
        mms_gateway=None,
    ),
    "virgin": CarrierGateway(
        key="virgin",
        display_name="Virgin Mobile",
        sms_gateway="vmobl.com",
        mms_gateway="vmpix.com",
    ),
}


def get_carrier(key: str) -> CarrierGateway | None:
    """Return a carrier by key (case-insensitive)."""
    return CARRIERS.get(key.lower())


def build_gateway_email(phone_digits: str, carrier_key: str) -> str | None:
    """
    Build the SMTP-to-SMS gateway email address.

    phone_digits: 10-digit US number with no formatting, e.g. '2025551234'
    carrier_key:  key from CARRIERS dict
    """
    carrier = get_carrier(carrier_key)
    if carrier is None:
        return None
    return f"{phone_digits}@{carrier.sms_gateway}"


def list_carriers() -> list[CarrierGateway]:
    """Return all carriers sorted by display name."""
    return sorted(CARRIERS.values(), key=lambda c: c.display_name)
