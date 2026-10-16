"""Answerability gate: answer only when retrieval found strong, distinct evidence."""

from dataclasses import dataclass

from legisqa.retrieval import SearchResult


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    strength: float
    margin: float


def decide(result: SearchResult, min_strength: float, min_margin: float) -> GateDecision:
    passed = bool(result.hits) and result.strength >= min_strength and result.margin >= min_margin
    return GateDecision(passed=passed, strength=result.strength, margin=result.margin)
