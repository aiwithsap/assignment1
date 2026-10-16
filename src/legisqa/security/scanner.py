"""Severity policy over detector findings.

Quarantine when any finding is High, or when Medium findings (with two Lows counting as
one Medium) reach two. Low findings alone are only logged.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from legisqa.security.detectors import CONTENT_DETECTORS, Detector, Finding, Severity

MEDIUM_THRESHOLD = 2.0


@dataclass(frozen=True)
class ScanResult:
    findings: tuple[Finding, ...]
    flagged: bool

    @property
    def detectors(self) -> tuple[str, ...]:
        return tuple(sorted({f.detector.value for f in self.findings}))


def apply_policy(findings: Iterable[Finding], high_only: bool = False) -> bool:
    findings = list(findings)
    if any(f.severity is Severity.HIGH for f in findings):
        return True
    if high_only:
        return False
    weight = sum(
        1.0 if f.severity is Severity.MEDIUM else 0.5
        for f in findings
        if f.severity < Severity.HIGH
    )
    return weight >= MEDIUM_THRESHOLD


def scan(
    text: str, detectors: tuple[Detector, ...] = CONTENT_DETECTORS, high_only: bool = False
) -> ScanResult:
    findings = tuple(f for detector in detectors for f in detector(text))
    return ScanResult(findings=findings, flagged=apply_policy(findings, high_only))
