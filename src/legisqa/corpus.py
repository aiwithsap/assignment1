"""Load the pinned corpus, verify it against its manifest, and quarantine unsafe chunks.

Ingest runs two layers before anything becomes retrievable:

* **L1 provenance**: each chunk's text must hash to the manifest value recorded for the
  ``version_id`` it claims. Any alteration of a known document fails, whatever its wording.
* **L2 content scan**: deterministic detectors (``legisqa.security``) look for content that
  genuine legislation does not contain.

Quarantined chunks stay visible for audit but are never handed to the retriever.
Any integrity failure raises ``StartupError``; the service then runs unready.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from legisqa.errors import StartupError
from legisqa.models import Chunk
from legisqa.security.detectors import DetectorId, Finding, Severity
from legisqa.security.events import EventAction, EventSource, EventStore, make_event
from legisqa.security.scanner import scan

MANIFEST_SCHEMA_VERSION = 1
CORPUS_FILE = "corpus.jsonl"
OVERLAY_FILE = "adversarial/injected_chunks.jsonl"


@dataclass(frozen=True)
class IngestPolicy:
    """Which ingest layers run. All on in normal operation; switched off only for ablations."""

    provenance: bool = True
    content_scan: bool = True
    high_only: bool = False


@dataclass(frozen=True)
class Quarantined:
    chunk: Chunk
    layer: str  # "provenance" or "content"
    findings: tuple[Finding, ...]


@dataclass
class Corpus:
    version: str
    manifest: dict[str, Any]
    clean: dict[str, Chunk] = field(default_factory=dict)
    quarantined: dict[str, Quarantined] = field(default_factory=dict)
    overlay_loaded: bool = False

    def get(self, chunk_id: str) -> Chunk | None:
        if chunk_id in self.clean:
            return self.clean[chunk_id]
        record = self.quarantined.get(chunk_id)
        return record.chunk if record else None

    def is_quarantined(self, chunk_id: str) -> bool:
        return chunk_id in self.quarantined


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_manifest(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "manifest.json"
    try:
        manifest: dict[str, Any] = json.loads(path.read_text("utf-8"))
    except FileNotFoundError as exc:
        raise StartupError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StartupError(f"manifest is not valid JSON: {exc}") from exc
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise StartupError(
            f"manifest schema {manifest.get('schema_version')} is incompatible with this code "
            f"(expects {MANIFEST_SCHEMA_VERSION})"
        )
    return manifest


def _read_verified(data_dir: Path, rel: str, manifest: dict[str, Any]) -> list[Chunk]:
    path = data_dir / rel
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise StartupError(f"corpus file missing: {rel}") from exc
    expected = manifest.get("files", {}).get(rel)
    if expected is None or _sha256(data) != expected:
        raise StartupError(f"hash mismatch for {rel}: file differs from manifest")
    try:
        return [
            Chunk.model_validate_json(line) for line in data.decode("utf-8").splitlines() if line
        ]
    except ValidationError as exc:
        raise StartupError(f"invalid chunk record in {rel}: {exc.error_count()} error(s)") from exc


def _inserted_span(original: str, altered: str) -> tuple[int, int]:
    """Locate the region of ``altered`` that differs from ``original`` (prefix/suffix diff)."""
    prefix = 0
    while prefix < min(len(original), len(altered)) and original[prefix] == altered[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < min(len(original), len(altered)) - prefix
        and original[-1 - suffix] == altered[-1 - suffix]
    ):
        suffix += 1
    return prefix, len(altered) - suffix


def _provenance_finding(chunk: Chunk, reference: Chunk | None) -> Finding:
    start, end = (
        (0, len(chunk.text)) if reference is None else _inserted_span(reference.text, chunk.text)
    )
    return Finding(
        DetectorId.PROV, Severity.HIGH, start, end, chunk.text[start:end], "hash_mismatch"
    )


def load_corpus(
    data_dir: Path,
    *,
    include_overlay: bool,
    policy: IngestPolicy | None = None,
    events: EventStore | None = None,
) -> Corpus:
    policy = policy or IngestPolicy()
    manifest = _read_manifest(data_dir)
    chunks = _read_verified(data_dir, CORPUS_FILE, manifest)
    if include_overlay:
        chunks += _read_verified(data_dir, OVERLAY_FILE, manifest)

    seen: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_id in seen:
            raise StartupError(f"duplicate chunk_id {chunk.chunk_id}")
        seen.add(chunk.chunk_id)

    expected_hashes: dict[str, str] = manifest.get("chunk_text_sha256", {})
    by_version: dict[str, Chunk] = {}
    for chunk in chunks:
        if expected_hashes.get(chunk.version_id) == _sha256(chunk.text.encode("utf-8")):
            by_version[chunk.version_id] = chunk

    corpus = Corpus(
        version=manifest["corpus_version"], manifest=manifest, overlay_loaded=include_overlay
    )
    for chunk in chunks:
        record: Quarantined | None = None
        digest = _sha256(chunk.text.encode("utf-8"))
        if policy.provenance and expected_hashes.get(chunk.version_id) != digest:
            finding = _provenance_finding(chunk, by_version.get(chunk.version_id))
            record = Quarantined(chunk, "provenance", (finding,))
        elif policy.content_scan:
            result = scan(chunk.text, high_only=policy.high_only)
            if result.flagged:
                record = Quarantined(chunk, "content", result.findings)
        if record is None:
            corpus.clean[chunk.chunk_id] = chunk
            continue
        corpus.quarantined[chunk.chunk_id] = record
        if events is not None:
            for finding in record.findings:
                events.add(
                    make_event(
                        finding,
                        EventSource.CORPUS,
                        EventAction.QUARANTINED,
                        chunk_id=chunk.chunk_id,
                    )
                )
    return corpus
