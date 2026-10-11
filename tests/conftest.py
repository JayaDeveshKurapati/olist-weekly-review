import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from make_synthetic_data import generate  # noqa: E402


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory):
    """One small synthetic dataset shared by the whole test session."""
    return generate(tmp_path_factory.mktemp("raw"), n_orders=3000, seed=7)


@pytest.fixture()
def fresh_copy(synthetic_dir, tmp_path):
    """A private, editable copy of the dataset for tests that break files."""
    import shutil
    dest = tmp_path / "raw"
    shutil.copytree(synthetic_dir, dest)
    return dest
