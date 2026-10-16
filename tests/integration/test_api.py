import json
from pathlib import Path

from fastapi.testclient import TestClient

from legisqa.api import create_app
from legisqa.config import Profile, Settings


def client(tmp_path: Path, data: Path, **kw: object) -> TestClient:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        data_dir=data,
        var_dir=tmp_path / "var",
        frontend_dist=tmp_path / "no-ui",
        **kw,  # type: ignore[arg-type]
    )
    return TestClient(create_app(settings), raise_server_exceptions=False)


def dev_question(data: Path) -> str:
    return str(
        json.loads((data / "questions_dev.jsonl").read_text("utf-8").splitlines()[0])["question"]
    )


def test_answer_contract_and_headers(tmp_path: Path, sample_data: Path) -> None:
    api = client(tmp_path, sample_data)
    response = api.post("/v1/answers", json={"question": dev_question(sample_data)})
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "answered" and body["result"]["citations"]
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_supplied_request_id_is_echoed(tmp_path: Path, sample_data: Path) -> None:
    response = client(tmp_path, sample_data).post(
        "/v1/answers", json={"question": "what is a licence"}, headers={"X-Request-ID": "abc-1"}
    )
    assert response.json()["request_id"] == "abc-1"


def test_rejections_use_the_error_envelope(tmp_path: Path, sample_data: Path) -> None:
    api = client(tmp_path, sample_data)
    for payload, code in [
        ({"question": ""}, "empty"),
        ({"question": "x" * 600}, "too_long"),
        ({"question": "email me at a@example.com"}, "pii_detected"),
        ({"question": "<script>x</script> fee"}, "active_content"),
        ({"question": "fee", "jurisdiction": "mars"}, "invalid_request"),
        ({}, "invalid_request"),
    ]:
        response = api.post("/v1/answers", json=payload)
        assert response.status_code == 422, payload
        body = response.json()
        assert body["outcome"] == "rejected" and body["code"] == code and body["request_id"]


def test_unready_service(tmp_path: Path, sample_data_copy: Path) -> None:
    (sample_data_copy / "manifest.json").unlink()
    api = client(tmp_path, sample_data_copy)
    assert api.get("/healthz").status_code == 200
    ready = api.get("/readyz")
    assert ready.status_code == 503 and not ready.json()["ready"]
    answer = api.post("/v1/answers", json={"question": "what is a licence fee"})
    assert answer.status_code == 503 and answer.json()["code"] == "not_ready"


def test_internal_errors_are_enveloped(tmp_path: Path, sample_data: Path) -> None:
    api = client(tmp_path, sample_data)
    service = api.app.state.service  # type: ignore[attr-defined]

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("bug")

    service.ask = boom
    response = api.post("/v1/answers", json={"question": "what is a licence fee"})
    assert response.status_code == 500
    assert response.json()["outcome"] == "internal_error" and response.json()["code"] is None


def test_profile_gating(tmp_path: Path, sample_data: Path) -> None:
    labels = (sample_data / "adversarial/labels.jsonl").read_text("utf-8").splitlines()
    poisoned = json.loads(labels[0])["chunk_id"]
    prod = client(tmp_path, sample_data)
    assert prod.get("/v1/security-events").status_code in (404, 405)
    assert prod.get(f"/v1/sources/{poisoned}").status_code == 404
    demo = client(tmp_path, sample_data, profile=Profile.DEMO)
    events = demo.get("/v1/security-events")
    assert events.status_code == 200 and len(events.json()) >= 28
    source = demo.get(f"/v1/sources/{poisoned}").json()
    assert source["quarantined"] and source["quarantine_layer"] == "provenance"


def test_sources_and_ui_hint(tmp_path: Path, sample_data: Path) -> None:
    api = client(tmp_path, sample_data)
    assert api.get("/v1/sources/c_ffffffffffff").status_code == 404
    first = json.loads((sample_data / "corpus.jsonl").read_text("utf-8").splitlines()[0])
    source = api.get(f"/v1/sources/{first['chunk_id']}").json()
    assert source["quarantined"] is False and source["chunk"]["text"] == first["text"]
    assert "UI has not been built" in api.get("/").text


def test_built_ui_is_served_with_security_headers(tmp_path: Path, sample_data: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Legislation Q&amp;A</title>", "utf-8")
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=sample_data, var_dir=tmp_path / "var", frontend_dist=dist
    )
    api = TestClient(create_app(settings))
    page = api.get("/")
    assert page.status_code == 200 and "Legislation Q&amp;A" in page.text
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
