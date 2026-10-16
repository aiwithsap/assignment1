"""TF-IDF cosine baseline for comparison 1 (retrieval method), numpy only."""

import math
from collections import Counter
from collections.abc import Iterable

import numpy as np

from legisqa.models import Chunk
from legisqa.retrieval import tokenize


class TfidfRetriever:
    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self._chunks = sorted(chunks, key=lambda c: c.chunk_id)
        docs = [tokenize(f"{c.citation} {c.text}") for c in self._chunks]
        df = Counter(t for doc in docs for t in set(doc))
        self._vocab = {t: i for i, t in enumerate(sorted(df))}
        n = len(docs)
        self._idf = np.array([math.log((1 + n) / (1 + df[t])) + 1 for t in sorted(df)])
        self._matrix = np.vstack([self._vector(doc) for doc in docs])

    def _vector(self, tokens: list[str]) -> np.ndarray:
        vec = np.zeros(len(self._vocab))
        for term, count in Counter(tokens).items():
            index = self._vocab.get(term)
            if index is not None:
                vec[index] = count
        vec *= self._idf
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def ranked_ids(self, query: str, k: int = 5) -> list[str]:
        scores = self._matrix @ self._vector(tokenize(query))
        order = np.argsort(-scores, kind="stable")[:k]
        return [self._chunks[i].chunk_id for i in order if scores[i] > 0]
