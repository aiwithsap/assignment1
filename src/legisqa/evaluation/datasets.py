"""Evaluation sets built from the committed sample data. Labels are read only here."""

import json
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legisqa.guards import is_valid_tfn

C_SAMPLE_SIZE = 100
SEED = 20261015
MASK = "the relevant instrument"


@dataclass(frozen=True)
class Answerable:
    question_id: str
    question: str
    gold_answer: str
    gold_chunk_id: str
    citation: str


@dataclass(frozen=True)
class Negative:
    negative_id: str
    kind: str  # hard_negative | out_of_corpus | evidence_removed
    question: str
    withheld_chunk_id: str = ""  # evidence_removed only
    related_citation: str = ""


@dataclass(frozen=True)
class Attack:
    attack_id: str
    technique: str
    objective: str
    poisoned_chunk_id: str
    original_chunk_id: str
    question: str
    payload: str


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def answerable(data: Path, split: str) -> list[Answerable]:
    return [
        Answerable(
            r["question_id"], r["question"], r["gold_answer"], r["gold_chunk_id"], r["citation"]
        )
        for r in _jsonl(data / f"questions_{split}.jsonl")
    ]


def _citation_pattern(citation: str) -> re.Pattern[str]:
    core = re.sub(r"\s*\((?:Cth|NSW|Qld|WA|SA|Tas|Vic|NI)\)\s*$", "", citation).strip()
    return re.compile(re.escape(core) + r"(?:\s*\([A-Za-z]+\))?", re.IGNORECASE)


def masked(items: list[Answerable]) -> list[Answerable]:
    """Condition B: the instrument's name replaced, to remove the lexical shortcut."""
    out = []
    for item in items:
        question = _citation_pattern(item.citation).sub(MASK, item.question)
        out.append(
            Answerable(
                item.question_id, question, item.gold_answer, item.gold_chunk_id, item.citation
            )
        )
    return out


def names_instrument(item: Answerable) -> bool:
    return bool(_citation_pattern(item.citation).search(item.question))


def negatives(
    data: Path, split: str, items: list[Answerable], sample: int | None
) -> list[Negative]:
    """Hand-built negatives plus evidence-removed versions of answerable questions."""
    out = [
        Negative(r["negative_id"], r["kind"], r["question"])
        for r in _jsonl(data / f"negatives_{split}.jsonl")
    ]
    pool = sorted(items, key=lambda i: i.question_id)
    if sample is not None and sample < len(pool):
        pool = random.Random(SEED).sample(pool, sample)  # noqa: S311 - deterministic sampling
    out += [
        Negative("er_" + i.question_id, "evidence_removed", i.question, i.gold_chunk_id, i.citation)
        for i in pool
    ]
    return out


def attacks(data: Path) -> list[Attack]:
    labels = {r["chunk_id"]: r for r in _jsonl(data / "adversarial/labels.jsonl")}
    texts = {r["chunk_id"]: r["text"] for r in _jsonl(data / "adversarial/injected_chunks.jsonl")}
    out = []
    for q in _jsonl(data / "adversarial/questions.jsonl"):
        label = labels[q["poisoned_chunk_id"]]
        start, end = label["payload_span"]
        out.append(
            Attack(
                label["attack_id"],
                label["technique"],
                label["objective"],
                q["poisoned_chunk_id"],
                q["gold_chunk_id"],
                q["question"],
                texts[q["poisoned_chunk_id"]][start:end],
            )
        )
    return out


def direct_injections(data: Path) -> list[dict[str, str]]:
    raw: list[dict[str, str]] = json.loads(
        (data / "sources/direct_injections.json").read_text("utf-8")
    )["questions"]
    return raw


def _tfn(seed: int) -> str:
    """A synthetic number that passes the TFN check digit (never a real person's by design)."""
    base = 100_000_000 + seed * 7919
    while not is_valid_tfn(str(base)):
        base += 1
    s = str(base)
    return f"{s[:3]} {s[3:6]} {s[6:]}"


def pii_variants(items: list[Answerable]) -> list[tuple[str, str]]:
    """Condition E: ten questions carrying synthetic personal information."""
    shapes: list[Callable[[int], str]] = [
        lambda i: f"My email is jordan.citizen{i}@example.com.",
        lambda i: f"Call me on 0412 345 {600 + i:03d}.",
        lambda i: f"My TFN is {_tfn(i)}.",
        lambda i: "My card is 4111 1111 1111 1111.",
        lambda i: f"Reach me at +61 2 9{i:03d} 1234.",
    ]
    out = []
    for n, item in enumerate(sorted(items, key=lambda x: x.question_id)[:10]):
        out.append((f"pii_{n}", f"{item.question} {shapes[n % len(shapes)](n)}"))
    return out
