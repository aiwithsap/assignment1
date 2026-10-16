"""Structured JSON logging with a request-id context and mandatory redaction.

Question text is never written to logs. Fields that may hold user or document text are
replaced by a length and a short SHA-256 fingerprint before any handler sees them.
"""

import hashlib
import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REDACTED_FIELDS = frozenset({"question", "raw_text", "matched_text"})

# Attributes every LogRecord has; anything else was passed through ``extra=``.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def fingerprint(text: str) -> str:
    """Stable, non-reversible identifier for a piece of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def redacted(text: str) -> dict[str, int | str]:
    return {"len": len(text), "sha256_16": fingerprint(text)}


class RedactingFilter(logging.Filter):
    """Replace sensitive ``extra`` fields with a fingerprint before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name in REDACTED_FIELDS:
            value = getattr(record, name, None)
            if isinstance(value, str):
                setattr(record, name, redacted(value))
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, including any ``extra`` fields and the request id."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class JsonStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Stream handler pre-wired with the JSON formatter and the redaction filter."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.addFilter(RedactingFilter())


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, JsonStreamHandler):
            root.removeHandler(handler)
    root.addHandler(JsonStreamHandler())
    root.setLevel(level)
