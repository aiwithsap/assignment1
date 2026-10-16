from legisqa.answerers.extractive import ExtractiveAnswerer, split_sentences
from legisqa.corpus import Corpus
from legisqa.models import AnswerStatus, Chunk, DocType, Hit, Jurisdiction
from legisqa.retrieval import Retriever

TEXT = (
    "This instrument is made under s. 33 of the Act. A licence holder must pay the annual "
    "licence fee before 30 June each year. The fee is set out in Schedule 1. Late payment "
    "attracts a penalty of 10 penalty units."
)
CHUNK = Chunk(
    chunk_id="c_00000000000a",
    version_id="v",
    citation="Fees Determination 2020 (Cth)",
    jurisdiction=Jurisdiction.COMMONWEALTH,
    doc_type=DocType.SECONDARY_LEGISLATION,
    url="https://www.legislation.gov.au/x",
    text=TEXT,
)
OTHER = CHUNK.model_copy(update={"chunk_id": "c_00000000000b", "text": "Unrelated aviation text."})


def make() -> tuple[ExtractiveAnswerer, Corpus]:
    corpus = Corpus(version="v", manifest={}, clean={c.chunk_id: c for c in (CHUNK, OTHER)})
    return ExtractiveAnswerer(Retriever(corpus.clean.values()), window=1), corpus


def test_sentence_split_respects_legal_abbreviations() -> None:
    sentences = [TEXT[s.start : s.end] for s in split_sentences(TEXT)]
    assert sentences[0] == "This instrument is made under s. 33 of the Act."
    assert len(sentences) == 4


def test_excerpt_is_verbatim_best_sentence() -> None:
    answerer, corpus = make()
    hits = (Hit(chunk_id=CHUNK.chunk_id, score=1.0),)
    answer = answerer.answer("when must the annual licence fee be paid", hits, corpus)
    assert answer is not None and answer.status is AnswerStatus.ANSWERED
    assert (
        answer.answer
        == "A licence holder must pay the annual licence fee before 30 June each year."
    )
    assert answer.citations[0].quote in TEXT


def test_window_adds_following_context() -> None:
    corpus = make()[1]
    answerer = ExtractiveAnswerer(Retriever(corpus.clean.values()), window=2)
    hits = (Hit(chunk_id=CHUNK.chunk_id, score=1.0),)
    answer = answerer.answer("annual licence fee", hits, corpus)
    assert answer is not None and answer.answer is not None
    assert answer.answer.endswith("Schedule 1.")


def test_no_hits_or_no_overlap_returns_none() -> None:
    answerer, corpus = make()
    assert answerer.answer("fee", (), corpus) is None
    hits = (Hit(chunk_id=CHUNK.chunk_id, score=1.0),)
    assert answerer.answer("zebra quantum", hits, corpus) is None
