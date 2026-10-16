from pathlib import Path

import pytest
from pydantic import ValidationError

from legisqa.config import Profile, Settings


def make(**kwargs: object) -> Settings:
    # _env_file=None keeps a developer's local .env out of the tests.
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg, arg-type]


def test_defaults_are_safe() -> None:
    settings = make()
    assert settings.profile is Profile.PROD
    assert settings.host == "127.0.0.1"
    assert not settings.load_adversarial_overlay
    assert not settings.expose_security_endpoints


@pytest.mark.parametrize("profile", [Profile.DEMO, Profile.EVAL])
def test_demo_and_eval_load_overlay(profile: Profile) -> None:
    settings = make(profile=profile)
    assert settings.load_adversarial_overlay
    assert settings.expose_security_endpoints


def test_environment_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEGISQA_PROFILE", "demo")
    monkeypatch.setenv("LEGISQA_DATA_DIR", "elsewhere")
    settings = make()
    assert settings.profile is Profile.DEMO
    assert settings.data_dir == Path("elsewhere")


@pytest.mark.parametrize(
    "bad",
    [
        {"profile": "staging"},
        {"port": 0},
        {"gate_min_strength": 1.5},
        {"min_question_chars": 600, "max_question_chars": 500},
        {"unknown_setting": 1},
    ],
)
def test_invalid_settings_fail_fast(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make(**bad)


def test_settings_are_immutable() -> None:
    settings = make()
    with pytest.raises(ValidationError):
        settings.top_k = 9
