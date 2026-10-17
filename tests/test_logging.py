"""Structured logging redaction tests."""

from app.logging import _redact_value, redact_text


def test_redact_text_masks_known_sensitive_patterns() -> None:
    text = (
        "mail alice@example.com phone 13800138000 id 11010519491231002X "
        "Authorization: Bearer abc.def token=secret-value"
    )

    redacted = redact_text(text)

    for secret in ("alice@example.com", "13800138000", "11010519491231002X", "abc.def"):
        assert secret not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_ID]" in redacted


def test_nested_keys_and_values_are_redacted() -> None:
    payload = {
        "request_id": "req_1",
        "password": "plain",
        "nested": {
            "api_key": "key",
            "email": "alice@example.com",
            "items": ["token=abc", {"smtp_secret": "s"}],
        },
    }

    redacted = _redact_value(payload)

    assert redacted["password"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["email"] == "[REDACTED_EMAIL]"
    assert redacted["nested"]["items"][1]["smtp_secret"] == "[REDACTED]"


def test_token_usage_fields_are_preserved() -> None:
    redacted = _redact_value(
        {
            "input_tokens": 120,
            "output_tokens": 30,
            "max_tokens": 8192,
            "token_count": 150,
            "access_token": "secret-access-token",
            "token": "secret-token",
        }
    )

    assert redacted["input_tokens"] == 120
    assert redacted["output_tokens"] == 30
    assert redacted["max_tokens"] == 8192
    assert redacted["token_count"] == 150
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
