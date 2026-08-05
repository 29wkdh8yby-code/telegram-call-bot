"""Tests for phone normalization in recipient handler."""
from __future__ import annotations

import pytest


def test_normalize_phone_10_digit():
    from app.handlers.recipient_handler import _normalize_phone
    assert _normalize_phone("2025551234") == "+12025551234"


def test_normalize_phone_e164():
    from app.handlers.recipient_handler import _normalize_phone
    assert _normalize_phone("+12025551234") == "+12025551234"


def test_normalize_phone_with_dashes():
    from app.handlers.recipient_handler import _normalize_phone
    assert _normalize_phone("202-555-1234") == "+12025551234"


def test_normalize_phone_invalid():
    from app.handlers.recipient_handler import _normalize_phone
    assert _normalize_phone("123") is None
    assert _normalize_phone("not-a-number") is None


def test_phone_digits_strip_country():
    from app.handlers.recipient_handler import _phone_digits
    assert _phone_digits("+12025551234") == "2025551234"


def test_phone_digits_ten_digit():
    from app.handlers.recipient_handler import _phone_digits
    assert _phone_digits("2025551234") == "2025551234"
