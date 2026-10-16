"""Command-line interface. Further commands (ask, serve, eval) arrive with their features."""

import json
from typing import Annotated

import typer
import uvicorn

from legisqa import __version__
from legisqa.api import create_app
from legisqa.config import Profile, Settings
from legisqa.corpus import load_corpus
from legisqa.errors import EXIT_CODE, Outcome, RejectionError, StartupError, UnavailableError
from legisqa.logging_setup import configure_logging
from legisqa.models import ErrorEnvelope, Jurisdiction
from legisqa.service import AnswerService

ProfileOption = Annotated[
    Profile | None, typer.Option("--profile", help="Override LEGISQA_PROFILE.")
]

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


def _settings(profile: Profile | None) -> Settings:
    return Settings(profile=profile) if profile else Settings()


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question about Australian legislation.")],
    jurisdiction: Annotated[
        Jurisdiction | None, typer.Option(help="Restrict the search to one jurisdiction.")
    ] = None,
    profile: ProfileOption = None,
) -> None:
    """Answer one question. Prints the JSON response; exit code follows the outcome contract."""
    settings = _settings(profile)
    configure_logging("WARNING")
    service = AnswerService(settings)
    try:
        response = service.ask(question, jurisdiction)
    except (RejectionError, UnavailableError) as exc:
        outcome = Outcome.REJECTED if isinstance(exc, RejectionError) else Outcome.UNAVAILABLE
        envelope = ErrorEnvelope(
            request_id="cli", outcome=outcome, code=exc.code.value, message=exc.message
        )
        typer.echo(envelope.model_dump_json(indent=2))
        raise typer.Exit(EXIT_CODE[outcome]) from exc
    typer.echo(response.model_dump_json(indent=2))


@app.command()
def serve(profile: ProfileOption = None) -> None:
    """Serve the API and the built UI on the configured host and port."""
    settings = _settings(profile)
    configure_logging(settings.log_level)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)
