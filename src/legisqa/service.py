"""Request orchestration: guard -> retrieve -> gate -> answer -> validate -> guard -> audit.

The service always ends a request in exactly one contract outcome. If the corpus failed
to load or verify, the service still constructs but stays *unready* and refuses to answer.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from legisqa.answerers.base import Answerer
from legisqa.answerers.extractive import ExtractiveAnswerer
from legisqa.audit import AuditLog
from legisqa.citations import CitationFailure, validate_citations
from legisqa.config import Settings
from legisqa.corpus import Corpus, IngestPolicy, load_corpus
from legisqa.errors import (
    Outcome,
    RejectionError,
    StartupError,
    UnavailableCode,
    UnavailableError,
)
from legisqa.gate import decide
from legisqa.guards import check_question
from legisqa.logging_setup import fingerprint, request_id_var
from legisqa.models import AbstainReason, AnswerResponse, GroundedAnswer, Jurisdiction
from legisqa.output_guard import check_output
from legisqa.retrieval import Retriever, SearchResult
from legisqa.security.detectors import Finding
from legisqa.security.events import EventAction, EventSource, EventStore, make_event

log = logging.getLogger("legisqa.service")

# Readiness warning: more clean-namespace chunks quarantined than this suggests a poisoned
# corpus release rather than isolated false positives.
MAX_EXPECTED_CLEAN_QUARANTINE = 8


@dataclass(frozen=True)
class PipelineResult:
    search: SearchResult
    gate_passed: bool
    answer: GroundedAnswer
    citation_failure: CitationFailure | None = None
    output_findings: tuple[Finding, ...] = ()


def run_pipeline(
    question: str,
    *,
    corpus: Corpus,
    retriever: Retriever,
    answerer: Answerer,
    settings: Settings,
    output_guard: bool = True,
    jurisdiction: Jurisdiction | None = None,
) -> PipelineResult:
    """Retrieve, gate, answer, validate citations and guard the output. Pure: no I/O.

    Shared by the service and the evaluation harness, so evaluation measures exactly the
    code path that serves requests.
    """
    search = retriever.search(question, k=settings.top_k, jurisdiction=jurisdiction)
    gate = decide(search, settings.gate_min_strength, settings.gate_min_margin)
    abstain_low = GroundedAnswer.abstained(AbstainReason.LOW_EVIDENCE)
    if not gate.passed:
        return PipelineResult(search, False, abstain_low)
    candidate = answerer.answer(question, search.hits, corpus)
    if candidate is None:
        return PipelineResult(search, True, abstain_low)
    failure = validate_citations(candidate, corpus, {h.chunk_id for h in search.hits})
    if failure is not None:
        return PipelineResult(
            search, True, GroundedAnswer.abstained(AbstainReason.UNGROUNDED), failure
        )
    if output_guard and candidate.answer is not None:
        findings = tuple(check_output(candidate.answer))
        if findings:
            unsafe = GroundedAnswer.abstained(AbstainReason.UNSAFE_OUTPUT)
            return PipelineResult(search, True, unsafe, output_findings=findings)
    return PipelineResult(search, True, candidate)


@dataclass(frozen=True)
class Defences:
    """Defence layers. All on in normal operation; switched off only for ablations."""

    ingest: IngestPolicy = field(default_factory=IngestPolicy)
    output_guard: bool = True


@dataclass(frozen=True)
class Readiness:
    ready: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


class AnswerService:
    def __init__(
        self,
        settings: Settings,
        *,
        defences: Defences | None = None,
        answerer: Answerer | None = None,
    ) -> None:
        self.settings = settings
        self.defences = defences or Defences()
        self.events = EventStore(settings.var_dir / "audit" / "security.jsonl")
        self.audit = AuditLog(settings.var_dir / "audit" / "answers.jsonl")
        self.corpus: Corpus | None = None
        self.retriever: Retriever | None = None
        self.startup_error: str | None = None
        try:
            self.corpus = load_corpus(
                settings.data_dir,
                include_overlay=settings.load_adversarial_overlay,
                policy=self.defences.ingest,
                events=self.events,
            )
            self.retriever = Retriever(self.corpus.clean.values())
        except StartupError as exc:
            self.startup_error = exc.message
            log.error("startup failed; service is unready", extra={"reason": exc.message})
        self.answerer: Answerer | None = answerer or (
            ExtractiveAnswerer(self.retriever, window=settings.max_excerpt_sentences)
            if self.retriever
            else None
        )

    # -- status ------------------------------------------------------------------------

    def readiness(self) -> Readiness:
        reasons: list[str] = []
        warnings: list[str] = []
        if self.startup_error:
            reasons.append(f"corpus: {self.startup_error}")
        if not self.audit.writable():
            reasons.append("audit log is not writable")
        if self.corpus is not None:
            clean_quarantined = [c for c in self.corpus.quarantined if c.startswith("c_")]
            if len(clean_quarantined) > MAX_EXPECTED_CLEAN_QUARANTINE:
                warnings.append(
                    f"{len(clean_quarantined)} corpus chunks quarantined; possible poisoning"
                )
        return Readiness(not reasons, tuple(reasons), tuple(warnings))

    # -- request path --------------------------------------------------------------------

    def ask(
        self,
        question: str,
        jurisdiction: Jurisdiction | None = None,
        request_id: str | None = None,
    ) -> AnswerResponse:
        request_id = request_id or "req_" + uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        base: dict[str, Any] = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "request_id": request_id,
            "question_sha256_16": fingerprint(question),
            "question_len": len(question),
        }
        try:
            corpus, retriever, answerer = self.corpus, self.retriever, self.answerer
            if corpus is None or retriever is None or answerer is None:
                raise UnavailableError(
                    UnavailableCode.NOT_READY, self.startup_error or "corpus not loaded"
                )
            try:
                findings = check_question(question, self.settings)
            except RejectionError as exc:
                log.info("rejected", extra={"stage": "guard", "code": exc.code.value})
                self.audit.write(
                    {**base, "outcome": Outcome.REJECTED.value, "code": exc.code.value}
                )
                raise
            event_ids = [
                self.events.add(
                    make_event(f, EventSource.QUESTION, EventAction.LOGGED, request_id=request_id)
                ).event_id
                for f in findings
            ]
            if event_ids:
                log.warning("injection attempt in question logged", extra={"stage": "guard"})
            response = self._answer(
                corpus, retriever, answerer, question, jurisdiction, request_id, event_ids, started
            )
            self.audit.write(self._audit_record(base, response))
            return response
        finally:
            request_id_var.reset(token)

    def _answer(
        self,
        corpus: Corpus,
        retriever: Retriever,
        answerer: Answerer,
        question: str,
        jurisdiction: Jurisdiction | None,
        request_id: str,
        event_ids: list[str],
        started: float,
    ) -> AnswerResponse:
        result = run_pipeline(
            question,
            corpus=corpus,
            retriever=retriever,
            answerer=answerer,
            settings=self.settings,
            output_guard=self.defences.output_guard,
            jurisdiction=jurisdiction,
        )
        log.info(
            "retrieved",
            extra={
                "stage": "retrieve",
                "hits": len(result.search.hits),
                "strength": round(result.search.strength, 4),
                "margin": round(result.search.margin, 4),
                "gate_passed": result.gate_passed,
            },
        )
        if result.citation_failure is not None:
            log.warning(
                "citation rejected",
                extra={"stage": "validate", "failure": result.citation_failure.value},
            )
        for finding in result.output_findings:
            event = make_event(
                finding, EventSource.RESPONSE, EventAction.ABSTAINED, request_id=request_id
            )
            event_ids.append(self.events.add(event).event_id)
        if result.output_findings:
            log.warning("unsafe output withheld", extra={"stage": "validate"})
        answer = result.answer
        outcome = Outcome.ANSWERED if answer.answer is not None else Outcome.ABSTAINED
        log.info("answered", extra={"stage": "answer", "outcome": outcome.value})
        return AnswerResponse(
            request_id=request_id,
            outcome=outcome,
            corpus_version=corpus.version,
            result=answer,
            retrieved=result.search.hits,
            security_event_ids=tuple(event_ids),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    @staticmethod
    def _audit_record(base: dict[str, Any], response: AnswerResponse) -> dict[str, Any]:
        return {
            **base,
            "outcome": response.outcome.value,
            "abstain_reason": response.result.abstain_reason,
            "corpus_version": response.corpus_version,
            "retrieved": [(h.chunk_id, h.score) for h in response.retrieved],
            "citations": [c.chunk_id for c in response.result.citations],
            "security_event_ids": list(response.security_event_ids),
            "latency_ms": response.latency_ms,
        }
