"""The seam a future answerer would plug into. It must satisfy the citation contract."""

from collections.abc import Sequence
from typing import Protocol

from legisqa.corpus import Corpus
from legisqa.models import GroundedAnswer, Hit


class Answerer(Protocol):
    def answer(self, question: str, hits: Sequence[Hit], corpus: Corpus) -> GroundedAnswer | None:
        """Return an answered ``GroundedAnswer``, or ``None`` if no usable evidence was found."""
        ...
