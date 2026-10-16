"""Every outcome has exactly one HTTP status and one CLI exit code."""

from legisqa.errors import (
    EXIT_CODE,
    HTTP_STATUS,
    AuditWriteError,
    Outcome,
    RejectionCode,
    RejectionError,
    StartupError,
    UnavailableCode,
)


def test_every_outcome_is_mapped() -> None:
    assert set(HTTP_STATUS) == set(Outcome)
    assert set(EXIT_CODE) == set(Outcome)


def test_documented_codes() -> None:
    assert HTTP_STATUS[Outcome.REJECTED] == 422
    assert HTTP_STATUS[Outcome.UNAVAILABLE] == 503
    assert EXIT_CODE[Outcome.REJECTED] == 2
    assert EXIT_CODE[Outcome.UNAVAILABLE] == 3
    assert EXIT_CODE[Outcome.ANSWERED] == EXIT_CODE[Outcome.ABSTAINED] == 0


def test_exceptions_carry_codes() -> None:
    assert RejectionError(RejectionCode.TOO_LONG, "x").code is RejectionCode.TOO_LONG
    assert StartupError("bad hash").code is UnavailableCode.NOT_READY
    assert AuditWriteError("disk full").code is UnavailableCode.AUDIT_UNAVAILABLE
