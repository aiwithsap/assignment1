"""Evaluation definitions behave as documented (metrics, datasets, report sections, gates)."""

import json
from pathlib import Path

import pytest

from legisqa.evaluation import datasets as ds
from legisqa.evaluation.harness import _derived, check_acceptance, code_fingerprint
from legisqa.evaluation.metrics import content_overlap, rank_of, rate, supported
from legisqa.evaluation.report import replace_section
from legisqa.guards import is_valid_tfn
from legisqa.models import Citation, GroundedAnswer, Hit

REPO = Path(__file__).resolve().parents[2]
QUOTE = "A licence holder must pay the annual licence fee before 30 June each year."


def test_support_definition() -> None:
    answer = GroundedAnswer.answered(QUOTE, (Citation(chunk_id="c_00000000000a", quote=QUOTE),))
    assert supported(
        answer, "c_00000000000a", "The annual licence fee must be paid before 30 June."
    )
    assert not supported(
        answer, "c_00000000000b", "The annual licence fee must be paid before 30 June."
    )
    assert not supported(answer, "c_00000000000a", "Penalties apply for unregistered aircraft.")
    assert content_overlap("", QUOTE) == 0.0


def test_rank_and_rate() -> None:
    hits = (Hit(chunk_id="c_00000000000a", score=2.0), Hit(chunk_id="c_00000000000b", score=1.0))
    assert rank_of(hits, "c_00000000000b") == 2
    assert rank_of(hits, "c_00000000000c") is None
    assert rate(1, 4) == 0.25 and rate(0, 0) is None


def test_masking_removes_instrument_name() -> None:
    item = ds.Answerable(
        "q1",
        "Under the Privacy (Persons Reported as Missing) Rule 2014 (Cth), who may act?",
        "a",
        "c_00000000000a",
        "Privacy (Persons Reported as Missing) Rule 2014 (Cth)",
    )
    masked = ds.masked([item])[0]
    assert "Privacy" not in masked.question and ds.MASK in masked.question
    assert ds.names_instrument(item) and not ds.names_instrument(masked)


def test_datasets_load_from_committed_sample_data() -> None:
    data = REPO / "sample-data"
    dev = ds.answerable(data, "dev")
    negatives = ds.negatives(data, "dev", dev, sample=10)
    assert {n.kind for n in negatives} == {"hard_negative", "out_of_corpus", "evidence_removed"}
    attacks = ds.attacks(data)
    assert len({a.attack_id for a in attacks}) == len(attacks) >= 28
    assert all(a.payload for a in attacks)
    assert len(ds.pii_variants(dev)) == 10


def test_synthetic_tfns_pass_the_check_digit() -> None:
    for i in range(5):
        assert is_valid_tfn(ds._tfn(i).replace(" ", ""))


def test_replace_section_preserves_commentary(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "# Title\n\nIntro.\n\n<!-- BEGIN GENERATED: x -->\nold\n"
        "<!-- END GENERATED: x -->\n\nOutro.\n"
    )
    replace_section(path, "x", "new table")
    text = path.read_text()
    assert "new table" in text and "old" not in text and text.endswith("Outro.\n")


def test_acceptance_uses_predeclared_thresholds() -> None:
    final = json.loads((REPO / "eval/results/final.json").read_text())
    results = check_acceptance(final, REPO / "eval/acceptance.toml")
    assert [r["id"] for r in results] == ["AT1", "AT2", "AT3", "AT4", "AT5"]
    assert results == final["acceptance"]


@pytest.mark.parametrize("metric", ["security.rejection_rate", "security.attack_failure_rate"])
def test_derived_security_metrics(metric: str) -> None:
    final = json.loads((REPO / "eval/results/final.json").read_text())
    assert _derived(final, metric) == 1.0


def test_committed_final_results_match_current_code() -> None:
    manifest = json.loads((REPO / "eval/results/final-manifest.json").read_text())
    assert manifest["code_fingerprint"] == code_fingerprint()
