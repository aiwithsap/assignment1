import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SAMPLE_DATA = REPO / "sample-data"


@pytest.fixture
def sample_data() -> Path:
    return SAMPLE_DATA


@pytest.fixture
def sample_data_copy(tmp_path: Path) -> Path:
    """A writable copy of sample-data for tamper tests."""
    target = tmp_path / "sample-data"
    shutil.copytree(SAMPLE_DATA, target)
    return target
