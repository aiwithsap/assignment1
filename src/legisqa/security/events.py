"""Security events: what was detected, where, and what was done about it.

Redaction rules: events about corpus content keep the matched span truncated to 80
characters (the corpus is public, truncation limits re-display of payloads). Events about
user questions or responses never store text, only offsets and a fingerprint.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, ConfigDict

from legisqa.logging_setup import fingerprint
from legisqa.security.detectors import Finding

MAX_MATCHED_CHARS = 80

log = logging.getLogger("legisqa.security")


class EventSource(StrEnum):
    CORPUS = "corpus"
    QUESTION = "question"
    RESPONSE = "response"


class EventAction(StrEnum):
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    LOGGED = "logged"
    ABSTAINED = "abstained"


class SecurityEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    ts: str
    source: EventSource
    action: EventAction
    detector: str
    severity: str
    rule: str
    span: tuple[int, int]
    chunk_id: str | None = None
    request_id: str | None = None
    matched_text: str | None = None
    matched_sha256_16: str


def make_event(
    finding: Finding,
    source: EventSource,
    action: EventAction,
    *,
    chunk_id: str | None = None,
    request_id: str | None = None,
) -> SecurityEvent:
    keep_text = source is EventSource.CORPUS
    return SecurityEvent(
        event_id="se_" + uuid.uuid4().hex[:12],
        ts=datetime.now(tz=UTC).isoformat(),
        source=source,
        action=action,
        detector=finding.detector.value,
        severity=finding.severity.name,
        rule=finding.rule,
        span=(finding.start, finding.end),
        chunk_id=chunk_id,
        request_id=request_id,
        matched_text=finding.matched[:MAX_MATCHED_CHARS] if keep_text else None,
        matched_sha256_16=fingerprint(finding.matched),
    )


class EventStore:
    """In-memory event list, optionally mirrored to an append-only JSONL file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._events: list[SecurityEvent] = []
        self._lock = Lock()

    def add(self, event: SecurityEvent) -> SecurityEvent:
        with self._lock:
            self._events.append(event)
            if self._path is not None:
                # The JSONL mirror is best-effort; the answer audit log is the fail-closed control.
                try:
                    self._path.parent.mkdir(parents=True, exist_ok=True)
                    with self._path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(event.model_dump(mode="json")) + "\n")
                except OSError:
                    log.error("security event file not writable; event kept in memory")
        return event

    def all(self) -> tuple[SecurityEvent, ...]:
        with self._lock:
            return tuple(self._events)
