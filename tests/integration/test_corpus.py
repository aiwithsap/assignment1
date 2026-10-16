"""Corpus integrity, provenance and quarantine against the real committed sample data."""

import json
from pathlib import Path

import pytest

from legisqa.corpus import IngestPolicy, load_corpus
from legisqa.errors import StartupError
from legisqa.models import Chunk
from legisqa.security.detectors import DetectorId
from legisqa.security.events import EventStore


def labels(data: Path) -> dict[str, dict[str, object]]:
    lines = (data / "adversarial/labels.jsonl").read_text("utf-8").splitlines()
    return {(rec := json.loads(line))["chunk_id"]: rec for line in lines}


def test_prod_load_has_no_overlay_and_no_quarantine(sample_data: Path) -> None:
    corpus = load_corpus(sample_data, include_overlay=False)
    assert len(corpus.clean) == 426
    assert not corpus.quarantined
    assert not any(cid.startswith("adv_") for cid in corpus.clean)


def test_every_overlay_chunk_is_quarantined_by_provenance(sample_data: Path) -> None:
    events = EventStore()
    corpus = load_corpus(sample_data, include_overlay=True, events=events)
    attack = labels(sample_data)
    assert set(attack) <= set(corpus.quarantined)
    assert all(corpus.quarantined[c].layer == "provenance" for c in attack)
    assert len(corpus.clean) == 426  # clean originals stay answerable
    assert {e.chunk_id for e in events.all()} == set(attack)


def test_provenance_pinpoints_inserted_payload(sample_data: Path) -> None:
    corpus = load_corpus(sample_data, include_overlay=True)
    for chunk_id, record in labels(sample_data).items():
        finding = corpus.quarantined[chunk_id].findings[0]
        span = record["payload_span"]
        assert isinstance(span, list)
        start, end = int(span[0]), int(span[1])
        assert finding.detector is DetectorId.PROV
        assert finding.start <= start and finding.end >= end


def test_content_scan_catches_catalogue_without_provenance(sample_data: Path) -> None:
    corpus = load_corpus(sample_data, include_overlay=True, policy=IngestPolicy(provenance=False))
    attack = labels(sample_data)
    missed = [attack[c]["attack_id"] for c in attack if c not in corpus.quarantined]
    assert missed == []


def test_all_layers_off_lets_everything_through(sample_data: Path) -> None:
    corpus = load_corpus(
        sample_data,
        include_overlay=True,
        policy=IngestPolicy(provenance=False, content_scan=False),
    )
    assert not corpus.quarantined


def test_tampered_corpus_file_fails_startup(sample_data_copy: Path) -> None:
    path = sample_data_copy / "corpus.jsonl"
    path.write_bytes(path.read_bytes().replace(b"Minister", b"Ministre", 1))
    with pytest.raises(StartupError, match="hash mismatch"):
        load_corpus(sample_data_copy, include_overlay=False)


def test_missing_manifest_fails_startup(sample_data_copy: Path) -> None:
    (sample_data_copy / "manifest.json").unlink()
    with pytest.raises(StartupError, match="manifest not found"):
        load_corpus(sample_data_copy, include_overlay=False)


def test_incompatible_manifest_schema_fails_startup(sample_data_copy: Path) -> None:
    path = sample_data_copy / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["schema_version"] = 99
    path.write_text(json.dumps(manifest), "utf-8")
    with pytest.raises(StartupError, match="incompatible"):
        load_corpus(sample_data_copy, include_overlay=False)


def test_chunk_records_carry_no_evaluation_labels() -> None:
    assert set(Chunk.model_fields) == {
        "chunk_id",
        "version_id",
        "citation",
        "jurisdiction",
        "doc_type",
        "url",
        "text",
    }


def test_loading_never_needs_the_label_file(sample_data_copy: Path) -> None:
    (sample_data_copy / "adversarial/labels.jsonl").unlink()
    expected = len(
        (sample_data_copy / "adversarial/questions.jsonl").read_text("utf-8").splitlines()
    )
    corpus = load_corpus(sample_data_copy, include_overlay=True)
    assert len(corpus.quarantined) == expected
