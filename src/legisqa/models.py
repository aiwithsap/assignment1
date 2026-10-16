"""Pydantic schemas shared by the service, API, CLI, evaluation and frontend types.

Cross-field invariants live here so that impossible states cannot be constructed:
an answer always carries citations, and an abstention never carries an answer.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from legisqa.errors import Outcome, RejectionCode, UnavailableCode

CHUNK_ID_PATTERN = r"^(c|adv)_[0-9a-f]{12}$"
ChunkId = Annotated[str, StringConstraints(pattern=CHUNK_ID_PATTERN)]

MIN_QUOTE_CHARS = 20

NOT_LEGAL_ADVICE = (
    "Evidence excerpts from public legislation, provided for research. Not legal advice."
)


class Jurisdiction(StrEnum):
    COMMONWEALTH = "commonwealth"
    NEW_SOUTH_WALES = "new_south_wales"
    QUEENSLAND = "queensland"
    WESTERN_AUSTRALIA = "western_australia"
    SOUTH_AUSTRALIA = "south_australia"
    TASMANIA = "tasmania"
    NORFOLK_ISLAND = "norfolk_island"


class DocType(StrEnum):
    PRIMARY_LEGISLATION = "primary_legislation"
    SECONDARY_LEGISLATION = "secondary_legislation"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Chunk(_Frozen):
    """One retrievable passage of legislation.

    The record deliberately carries no evaluation labels: whether a chunk is part of the
    adversarial test overlay is held in a separate label file the detectors never read.
    """

    chunk_id: ChunkId
    version_id: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    jurisdiction: Jurisdiction
    doc_type: DocType
    url: str = Field(pattern=r"^https://")
    text: str = Field(min_length=1)


class Citation(_Frozen):
    chunk_id: ChunkId
    quote: str = Field(min_length=MIN_QUOTE_CHARS, max_length=4000)


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    ABSTAINED = "abstained"


class AbstainReason(StrEnum):
    LOW_EVIDENCE = "low_evidence"
    UNGROUNDED = "ungrounded"
    UNSAFE_OUTPUT = "unsafe_output"


class GroundedAnswer(_Frozen):
    """An evidence excerpt with citations, or a reasoned abstention. Never both."""

    status: AnswerStatus
    answer: str | None = None
    citations: tuple[Citation, ...] = ()
    abstain_reason: AbstainReason | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.status is AnswerStatus.ANSWERED:
            if not self.answer or not self.answer.strip():
                raise ValueError("an answered response needs non-empty answer text")
            if not self.citations:
                raise ValueError("an answered response needs at least one citation")
            if self.abstain_reason is not None:
                raise ValueError("an answered response cannot carry an abstain reason")
        else:
            if self.abstain_reason is None:
                raise ValueError("an abstention needs an abstain reason")
            if self.answer is not None:
                raise ValueError("an abstention cannot carry answer text")
            if self.citations:
                raise ValueError("an abstention cannot carry citations")
        return self

    @classmethod
    def answered(cls, answer: str, citations: tuple[Citation, ...]) -> "GroundedAnswer":
        return cls(status=AnswerStatus.ANSWERED, answer=answer, citations=citations)

    @classmethod
    def abstained(cls, reason: AbstainReason) -> "GroundedAnswer":
        return cls(status=AnswerStatus.ABSTAINED, abstain_reason=reason)


class Hit(_Frozen):
    chunk_id: ChunkId
    score: float = Field(ge=0.0)
    top_terms: tuple[str, ...] = ()


class AskRequest(_Frozen):
    # Hard ceiling against oversized bodies; the configurable limit is enforced by the guard
    # so that it produces a ``too_long`` rejection rather than a schema error.
    question: str = Field(max_length=20_000)
    jurisdiction: Jurisdiction | None = None


class AnswerResponse(_Frozen):
    request_id: str = Field(min_length=1)
    outcome: Literal[Outcome.ANSWERED, Outcome.ABSTAINED]
    corpus_version: str = Field(min_length=1)
    result: GroundedAnswer
    retrieved: tuple[Hit, ...] = ()
    security_event_ids: tuple[str, ...] = ()
    latency_ms: float = Field(ge=0.0)
    notice: str = NOT_LEGAL_ADVICE

    @model_validator(mode="after")
    def _outcome_matches_status(self) -> Self:
        expected = (
            Outcome.ANSWERED if self.result.status is AnswerStatus.ANSWERED else Outcome.ABSTAINED
        )
        if self.outcome is not expected:
            raise ValueError("outcome must match the result status")
        return self


class ErrorEnvelope(_Frozen):
    """Body for every non-answer outcome (HTTP 422, 503 and 500)."""

    request_id: str = Field(min_length=1)
    outcome: Literal[Outcome.REJECTED, Outcome.UNAVAILABLE, Outcome.INTERNAL_ERROR]
    code: str | None = None
    message: str

    @model_validator(mode="after")
    def _code_matches_outcome(self) -> Self:
        allowed: dict[Outcome, set[str]] = {
            Outcome.REJECTED: {c.value for c in RejectionCode},
            Outcome.UNAVAILABLE: {c.value for c in UnavailableCode},
        }
        if self.outcome is Outcome.INTERNAL_ERROR:
            if self.code is not None:
                raise ValueError("internal errors carry no code")
        elif self.code not in allowed[self.outcome]:
            raise ValueError(f"code {self.code!r} is not valid for outcome {self.outcome}")
        return self
