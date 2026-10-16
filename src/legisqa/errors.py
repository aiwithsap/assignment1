"""The request outcome contract and the exceptions that produce non-answer outcomes.

Every request ends in exactly one ``Outcome``. Each outcome has a fixed HTTP status and
CLI exit code so the API, CLI, UI, tests and reports agree on what happened.
"""

from enum import StrEnum


class Outcome(StrEnum):
    ANSWERED = "answered"
    ABSTAINED = "abstained"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    INTERNAL_ERROR = "internal_error"


HTTP_STATUS: dict[Outcome, int] = {
    Outcome.ANSWERED: 200,
    Outcome.ABSTAINED: 200,
    Outcome.REJECTED: 422,
    Outcome.UNAVAILABLE: 503,
    Outcome.INTERNAL_ERROR: 500,
}

EXIT_CODE: dict[Outcome, int] = {
    Outcome.ANSWERED: 0,
    Outcome.ABSTAINED: 0,
    Outcome.INTERNAL_ERROR: 1,
    Outcome.REJECTED: 2,
    Outcome.UNAVAILABLE: 3,
}


class RejectionCode(StrEnum):
    """Why an input was refused before any retrieval took place."""

    INVALID_REQUEST = "invalid_request"
    EMPTY = "empty"
    TOO_LONG = "too_long"
    PII_DETECTED = "pii_detected"
    ACTIVE_CONTENT = "active_content"


class UnavailableCode(StrEnum):
    """Why the service cannot answer at all right now."""

    NOT_READY = "not_ready"
    AUDIT_UNAVAILABLE = "audit_unavailable"


class LegisQAError(Exception):
    """Base class for expected, contract-level failures."""


class RejectionError(LegisQAError):
    """The input was refused. Maps to HTTP 422 and CLI exit code 2."""

    def __init__(self, code: RejectionCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UnavailableError(LegisQAError):
    """The service cannot answer. Maps to HTTP 503 and CLI exit code 3."""

    def __init__(self, code: UnavailableCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StartupError(UnavailableError):
    """Corpus or manifest could not be loaded or verified; the service stays unready."""

    def __init__(self, message: str) -> None:
        super().__init__(UnavailableCode.NOT_READY, message)


class AuditWriteError(UnavailableError):
    """The audit record could not be written, so the response must be withheld."""

    def __init__(self, message: str) -> None:
        super().__init__(UnavailableCode.AUDIT_UNAVAILABLE, message)
