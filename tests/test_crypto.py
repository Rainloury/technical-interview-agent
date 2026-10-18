"""Delivery-secret encryption and tamper-detection tests."""

from __future__ import annotations

import base64
import os

import pytest
from app.config import Settings
from app.crypto import decrypt_secret, encrypt_secret


def _settings() -> Settings:
    return Settings(
        app_env="test",
        data_encryption_key=base64.urlsafe_b64encode(os.urandom(32)).decode(),
        _env_file=None,
    )


def test_delivery_ciphertext_round_trips_and_does_not_contain_plaintext() -> None:
    settings = _settings()

    ciphertext = encrypt_secret(settings, "user@example.com\0super-secret-token")

    assert "user@example.com" not in ciphertext
    assert "super-secret-token" not in ciphertext
    assert decrypt_secret(settings, ciphertext) == "user@example.com\0super-secret-token"


def test_delivery_ciphertext_rejects_tampering_and_missing_key() -> None:
    settings = _settings()
    ciphertext = encrypt_secret(settings, "user@example.com\0token")
    tampered = ciphertext[:-2] + ("AA" if not ciphertext.endswith("AA") else "BB")

    with pytest.raises(ValueError, match="invalid"):
        decrypt_secret(settings, tampered)
    with pytest.raises(ValueError, match="DATA_ENCRYPTION_KEY"):
        encrypt_secret(Settings(app_env="test", _env_file=None), "value")
