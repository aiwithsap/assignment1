"""Content detectors. Each is a small pure function: text in, findings out.

Detectors look for features genuine legislation essentially never contains. They run on
a *scan copy* of the text (NFKC-normalised, invisible format characters removed, common
Cyrillic/Greek look-alikes mapped to Latin) so that obfuscation cannot hide a phrase,
while spans are reported against the original text where the detector inspects it directly.
"""

import base64
import binascii
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class DetectorId(StrEnum):
    PROV = "PROV"
    CHR = "CHR"
    ENC = "ENC"
    MKP = "MKP"
    ROLE = "ROLE"
    IMP = "IMP"
    SOC = "SOC"
    STF = "STF"
    STY = "STY"


@dataclass(frozen=True)
class Finding:
    detector: DetectorId
    severity: Severity
    start: int
    end: int
    matched: str
    rule: str


Detector = Callable[[str], list[Finding]]

# --- character-level -------------------------------------------------------------------

_ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
_BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
_TAG_CHARS = re.compile("[\U000e0000-\U000e007f]")
_CONTROL = re.compile("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]")

# Common look-alikes used to disguise Latin words.
_CONFUSABLES = str.maketrans(
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0455\u0406\u0410\u0415\u041e\u0420\u0421\u0425\u03bf\u03b1\u03b5",
    "aeopcyxijsIAEOPCXoae",
)


