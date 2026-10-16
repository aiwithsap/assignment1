"""Run every check CI runs, in order, and print a PASS / FAIL / SKIPPED table.

Usage:
    uv run python scripts/verify.py [--require-frontend]

A SKIPPED step is never reported as a pass. ``--require-frontend`` (always set in CI)
turns a skipped frontend step into a failure. Exit code is 1 if any step failed.
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DENYLIST = ROOT / "tmp" / "denylist.txt"

# Paths that must never be tracked, and credential shapes that must never appear.
FORBIDDEN_PREFIXES = ("tmp/", "data/raw/", ".env")
ALLOWED_ENV_FILES = {".env.example"}
CREDENTIAL_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
MAX_SCAN_BYTES = 5_000_000


class Status(StrEnum):
    PASS = "PASS"  # noqa: S105 - a status label, not a password
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class StepResult:
    status: Status
    detail: str = ""


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[argparse.Namespace], StepResult]


def _run(cmd: list[str], cwd: Path = ROOT) -> StepResult:
    """Run a command; PASS on exit 0, otherwise FAIL with the tail of its output."""
    print(f"  $ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return StepResult(Status.PASS)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-25:]
    print("\n".join(f"    {line}" for line in tail))
    return StepResult(Status.FAIL, f"exit {proc.returncode}")


def _python(*args: str) -> list[str]:
    return [sys.executable, "-m", *args]


def step_format(_: argparse.Namespace) -> StepResult:
    return _run(_python("ruff", "format", "--check", "."))


def step_lint(_: argparse.Namespace) -> StepResult:
    return _run(_python("ruff", "check", "--no-fix", "."))


def step_types(_: argparse.Namespace) -> StepResult:
    return _run(_python("mypy", "src", "scripts", "tests"))


def step_tests(_: argparse.Namespace) -> StepResult:
    return _run(_python("pytest", "--cov", "--cov-report=term-missing"))


def step_corpus(_: argparse.Namespace) -> StepResult:
    return _run(_python("legisqa", "verify-corpus"))


def step_evaluation(_: argparse.Namespace) -> StepResult:
    """Dev regression floors, AT3-AT5 on the security suite, and frozen-final integrity."""
    return _run(_python("legisqa", "eval", "check"))


def step_frontend(args: argparse.Namespace) -> StepResult:
    npm = shutil.which("npm")
    if npm is None:
        status = Status.FAIL if args.require_frontend else Status.SKIPPED
        return StepResult(status, "npm not found; install Node 20+ to check the UI")
    if not (FRONTEND / "node_modules").is_dir():
        installed = _run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND)
        if installed.status is not Status.PASS:
            return installed
    for script in ("typecheck", "test", "build"):
        result = _run([npm, "run", "--silent", script], cwd=FRONTEND)
        if result.status is not Status.PASS:
            return StepResult(Status.FAIL, f"npm run {script} failed")
    return StepResult(Status.PASS)


def _candidate_files() -> list[str]:
    """Tracked files plus untracked files that are not ignored: everything a commit could hold."""
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted({line for line in proc.stdout.splitlines() if line})


def step_hygiene(_: argparse.Namespace) -> StepResult:
    problems: list[str] = []
    files = _candidate_files()
    for path in files:
        if path in ALLOWED_ENV_FILES:
            continue
        if path.startswith(FORBIDDEN_PREFIXES):
            problems.append(f"must not be committed: {path}")
    deny_terms: list[str] = []
    if DENYLIST.is_file():
        deny_terms = [
            t.strip().lower() for t in DENYLIST.read_text("utf-8").splitlines() if t.strip()
        ]
    for path in files:
        file = ROOT / path
        if not file.is_file() or file.stat().st_size > MAX_SCAN_BYTES:
            continue
        text = file.read_text("utf-8", errors="ignore")
        problems.extend(
            f"credential-like string in {path}"
            for pattern in CREDENTIAL_PATTERNS
            if pattern.search(text)
        )
        lowered = text.lower()
        # Report the file only, never the term: the deny-list itself stays private.
        if any(term in lowered for term in deny_terms):
            problems.append(f"deny-listed reference in {path}")
    if problems:
        print("\n".join(f"    {p}" for p in problems))
        return StepResult(Status.FAIL, f"{len(problems)} problem(s)")
    if not deny_terms:
        return StepResult(Status.PASS, f"{len(files)} files; deny-list absent (local check only)")
    return StepResult(Status.PASS, f"{len(files)} files scanned incl. local deny-list")


STEPS = [
    Step("format", step_format),
    Step("lint", step_lint),
    Step("types", step_types),
    Step("tests", step_tests),
    Step("corpus-integrity", step_corpus),
    Step("evaluation+security", step_evaluation),
    Step("frontend", step_frontend),
    Step("hygiene", step_hygiene),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-frontend",
        action="store_true",
        help="fail (rather than skip) when the frontend cannot be checked",
    )
    args = parser.parse_args(argv)

    results: list[tuple[str, StepResult, float]] = []
    for step in STEPS:
        print(f"[{step.name}]", flush=True)
        started = time.perf_counter()
        result = step.run(args)
        results.append((step.name, result, time.perf_counter() - started))

    print("\nverify summary")
    print(f"{'step':<20} {'status':<8} {'secs':>6}  detail")
    for name, result, secs in results:
        print(f"{name:<20} {result.status:<8} {secs:6.1f}  {result.detail}")
    failed = [name for name, result, _ in results if result.status is Status.FAIL]
    print(f"\n{'FAILED: ' + ', '.join(failed) if failed else 'OK: no failures'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
