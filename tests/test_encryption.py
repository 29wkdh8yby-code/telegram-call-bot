"""Tests for encryption utilities."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet


def _setup_encryption(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake:token")
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "123")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///test.db")
    # Reset lru_cache on Settings and Fernet singleton
    from app import config as cfg_module
    cfg_module.get_settings.cache_clear()
    import app.encryption as enc_module
    enc_module._fernet = None
    return key


def test_encrypt_decrypt_roundtrip(monkeypatch):
    _setup_encryption(monkeypatch)
    from app.encryption import decrypt, encrypt

    plaintext = "super-secret-password"
    token = encrypt(plaintext)
    assert token != plaintext
    assert decrypt(token) == plaintext


def test_encrypt_produces_different_tokens(monkeypatch):
    _setup_encryption(monkeypatch)
    from app.encryption import encrypt

    t1 = encrypt("password")
    t2 = encrypt("password")
    # Fernet uses random IV so tokens should differ
    assert t1 != t2
