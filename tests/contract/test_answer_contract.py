"""Contract tests: impossible answer/abstention states cannot be constructed."""

import pytest
from pydantic import ValidationError

from legisqa.errors import Outcome
from legisqa.models import (
    AbstainReason,
    AnswerResponse,
    AnswerStatus,
    Citation,
    ErrorEnvelope,
    GroundedAnswer,
)

QUOTE = "The Minister may, by legislative instrument, make rules prescribing matters."
CITATION = Citation(chunk_id="c_0123456789ab", quote=QUOTE)


def test_answered_with_citation_is_valid() -> None:
    answer = GroundedAnswer.answered(QUOTE, (CITATION,))
    assert answer.status is AnswerStatus.ANSWERED
    assert answer.abstain_reason is None


def test_abstention_with_reason_is_valid() -> None:
    answer = GroundedAnswer.abstained(AbstainReason.LOW_EVIDENCE)
    assert answer.answer is None
    assert answer.citations == ()


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "answered", "answer": QUOTE, "citations": ()},  # no citations
        {"status": "answered", "answer": "   ", "citations": (CITATION,)},  # blank answer
        {"status": "answered", "answer": None, "citations": (CITATION,)},  # missing answer
        {
            "status": "answered",
            "answer": QUOTE,
            "citations": (CITATION,),
            "abstain_reason": "low_evidence",
        },
        {"status": "abstained"},  # no reason
        {"status": "abstained", "abstain_reason": "ungrounded", "answer": QUOTE},
        {"status": "abstained", "abstain_reason": "ungrounded", "citations": (CITATION,)},
        {"status": "abstained", "abstain_reason": "pii_detected"},  # rejection code, not a reason
    ],
)
def test_impossible_states_are_rejected(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GroundedAnswer.model_validate(fields)


@pytest.mark.parametrize(
    ("chunk_id", "quote"),
    [
        ("c_0123456789ab", "too short"),
        ("chunk-1", QUOTE),
        ("c_0123456789AB", QUOTE),
        ("adv_xyz", QUOTE),
    ],
)
def test_citation_constraints(chunk_id: str, quote: str) -> None:
    with pytest.raises(ValidationError):
        Citation(chunk_id=chunk_id, quote=quote)


def test_adversarial_chunk_ids_are_distinct_namespace() -> None:
    assert Citation(chunk_id="adv_0123456789ab", quote=QUOTE).chunk_id.startswith("adv_")


def test_response_outcome_must_match_status() -> None:
    abstained = GroundedAnswer.abstained(AbstainReason.UNSAFE_OUTPUT)
    with pytest.raises(ValidationError):
        AnswerResponse(
            request_id="r1",
            outcome=Outcome.ANSWERED,
            corpus_version="v1",
            result=abstained,
            latency_ms=1.0,
        )
    ok = AnswerResponse(
        request_id="r1",
        outcome=Outcome.ABSTAINED,
        corpus_version="v1",
        result=abstained,
        latency_ms=1.0,
    )
    assert ok.notice.endswith("Not legal advice.")


@pytest.mark.parametrize(
    ("outcome", "code", "valid"),
    [
        (Outcome.REJECTED, "pii_detected", True),
        (Outcome.REJECTED, "not_ready", False),
        (Outcome.REJECTED, None, False),
        (Outcome.UNAVAILABLE, "audit_unavailable", True),
        (Outcome.UNAVAILABLE, "too_long", False),
        (Outcome.INTERNAL_ERROR, None, True),
        (Outcome.INTERNAL_ERROR, "empty", False),
    ],
)
def test_error_envelope_codes(outcome: Outcome, code: str | None, valid: bool) -> None:
    def build() -> ErrorEnvelope:
        return ErrorEnvelope.model_validate(
            {"request_id": "r1", "outcome": outcome, "code": code, "message": "m"}
        )

    if valid:
        assert build().outcome is outcome
    else:
        with pytest.raises(ValidationError):
            build()


def test_error_envelope_rejects_answer_outcomes() -> None:
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(
            {"request_id": "r1", "outcome": "answered", "code": None, "message": "m"}
        )
