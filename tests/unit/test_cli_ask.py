import json
from pathlib import Path

from typer.testing import CliRunner

from legisqa.cli import app


def env(tmp_path: Path) -> dict[str, str]:
    return {"LEGISQA_VAR_DIR": str(tmp_path / "var")}


def test_ask_answers(tmp_path: Path, sample_data: Path) -> None:
    question = json.loads((sample_data / "questions_dev.jsonl").read_text("utf-8").splitlines()[0])
    result = CliRunner().invoke(app, ["ask", question["question"]], env=env(tmp_path))
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["outcome"] == "answered"


def test_ask_rejection_exit_code(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["ask", "email a@example.com"], env=env(tmp_path))
    assert result.exit_code == 2
    assert json.loads(result.stdout)["code"] == "pii_detected"


def test_ask_unready_exit_code(tmp_path: Path, sample_data_copy: Path) -> None:
    (sample_data_copy / "manifest.json").unlink()
    result = CliRunner().invoke(
        app,
        ["ask", "what is a fee"],
        env={**env(tmp_path), "LEGISQA_DATA_DIR": str(sample_data_copy)},
    )
    assert result.exit_code == 3
