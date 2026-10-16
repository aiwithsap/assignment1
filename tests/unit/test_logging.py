import json
import logging

from legisqa.logging_setup import (
    JsonStreamHandler,
    configure_logging,
    fingerprint,
    request_id_var,
)


def _emit(handler: JsonStreamHandler, **extra: object) -> dict[str, object]:
    record = logging.makeLogRecord({"name": "t", "levelname": "INFO", "msg": "hello", **extra})
    for log_filter in handler.filters:
        assert isinstance(log_filter, logging.Filter)
        log_filter.filter(record)
    formatter = handler.formatter
    assert formatter is not None
    return json.loads(formatter.format(record))  # type: ignore[no-any-return]


def test_question_text_is_never_logged() -> None:
    question_text = "my email is someone@example.com"
    line = _emit(JsonStreamHandler(), question=question_text, stage="guard")
    assert question_text not in json.dumps(line)
    assert line["question"] == {"len": len(question_text), "sha256_16": fingerprint(question_text)}
    assert line["stage"] == "guard"


def test_request_id_is_included() -> None:
    token = request_id_var.set("req-123")
    try:
        assert _emit(JsonStreamHandler())["request_id"] == "req-123"
    finally:
        request_id_var.reset(token)


def test_configure_is_idempotent() -> None:
    configure_logging("DEBUG")
    configure_logging("INFO")
    root = logging.getLogger()
    assert sum(isinstance(h, JsonStreamHandler) for h in root.handlers) == 1
    assert root.level == logging.INFO


def test_fingerprint_is_stable() -> None:
    assert fingerprint("abc") == fingerprint("abc")
    assert len(fingerprint("abc")) == 16
