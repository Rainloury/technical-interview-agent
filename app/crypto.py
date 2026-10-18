"""Standard-library authenticated encryption for short-lived delivery secrets."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os

from app.config import Settings

_NONCE_BYTES = 16
_TAG_BYTES = 32


def _keys(settings: Settings) -> tuple[bytes, bytes]:
    configured = settings.data_encryption_key
    if configured is None:
        raise ValueError("DATA_ENCRYPTION_KEY is required for encrypted delivery")
    try:
        master = base64.urlsafe_b64decode(configured.get_secret_value())
    except (ValueError, binascii.Error) as exc:
        raise ValueError("DATA_ENCRYPTION_KEY must be base64 encoded") from exc
    if len(master) != 32:
        raise ValueError("DATA_ENCRYPTION_KEY must decode to 32 bytes")
    encryption_key = hmac.new(master, b"technical-interview-agent:encrypt", hashlib.sha256).digest()
    mac_key = hmac.new(master, b"technical-interview-agent:mac", hashlib.sha256).digest()
    return encryption_key, mac_key


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = (length + hashlib.sha256().digest_size - 1) // hashlib.sha256().digest_size
    output = bytearray()
    for counter in range(blocks):
        output.extend(
            hmac.new(
                key,
                nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
    return bytes(output[:length])


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    """Encrypt a short secret with a random nonce and HMAC-SHA256 tag."""

    encryption_key, mac_key = _keys(settings)
    nonce = os.urandom(_NONCE_BYTES)
    plaintext_bytes = plaintext.encode("utf-8")
    stream = _stream(encryption_key, nonce, len(plaintext_bytes))
    ciphertext = bytes(left ^ right for left, right in zip(plaintext_bytes, stream, strict=True))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")


def decrypt_secret(settings: Settings, value: str) -> str:
    """Verify and decrypt a value produced by ``encrypt_secret``."""

    encryption_key, mac_key = _keys(settings)
    try:
        packed = base64.urlsafe_b64decode(value)
        nonce = packed[:_NONCE_BYTES]
        ciphertext = packed[_NONCE_BYTES:-_TAG_BYTES]
        tag = packed[-_TAG_BYTES:]
        expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if len(packed) <= _NONCE_BYTES + _TAG_BYTES or not hmac.compare_digest(tag, expected):
            raise ValueError("integrity check failed")
        stream = _stream(encryption_key, nonce, len(ciphertext))
        plaintext = bytes(left ^ right for left, right in zip(ciphertext, stream, strict=True))
        return plaintext.decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("encrypted delivery value is invalid") from exc
