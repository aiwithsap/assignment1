"""HTTP API (thin): every route delegates to ``AnswerService`` and follows the outcome contract."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from legisqa import __version__
from legisqa.config import Settings
from legisqa.errors import HTTP_STATUS, Outcome, RejectionCode, RejectionError, UnavailableError
from legisqa.logging_setup import configure_logging
from legisqa.models import AnswerResponse, AskRequest, Chunk, ErrorEnvelope
from legisqa.security.events import SecurityEvent
from legisqa.service import AnswerService

log = logging.getLogger("legisqa.api")

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class ReadinessView(BaseModel):
    model_config = ConfigDict(frozen=True)

    ready: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    corpus_version: str | None
    profile: str
    clean_chunks: int
    quarantined_chunks: int


class SourceView(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    quarantined: bool
    quarantine_layer: str | None = None
    detectors: tuple[str, ...] = ()


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "req_" + uuid.uuid4().hex[:16]


def _envelope(request: Request, outcome: Outcome, code: str | None, message: str) -> JSONResponse:
    body = ErrorEnvelope(
        request_id=_request_id(request), outcome=outcome, code=code, message=message
    )
    return JSONResponse(status_code=HTTP_STATUS[outcome], content=body.model_dump(mode="json"))


def create_app(settings: Settings | None = None, service: AnswerService | None = None) -> FastAPI:
    settings = settings or Settings()
    service = service or AnswerService(settings)
    app = FastAPI(title="Legislation Q&A", version=__version__)
    app.state.service = service

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = (
            supplied if supplied.isascii() and 0 < len(supplied) <= 64 else None
        ) or "req_" + uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(RejectionError)
    async def on_rejection(request: Request, exc: RejectionError) -> JSONResponse:
        return _envelope(request, Outcome.REJECTED, exc.code.value, exc.message)

    @app.exception_handler(UnavailableError)
    async def on_unavailable(request: Request, exc: UnavailableError) -> JSONResponse:
        return _envelope(request, Outcome.UNAVAILABLE, exc.code.value, exc.message)

    @app.exception_handler(RequestValidationError)
    async def on_invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(
            request,
            Outcome.REJECTED,
            RejectionCode.INVALID_REQUEST.value,
            f"Invalid request body ({len(exc.errors())} error(s)).",
        )

    @app.exception_handler(Exception)
    async def on_error(request: Request, exc: Exception) -> JSONResponse:
        log.exception("internal error")
        return _envelope(request, Outcome.INTERNAL_ERROR, None, "Internal error.")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=ReadinessView)
    def readyz() -> JSONResponse:
        readiness = service.readiness()
        corpus = service.corpus
        view = ReadinessView(
            ready=readiness.ready,
            reasons=readiness.reasons,
            warnings=readiness.warnings,
            corpus_version=corpus.version if corpus else None,
            profile=settings.profile.value,
            clean_chunks=len(corpus.clean) if corpus else 0,
            quarantined_chunks=len(corpus.quarantined) if corpus else 0,
        )
        return JSONResponse(
            status_code=200 if readiness.ready else 503, content=view.model_dump(mode="json")
        )

    @app.post(
        "/v1/answers",
        response_model=AnswerResponse,
        responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
    )
    def answers(body: AskRequest, request: Request) -> AnswerResponse:
        return service.ask(body.question, body.jurisdiction, request_id=_request_id(request))

    @app.get("/v1/sources/{chunk_id}", response_model=SourceView)
    def source(chunk_id: str) -> SourceView:
        corpus = service.corpus
        chunk = corpus.get(chunk_id) if corpus else None
        if corpus is None or chunk is None:
            raise HTTPException(status_code=404, detail="unknown source")
        record = corpus.quarantined.get(chunk_id)
        if record is not None and not settings.expose_security_endpoints:
            raise HTTPException(status_code=404, detail="unknown source")
        return SourceView(
            chunk=chunk,
            quarantined=record is not None,
            quarantine_layer=record.layer if record else None,
            detectors=tuple(sorted({f.detector.value for f in record.findings})) if record else (),
        )

    if settings.expose_security_endpoints:

        @app.get("/v1/security-events", response_model=list[SecurityEvent])
        def security_events() -> tuple[SecurityEvent, ...]:
            return service.events.all()

    _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
        return

    @app.get("/", response_class=PlainTextResponse)
    def ui_missing() -> str:
        return (
            "The UI has not been built. Run: cd frontend && npm ci && npm run build, "
            "then restart. The API is available under /v1 and /docs."
        )


def build_app() -> FastAPI:
    """Factory for ``uvicorn --factory legisqa.api:build_app``."""
    settings = Settings()
    configure_logging(settings.log_level)
    return create_app(settings)
