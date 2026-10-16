import json
from pathlib import Path

from typer.testing import CliRunner

from legisqa.cli import app


def test_verify_corpus_reports_integrity() -> None:
    result = CliRunner().invoke(app, ["verify-corpus"])
    assert result.exit_code == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["clean_chunks"] == 426
    assert summary["overlay_quarantined"] == summary["overlay_chunks"] >= 28
    assert summary["problems"] == []


def test_verify_corpus_fails_on_tampering(sample_data_copy: Path) -> None:
    data = sample_data_copy
    (data / "corpus.jsonl").write_text("{}\n", "utf-8")
    result = CliRunner().invoke(app, ["verify-corpus"], env={"LEGISQA_DATA_DIR": str(data)})
    assert result.exit_code == 3
