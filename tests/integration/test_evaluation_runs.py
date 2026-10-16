"""Exercise the evaluation code paths against the committed data (dev and security only).

The test split is never evaluated here; the frozen final results are only read.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from legisqa.cli import app
from legisqa.config import Settings
from legisqa.evaluation.checks import run_checks
from legisqa.evaluation.harness import dev_run
from legisqa.evaluation.report import render

REPO = Path(__file__).resolve().parents[2]


def settings() -> Settings:
    return Settings(_env_file=None, data_dir=REPO / "sample-data")  # type: ignore[call-arg]


@pytest.fixture(scope="module")
def dev_results() -> dict[str, object]:
    return dev_run(REPO / "sample-data", settings())


def test_dev_run_reproduces_committed_dev_results(dev_results: dict[str, object]) -> None:
    committed = json.loads((REPO / "eval/results/dev.json").read_text("utf-8"))
    for key in ("operating_point", "A", "B_masked", "negatives", "comparison_retrieval"):
        assert json.loads(json.dumps(dev_results[key])) == committed[key], key


def test_configured_operating_point_is_the_dev_choice(dev_results: dict[str, object]) -> None:
    point = dev_results["operating_point"]
    assert isinstance(point, dict)
    configured = settings()
    assert point["gate_min_strength"] == configured.gate_min_strength
    assert point["gate_min_margin"] == configured.gate_min_margin
    assert point["max_excerpt_sentences"] == configured.max_excerpt_sentences


def test_checks_pass_on_committed_state() -> None:
    assert run_checks(settings(), REPO / "eval") == []


def test_render_writes_generated_sections(tmp_path: Path) -> None:
    dev = json.loads((REPO / "eval/results/dev.json").read_text("utf-8"))
    final = json.loads((REPO / "eval/results/final.json").read_text("utf-8"))
    render(dev, final, tmp_path)
    verify = (tmp_path / "verify.md").read_text("utf-8")
    security = (tmp_path / "security-report.md").read_text("utf-8")
    assert "| AT1 |" in verify and "BEGIN GENERATED: results" in verify
    assert "Attack success by defence configuration" in security


def test_eval_final_refuses_a_mismatched_operating_point(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["eval", "final"], env={"LEGISQA_GATE_MIN_STRENGTH": "0.3"})
    assert result.exit_code == 1
    assert "differs from dev.json" in result.output
