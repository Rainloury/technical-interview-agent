"""JSON logging and sensitive-data redaction."""

import logging
import re
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
ID_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
SECRET_PATTERN = re.compile(
    r"(?i)\b(bearer\s+)[a-z0-9._~+/-]+=*|"
    r"((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+"
)
CREDENTIAL_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "set_cookie",
    "token",
}
CREDENTIAL_KEY_SUFFIXES = (
    "_api_key",
    "_apikey",
    "_credential",
    "_password",
    "_passwd",
    "_private_key",
    "_secret",
    "_token",
)


def redact_text(value: str) -> str:
    """Mask common sensitive values in free-form text."""

    value = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    value = PHONE_PATTERN.sub("[REDACTED_PHONE]", value)
    value = ID_PATTERN.sub("[REDACTED_ID]", value)
    return SECRET_PATTERN.sub(
        lambda match: f"{match.group(1) or match.group(2) or ''}[REDACTED]",
        value,
    )


def _is_credential_key(key: str) -> bool:
    """Distinguish credential fields from telemetry fields such as ``input_tokens``."""

    normalized = key.lower().replace("-", "_")
    return normalized in CREDENTIAL_KEYS or normalized.endswith(CREDENTIAL_KEY_SUFFIXES)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_credential_key(key) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def redact_event(
    _logger: logging.Logger, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that recursively redacts event fields."""

    return cast(MutableMapping[str, Any], _redact_value(dict(event_dict)))


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog JSON lines and route standard logging through it."""

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_event,
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a configured structured logger."""

    return structlog.stdlib.get_logger(name)
