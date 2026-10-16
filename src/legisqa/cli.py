"""Command-line interface. Further commands (ask, serve, eval) arrive with their features."""

import json
from typing import Annotated

import typer

from legisqa import __version__
from legisqa.config import Settings

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"legisqa {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Grounded Q&A over Australian legislation."""


@app.command("show-config")
def show_config() -> None:
    """Print the effective settings as JSON (there are no secrets to hide)."""
    settings = Settings()
    typer.echo(json.dumps(settings.model_dump(mode="json"), indent=2, sort_keys=True))
