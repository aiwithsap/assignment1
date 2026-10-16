import pytest

from legisqa.gate import decide
from legisqa.models import Chunk, DocType, Jurisdiction
from legisqa.retrieval import Retriever, SearchResult, tokenize


def chunk(idx: int, text: str, jurisdiction: Jurisdiction = Jurisdiction.COMMONWEALTH) -> Chunk:
    return Chunk(
        chunk_id=f"c_{idx:012x}",
        version_id=f"v{idx}",
        citation=f"Example Act {idx} (Cth)",
        jurisdiction=jurisdiction,
        doc_type=DocType.PRIMARY_LEGISLATION,
        url="https://www.legislation.gov.au/x",
        text=text,
    )


CHUNKS = [
    chunk(1, "A licence holder must pay the annual licence fee before 30 June."),
    chunk(2, "The Minister may revoke an approval for a child care service."),
    chunk(3, "An inspector may enter premises with a warrant.", Jurisdiction.TASMANIA),
    chunk(4, "Airworthiness directive applies to engine mount beams of the aircraft."),
]


@pytest.fixture
def retriever() -> Retriever:
    return Retriever(CHUNKS)


def test_tokenize_drops_stopwords_and_keeps_section_numbers() -> None:
    assert tokenize("What does section 912A of the Act say?") == ["section", "912a", "act", "say"]


def test_ranks_the_matching_chunk_first(retriever: Retriever) -> None:
    result = retriever.search("when is the annual licence fee payable")
    assert result.hits[0].chunk_id == "c_000000000001"
    assert "licence" in result.hits[0].top_terms
    assert 0.0 < result.strength <= 1.0
    assert 0.0 <= result.margin <= 1.0


def test_jurisdiction_filter(retriever: Retriever) -> None:
    result = retriever.search("inspector enter premises", jurisdiction=Jurisdiction.COMMONWEALTH)
    assert all(h.chunk_id != "c_000000000003" for h in result.hits)


def test_unknown_terms_lower_strength(retriever: Retriever) -> None:
    known = retriever.search("annual licence fee")
    padded = retriever.search("annual licence fee interplanetary unicorn teleportation royalties")
    assert padded.strength < known.strength


def test_empty_or_stopword_query(retriever: Retriever) -> None:
    assert retriever.search("what is the").hits == ()
    assert retriever.search("zzzz qqqq").hits == ()


def test_empty_corpus_is_rejected() -> None:
    with pytest.raises(ValueError):
        Retriever([])


@pytest.mark.parametrize(
    ("strength", "margin", "passed"),
    [(0.5, 0.2, True), (0.29, 0.2, False), (0.5, 0.05, False)],
)
def test_gate(strength: float, margin: float, passed: bool) -> None:
    result = SearchResult(
        hits=Retriever(CHUNKS).search("licence fee").hits, strength=strength, margin=margin
    )
    assert decide(result, min_strength=0.3, min_margin=0.1).passed is passed


def test_gate_fails_without_hits() -> None:
    assert not decide(SearchResult((), 1.0, 1.0), 0.0, 0.0).passed
