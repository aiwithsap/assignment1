"""BM25 keyword retrieval over the clean (non-quarantined) chunks only."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from legisqa.models import Chunk, Hit, Jurisdiction

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "all",
        "also",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "me",
        "must",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "shall",
        "should",
        "so",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "under",
        "up",
        "upon",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    ]
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


@dataclass(frozen=True)
class SearchResult:
    hits: tuple[Hit, ...]
    strength: float  # top score / best attainable score for this query, in [0, 1]
    margin: float  # (top - second) / top, in [0, 1]


class Retriever:
    """Okapi BM25 over ``citation + text`` with optional jurisdiction filtering."""

    def __init__(self, chunks: Iterable[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self._chunks = sorted(chunks, key=lambda c: c.chunk_id)
        if not self._chunks:
            raise ValueError("cannot build a retriever over an empty corpus")
        self._k1, self._b = k1, b
        self._docs = [tokenize(f"{c.citation} {c.text}") for c in self._chunks]
        self._bm25 = BM25Okapi(self._docs, k1=k1, b=b)
        self._max_idf = max(self._bm25.idf.values())

    def __len__(self) -> int:
        return len(self._chunks)

    def idf(self, term: str) -> float:
        """Inverse document frequency; unseen terms get the maximum."""
        return float(self._bm25.idf.get(term, self._max_idf))

    def _term_score(self, index: int, term: str) -> float:
        tf = self._bm25.doc_freqs[index].get(term, 0)
        if tf == 0:
            return 0.0
        norm = 1 - self._b + self._b * self._bm25.doc_len[index] / self._bm25.avgdl
        idf = float(self._bm25.idf.get(term, 0.0))
        return float(idf * tf * (self._k1 + 1) / (tf + self._k1 * norm))

    def _ideal(self, terms: list[str]) -> float:
        """Score of a document holding every query term once at average length.

        Terms absent from the corpus count at the maximum idf, so a question about things
        the corpus never mentions gets a low relative strength.
        """
        return sum(float(self._bm25.idf.get(t, self._max_idf)) for t in set(terms))

    def search(
        self, query: str, k: int = 5, jurisdiction: Jurisdiction | None = None
    ) -> SearchResult:
        terms = tokenize(query)
        if not terms:
            return SearchResult(hits=(), strength=0.0, margin=0.0)
        scores = self._bm25.get_scores(terms)
        ranked = sorted(
            (
                (float(scores[i]), i)
                for i, chunk in enumerate(self._chunks)
                if jurisdiction is None or chunk.jurisdiction is jurisdiction
            ),
            key=lambda pair: (-pair[0], self._chunks[pair[1]].chunk_id),
        )
        ranked = [(s, i) for s, i in ranked if s > 0][:k]
        hits = tuple(
            Hit(
                chunk_id=self._chunks[i].chunk_id,
                score=round(score, 6),
                top_terms=tuple(
                    t
                    for t in sorted(set(terms), key=lambda t: -self._term_score(i, t))
                    if self._term_score(i, t) > 0
                )[:5],
            )
            for score, i in ranked
        )
        if not hits:
            return SearchResult(hits=(), strength=0.0, margin=0.0)
        top = ranked[0][0]
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        ideal = self._ideal(terms)
        strength = min(top / ideal, 1.0) if ideal > 0 else 0.0
        return SearchResult(hits=hits, strength=strength, margin=(top - second) / top)
