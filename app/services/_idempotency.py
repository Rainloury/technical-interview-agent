"""service 层幂等键与请求指纹的共享算法。"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def operation_key(operation: str, owner_id: uuid.UUID, client_key: str) -> str:
    """哈希所有幂等材料,不逐字存储调用方标识符。"""

    return sha256_text(f"{operation}\0{owner_id.hex}\0{client_key}")


def stable_json_fingerprint(value: dict[str, Any] | Any) -> str:
    """按键排序的紧凑 JSON 指纹,用于请求体重放校验。"""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
