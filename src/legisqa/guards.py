"""L3 input guard: reject unusable or unsafe questions before any retrieval.

Rejections (HTTP 422): empty, too long, personal information, active content (markup,
invisible or deceptive characters). Linguistic injection ("ignore your rules") is not
rejected: with no model in the product there is nothing to hijack, so it is returned as
findings to be logged as security events while the request continues.
"""

import re

from legisqa.config import Settings
from legisqa.errors import RejectionCode, RejectionError
from legisqa.security.detectors import (
    EMAIL_RE,
    PHONE_RE,
    QUESTION_LOG_DETECTORS,
    QUESTION_REJECT_DETECTORS,
    Finding,
)

_TFN = re.compile(r"(?<!\d)\d{3}[ -]?\d{3}[ -]?\d{3}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_TFN_WEIGHTS = (1, 4, 3, 7, 5, 8, 6, 9, 10)


def is_valid_tfn(digits: str) -> bool:
    """Australian tax file number check digit (9-digit form)."""
    if len(digits) != 9 or not digits.isdigit():
        return False
    return sum(int(d) * w for d, w in zip(digits, _TFN_WEIGHTS, strict=True)) % 11 == 0


def passes_luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def contains_pii(text: str) -> bool:
    if EMAIL_RE.search(text) or PHONE_RE.search(text):
        return True
    if any(is_valid_tfn(_digits(m.group())) for m in _TFN.finditer(text)):
        return True
    return any(passes_luhn(_digits(m.group())) for m in _CARD.finditer(text))


def check_question(question: str, settings: Settings) -> list[Finding]:
    """Raise ``RejectionError`` for unacceptable input; return injection findings to log."""
    if len(question.strip()) < settings.min_question_chars:
        raise RejectionError(RejectionCode.EMPTY, "The question is empty or too short.")
    if len(question) > settings.max_question_chars:
        raise RejectionError(
            RejectionCode.TOO_LONG,
            f"The question is longer than {settings.max_question_chars} characters.",
        )
    if any(detector(question) for detector in QUESTION_REJECT_DETECTORS):
        raise RejectionError(
            RejectionCode.ACTIVE_CONTENT,
            "The question contains markup, links or hidden characters. Please send plain text.",
        )
    if contains_pii(question):
        raise RejectionError(
            RejectionCode.PII_DETECTED,
            "The question appears to contain personal information. Please remove it.",
        )
    return [f for detector in QUESTION_LOG_DETECTORS for f in detector(question)]
