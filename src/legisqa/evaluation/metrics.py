"""Metric definitions. These were fixed before the final test run (see evidence/plan.md)."""

from collections.abc import Sequence

from legisqa.models import GroundedAnswer, Hit
from legisqa.retrieval import tokenize

SUPPORT_OVERLAP = 0.5


def rank_of(hits: Sequence[Hit], chunk_id: str) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if hit.chunk_id == chunk_id:
            return rank
    return None


def content_overlap(gold_answer: str, excerpt: str) -> float:
    """Share of the gold answer's content tokens that appear in the excerpt."""
    gold = set(tokenize(gold_answer))
    if not gold:
        return 0.0
    return len(gold & set(tokenize(excerpt))) / len(gold)


def cites(answer: GroundedAnswer, chunk_id: str) -> bool:
    return any(c.chunk_id == chunk_id for c in answer.citations)


def supported(answer: GroundedAnswer, gold_chunk_id: str, gold_answer: str) -> bool:
    """Predeclared: cites the gold chunk AND contains >= 50% of gold-answer content tokens."""
    return (
        answer.answer is not None
        and cites(answer, gold_chunk_id)
        and content_overlap(gold_answer, answer.answer) >= SUPPORT_OVERLAP
    )


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
