"""Command-line interface. Further commands (ask, serve, eval) arrive with their features."""

import json
from typing import Annotated

import typer

from legisqa import __version__
from legisqa.config import Settings
from legisqa.corpus import load_corpus
from legisqa.errors import EXIT_CODE, Outcome, StartupError

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


@app.command("verify-corpus")
def verify_corpus() -> None:
    """Check corpus integrity: hashes, overlay isolation, attribution, quarantine counts."""
    settings = Settings()
    problems: list[str] = []
    try:
        prod = load_corpus(settings.data_dir, include_overlay=False)
        full = load_corpus(settings.data_dir, include_overlay=True)
    except StartupError as exc:
        typer.echo(f"corpus integrity FAILED: {exc.message}", err=True)
        raise typer.Exit(EXIT_CODE[Outcome.UNAVAILABLE]) from exc
    prod_ids = set(prod.clean) | set(prod.quarantined)
    full_ids = set(full.clean) | set(full.quarantined)
    overlay_ids = full_ids - prod_ids
    if any(chunk_id.startswith("adv_") for chunk_id in prod_ids):
        problems.append("adversarial chunks present without the overlay")
    if not all(chunk_id.startswith("adv_") for chunk_id in overlay_ids):
        problems.append("overlay chunk ids must use the adv_ namespace")
    if not (settings.data_dir / "ATTRIBUTION.md").is_file():
        problems.append("ATTRIBUTION.md missing")
    clean_quarantined = sorted(c for c in full.quarantined if not c.startswith("adv_"))
    summary = {
        "corpus_version": full.version,
        "clean_chunks": len(prod_ids),
        "overlay_chunks": len(overlay_ids),
        "overlay_quarantined": len(overlay_ids & set(full.quarantined)),
        "clean_chunks_quarantined": len(clean_quarantined),
        "problems": problems,
    }
    typer.echo(json.dumps(summary, indent=2))
    if problems:
        raise typer.Exit(EXIT_CODE[Outcome.UNAVAILABLE])
