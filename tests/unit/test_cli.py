import json

from typer.testing import CliRunner

from legisqa import __version__
from legisqa.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_show_config_defaults() -> None:
    result = runner.invoke(app, ["show-config"], env={"LEGISQA_PROFILE": "eval"})
    assert result.exit_code == 0
    assert json.loads(result.stdout)["profile"] == "eval"
