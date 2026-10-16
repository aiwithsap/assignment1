"""L5 output guard: re-scan the composed response before it leaves the service.

Backstop for poisoned text that slipped past ingest: markup, external links, credential
solicitation, AI-directed instructions or hidden characters cause an ``unsafe_output``
abstention. Plain-text rendering in the UI stops execution, not phishing; this does.
"""

from legisqa.security.detectors import OUTPUT_DETECTORS, Finding


def check_output(text: str) -> list[Finding]:
    return [f for detector in OUTPUT_DETECTORS for f in detector(text)]
