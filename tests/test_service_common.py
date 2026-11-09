"""service 层公共模块的确定性单测。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.errors import AppError
from app.services._idempotency import operation_key, sha256_text, stable_json_fingerprint
from app.services._pagination import Cursor, cursor_condition, decode_cursor, encode_cursor


def test_operation_key_is_stable_and_owner_scoped() -> None:
    owner = uuid.UUID(int=1)
    other = uuid.UUID(int=2)
    assert operation_key("upload", owner, "key") == sha256_text(f"upload\0{owner.hex}\0key")
    assert operation_key("upload", owner, "key") != operation_key("upload", other, "key")
    assert operation_key("upload", owner, "key") != operation_key("delete", owner, "key")


def test_stable_json_fingerprint_ignores_key_order() -> None:
    assert stable_json_fingerprint({"a": 1, "b": 2}) == stable_json_fingerprint({"b": 2, "a": 1})
    assert stable_json_fingerprint({"a": 1}) != stable_json_fingerprint({"a": 2})


def test_cursor_round_trip_preserves_timestamp_and_id() -> None:
    cursor = Cursor(timestamp=datetime(2026, 11, 9, 8, 30, tzinfo=UTC), id=uuid.UUID(int=7))
    encoded = encode_cursor(cursor)
    decoded = decode_cursor(encoded)
    assert decoded.timestamp == cursor.timestamp
    assert decoded.id == cursor.id


def test_cursor_round_trip_supports_updated_at_field() -> None:
    cursor = Cursor(timestamp=datetime(2026, 11, 9, 8, 30, tzinfo=UTC), id=uuid.UUID(int=7))
    encoded = encode_cursor(cursor, field="updated_at")
    decoded = decode_cursor(encoded, field="updated_at")
    assert decoded.timestamp == cursor.timestamp
    assert decoded.id == cursor.id
    with pytest.raises(AppError):
        decode_cursor(encoded)


def test_cursor_rejects_malformed_payload() -> None:
    with pytest.raises(AppError) as exc_info:
        decode_cursor("not-a-cursor")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_request"


def test_cursor_condition_is_true_without_cursor() -> None:
    condition = cursor_condition(object(), object(), None)
    assert str(condition) == "true"
