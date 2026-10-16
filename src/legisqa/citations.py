"""Citation validator (citation integrity, not answer support).

Every citation must point to a chunk that exists, is not quarantined, was retrieved in
this request, and contains the quote verbatim. For the extractive answerer these hold by
construction; they remain the contract any other answerer must meet.
"""

import re
import unicodedata
from collections.abc import Collection
from enum import StrEnum

from legisqa.corpus import Corpus
from legisqa.models import AnswerStatus, GroundedAnswer


class CitationFailure(StrEnum):
    UNKNOWN_CHUNK = "unknown_chunk"
    QUARANTINED = "quarantined"
    NOT_RETRIEVED = "not_retrieved"
    NOT_VERBATIM = "not_verbatim"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def validate_citations(
    answer: GroundedAnswer, corpus: Corpus, retrieved_ids: Collection[str]
) -> CitationFailure | None:
    if answer.status is not AnswerStatus.ANSWERED:
        return None
    for citation in answer.citations:
        chunk = corpus.get(citation.chunk_id)
        if chunk is None:
            return CitationFailure.UNKNOWN_CHUNK
        if corpus.is_quarantined(citation.chunk_id):
            return CitationFailure.QUARANTINED
        if citation.chunk_id not in retrieved_ids:
            return CitationFailure.NOT_RETRIEVED
        if _norm(citation.quote) not in _norm(chunk.text):
            return CitationFailure.NOT_VERBATIM
    return None
