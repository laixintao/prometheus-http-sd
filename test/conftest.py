import pytest
from pathlib import Path


@pytest.fixture
def good_root() -> Path:
    good_root = Path(__file__).parent / "good_root"
    return good_root