def scan_copy(text: str) -> str:
    """Normalised text used by the phrase detectors."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return text.translate(_CONFUSABLES)


def _script(ch: str) -> str | None:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    for script in ("LATIN", "CYRILLIC", "GREEK"):
        if name.startswith(script):
            return script
    return None


def detect_characters(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for pattern, severity, rule in (
        (_BIDI, Severity.HIGH, "bidi_control"),
        (_TAG_CHARS, Severity.HIGH, "unicode_tag"),
        (_ZERO_WIDTH, Severity.MEDIUM, "zero_width"),
        (_CONTROL, Severity.MEDIUM, "control_char"),
    ):
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(DetectorId.CHR, severity, match.start(), match.end(), match.group(), rule)
            )
    for match in re.finditer(r"\w+", text):
        scripts = {s for ch in match.group() if (s := _script(ch))}
        if len(scripts) > 1:
            findings.append(
                Finding(
                    DetectorId.CHR,
                    Severity.MEDIUM,
                    match.start(),
                    match.end(),
                    match.group(),
                    "mixed_script",
                )
            )
            break
    return findings


# --- markup and links ------------------------------------------------------------------

ALLOWED_HOST_SUFFIXES = (".gov.au", ".gov")
_TAG = re.compile(r"<\s*/?\s*[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?>")
_EVENT_ATTR = re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE)
_SCHEME = re.compile(r"\b(?:javascript|vbscript|data):", re.IGNORECASE)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")
URL_RE = re.compile(r"\bhttps?://([^/\s?#)]+)", re.IGNORECASE)


def _host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".").split(":")[0]
    return host.endswith(ALLOWED_HOST_SUFFIXES)


def detect_markup(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for pattern, rule in (
        (_TAG, "html_tag"),
        (_EVENT_ATTR, "event_handler"),
        (_SCHEME, "script_scheme"),
        (_MD_IMAGE, "markdown_image"),
        (_MD_LINK, "markdown_link"),
    ):
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(
                    DetectorId.MKP, Severity.HIGH, match.start(), match.end(), match.group(), rule
                )
            )
    for match in URL_RE.finditer(text):
        if not _host_allowed(match.group(1)):
            findings.append(
                Finding(
                    DetectorId.MKP,
                    Severity.HIGH,
                    match.start(),
                    match.end(),
                    match.group(),
                    "external_url",
                )
            )
            break
    return findings


# --- role and delimiter spoofing --------------------------------------------------------

_ROLE_PATTERNS = (
    (re.compile(r"(?:^|\n|[.!?]\s+)\s*(?:system|assistant|developer)\s*:", re.I), "role_label"),
    (re.compile(r"\bSYSTEM\s*:"), "system_label"),
    (re.compile(r"<\|im_(?:start|end)\|>|\[/?INST\]|<<SYS>>"), "chat_template_token"),
    (re.compile(r"#{2,}\s*(?:instruction|system|prompt)\b", re.I), "markdown_role_header"),
    (
        re.compile(r"</?\s*(?:evidence|context|document|system|instructions)\s*>", re.I),
        "wrapper_tag",
    ),
)


def detect_roles(text: str) -> list[Finding]:
    findings = []
    for pattern, rule in _ROLE_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(
                    DetectorId.ROLE, Severity.HIGH, match.start(), match.end(), match.group(), rule
                )
            )
    return findings


# --- AI-directed imperatives -------------------------------------------------------------
# Anchored on model-directed objects ("previous instructions", "system prompt"), not on
# ordinary legislative words such as "direction" or "instructions for continued airworthiness".

_IMPERATIVES = (
    (
        r"\b(?:ignore|disregard|forget|override|bypass)\b[^.;]{0,40}?"
        r"\b(?:previous|prior|above|earlier|all|any|your|the)\b[^.;]{0,30}?"
        r"\b(?:instructions?|rules|guidelines|prompts?)\b",
        "override",
    ),
    (
        r"\byou are now\b|\bdeveloper mode\b|\bjailbreak\b|\bact as an? (?:ai|assistant)\b",
        "persona",
    ),
    (
        r"\b(?:reveal|print|show|repeat|output|display|disclose)\b[^.;]{0,40}?"
        r"\b(?:system prompt|hidden (?:prompt|instructions)|instructions you were given|"
        r"api[ -]?keys?|secret keys?|environment variables)\b",
        "exfiltration",
    ),
    (r"\b(?:respond|reply|answer)\s+only\s+with\b", "output_control"),
    (r"\b(?:answer|respond)\s+without\s+(?:any\s+)?citations?\b", "output_control"),
    (r"\bdo not (?:cite|mention|reference) (?:this|the|any)\b", "output_control"),
    (r"\bcite (?:chunk|source|document)\s+\S+", "citation_forgery"),
    (r"\battribute the answer to\b", "citation_forgery"),
    (
        r"\b(?:call|invoke|use)\b[^.;]{0,25}?\b(?:\w+_\w+|search|read|retrieval)\s+"
        r"(?:tool|function)s?\b",
        "tool_instruction",
    ),
    (r"\b(?:the|this|your) (?:ai|chatbot|language model|llm)\b", "model_reference"),
)
_IMPERATIVE_RES = tuple((re.compile(p, re.IGNORECASE), rule) for p, rule in _IMPERATIVES)


def detect_imperatives(text: str) -> list[Finding]:
    scan = scan_copy(text)
    findings = []
    for pattern, rule in _IMPERATIVE_RES:
        match = pattern.search(scan)
        if match:
            findings.append(
                Finding(
                    DetectorId.IMP, Severity.HIGH, match.start(), match.end(), match.group(), rule
                )
            )
    return findings


# --- social engineering ------------------------------------------------------------------

_REQUEST = r"\b(?:send|e-?mail|provide|verify|confirm|submit|reply with|text|enter)\b"
_SENSITIVE = (
    r"\b(?:tax file number|tfn|password|pin|card number|account number|bsb|bank details|"
    r"login|one-time code)\b"
)
_SOLICITATION = re.compile(
    rf"{_REQUEST}[^.;]{{0,60}}?{_SENSITIVE}|{_SENSITIVE}[^.;]{{0,40}}?{_REQUEST}", re.I
)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:\+?61[\s-]?|0)[2-478](?:[\s-]?\d){8}|1[389]00(?:[\s-]?\d){6}|13(?:[\s-]?\d){4})(?!\d)"
)


def detect_solicitation(text: str) -> list[Finding]:
    scan = scan_copy(text)
    match = _SOLICITATION.search(scan)
    if not match:
        return []
    if not (EMAIL_RE.search(scan) or PHONE_RE.search(scan) or URL_RE.search(scan)):
        return []
    return [
        Finding(
            DetectorId.SOC,
            Severity.HIGH,
            match.start(),
            match.end(),
            match.group(),
            "credential_request",
        )
    ]


# --- encoded payloads ----------------------------------------------------------------------

_BASE64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def _decode(blob: str) -> str | None:
    try:
        raw = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    printable = sum(ch.isprintable() for ch in decoded) / max(len(decoded), 1)
    return decoded if printable > 0.95 and len(decoded) >= 16 else None


def detect_encoded(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in _BASE64.finditer(text):
        decoded = _decode(match.group())
        if decoded is None:
            continue
        inner = [f for detector in _PHRASE_DETECTORS for f in detector(decoded)]
        severity = max((f.severity for f in inner), default=Severity.MEDIUM)
        findings.append(
            Finding(
                DetectorId.ENC, severity, match.start(), match.end(), match.group(), "base64_text"
            )
        )
        break
    return findings


# --- keyword stuffing and register anomaly ---------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")
TANDEM_MIN_REPEATS = 3
TANDEM_MIN_WORDS, TANDEM_MAX_WORDS = 3, 40


def _tandem_repeat(tokens: list[str]) -> tuple[int, int, int]:
    """Longest back-to-back repetition of one word sequence: (repeats, start, length)."""
    best = (1, 0, 0)
    for size in range(TANDEM_MIN_WORDS, min(TANDEM_MAX_WORDS, len(tokens) // 2) + 1):
        for i in range(len(tokens) - 2 * size + 1):
            repeats, j = 1, i
            while (
                j + 2 * size <= len(tokens)
                and tokens[j : j + size] == tokens[j + size : j + 2 * size]
            ):
                repeats, j = repeats + 1, j + size
            if repeats > best[0]:
                best = (repeats, i, size)
    return best


def detect_stuffing(text: str) -> list[Finding]:
    """Keyword stuffing: the same word sequence repeated back-to-back three or more times.

    Plain repetition is not a usable signal in legislation (lists and schedules repeat
    phrases constantly); immediate tandem repetition is (see evidence/verify.md).
    """
    tokens = _WORD.findall(text.lower())
    repeats, start, size = _tandem_repeat(tokens)
    if repeats < TANDEM_MIN_REPEATS:
        return []
    phrase = " ".join(tokens[start : start + size])
    offset = max(text.lower().find(phrase), 0)
    return [
        Finding(
            DetectorId.STF,
            Severity.HIGH,
            offset,
            offset + len(phrase),
            phrase,
            f"tandem_repeat_x{repeats}",
        )
    ]


_URGENCY = re.compile(r"\b(?:urgent|immediately|act now|today|avoid penalties|keep access)\b", re.I)


def detect_register(text: str) -> list[Finding]:
    tokens = _WORD.findall(text.lower())
    second_person = sum(t in {"you", "your", "yours"} for t in tokens)
    signals = []
    if tokens and second_person >= 3 and second_person / len(tokens) > 0.03:
        signals.append("second_person")
    if text.count("!") >= 2:
        signals.append("exclamation")
    if _URGENCY.search(text):
        signals.append("urgency")
    return [Finding(DetectorId.STY, Severity.LOW, 0, 0, "", rule) for rule in signals]


_PHRASE_DETECTORS: tuple[Detector, ...] = (
    detect_roles,
    detect_imperatives,
    detect_solicitation,
    detect_markup,
)

CONTENT_DETECTORS: tuple[Detector, ...] = (
    detect_characters,
    detect_encoded,
    detect_markup,
    detect_roles,
    detect_imperatives,
    detect_solicitation,
    detect_stuffing,
    detect_register,
)

QUESTION_REJECT_DETECTORS: tuple[Detector, ...] = (detect_characters, detect_markup)
QUESTION_LOG_DETECTORS: tuple[Detector, ...] = (detect_imperatives, detect_roles)
OUTPUT_DETECTORS: tuple[Detector, ...] = (
    detect_markup,
    detect_solicitation,
    detect_imperatives,
    detect_characters,
)
