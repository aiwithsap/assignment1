"""Deterministic extractive answerer: the excerpt is a verbatim span of the top chunk."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from legisqa.corpus import Corpus
from legisqa.models import MIN_QUOTE_CHARS, Citation, GroundedAnswer, Hit
from legisqa.retrieval import Retriever, tokenize

# Abbreviations common in legislation that end with a full stop but do not end a sentence.
_ABBREVIATIONS = re.compile(
    r"(?:\b(?:s|ss|subs|sub-s|para|paras|subpara|reg|regs|r|rr|cl|No|Nos|Pt|Div|Sch|"
    r"e\.g|i\.e|etc|cf|viz|approx|Cth|Vic|Qld|Tas|Pty|Ltd|Co|Inc|St|Dr|Mr|Ms|Mrs|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.|\b[A-Z]\.)$"
)
_BOUNDARY = re.compile(r"(?<=[.;:])\s+(?=[(\[A-Z0-9\"\u2018\u201c])")
MAX_SENTENCE_CHARS = 600


@dataclass(frozen=True)
class Span:
    start: int
    end: int


def split_sentences(text: str) -> list[Span]:
    """Split legislation text into sentence spans, respecting legal abbreviations."""
    spans: list[Span] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        candidate = text[start : match.start()]
        if _ABBREVIATIONS.search(candidate):
            continue
        if len(candidate.strip()) >= MIN_QUOTE_CHARS or len(candidate) > MAX_SENTENCE_CHARS:
            spans.append(Span(start, match.start()))
            start = match.end()
    if start < len(text):
        tail = Span(start, len(text))
        if spans and len(text[start:].strip()) < MIN_QUOTE_CHARS:
            spans[-1] = Span(spans[-1].start, len(text))
        else:
            spans.append(tail)
    return spans


class ExtractiveAnswerer:
    """Pick the best-scoring sentence of the top-ranked chunk, plus following context.

    ``window`` is the number of consecutive sentences returned (chosen on dev data).
    """

    def __init__(self, retriever: Retriever, window: int = 2) -> None:
        if window < 1:
            raise ValueError("window must be at least 1")
        self._retriever = retriever
        self._window = window

    def _score(self, sentence: str, query_terms: set[str]) -> float:
        # 1 + idf: every matched term counts, rarer terms count more (idf can be 0 in tiny corpora).
        present = query_terms & set(tokenize(sentence))
        return sum(1.0 + max(self._retriever.idf(t), 0.0) for t in present)

    def answer(self, question: str, hits: Sequence[Hit], corpus: Corpus) -> GroundedAnswer | None:
        if not hits:
            return None
        chunk = corpus.get(hits[0].chunk_id)
        if chunk is None:
            return None
        terms = set(tokenize(question))
        spans = split_sentences(chunk.text)
        scores = [self._score(chunk.text[s.start : s.end], terms) for s in spans]
        if not spans or max(scores) <= 0:
            return None
        best = scores.index(max(scores))
        chosen = spans[best : best + self._window]
        start, end = chosen[0].start, chosen[-1].end
        excerpt = chunk.text[start:end].strip()
        if len(excerpt) < MIN_QUOTE_CHARS:
            excerpt = chunk.text.strip()
        return GroundedAnswer.answered(excerpt, (Citation(chunk_id=chunk.chunk_id, quote=excerpt),))
