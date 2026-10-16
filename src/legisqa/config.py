"""Application settings.

Settings are read once, at startup, from ``LEGISQA_*`` environment variables (and an
optional ``.env`` file). There is no hot reload: changing a value requires a restart.
"""

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(StrEnum):
    """Deployment profile. ``prod`` is the default and never loads attack fixtures."""

    PROD = "prod"
    DEMO = "demo"
    EVAL = "eval"


class Settings(BaseSettings):
    """Validated, immutable runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LEGISQA_",
        env_file=".env",
        extra="forbid",
        frozen=True,
    )

    profile: Profile = Profile.PROD
    data_dir: Path = Path("sample-data")
    var_dir: Path = Path("var")
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    min_question_chars: int = Field(default=3, ge=1)
    max_question_chars: int = Field(default=500, ge=10, le=5000)
    top_k: int = Field(default=5, ge=1, le=20)

    # Answerability gate: development defaults, tuned on the dev split only.
    gate_min_strength: float = Field(default=0.3, ge=0.0, le=1.0)
    gate_min_margin: float = Field(default=0.0, ge=0.0)
    max_excerpt_sentences: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.min_question_chars >= self.max_question_chars:
            raise ValueError("min_question_chars must be smaller than max_question_chars")
        return self

    @property
    def load_adversarial_overlay(self) -> bool:
        """Attack fixtures are loaded only for demonstration and evaluation."""
        return self.profile in {Profile.DEMO, Profile.EVAL}

    @property
    def expose_security_endpoints(self) -> bool:
        """Security-event and quarantine views would need authentication in production."""
        return self.profile in {Profile.DEMO, Profile.EVAL}
