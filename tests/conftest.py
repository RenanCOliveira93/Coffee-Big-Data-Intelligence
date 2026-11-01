import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def sidra_sample():
    return json.loads((FIX / "sidra_pam_sample.json").read_text())


@pytest.fixture
def power_sample():
    return json.loads((FIX / "power_sample.json").read_text())


@pytest.fixture
def lake(tmp_path):
    from coffeebdi.lake import Lake
    lk = Lake(tmp_path / "lake")
    yield lk
    lk.close()


def pytest_collection_modifyitems(config, items):
    from coffeebdi.spark_utils import java_available
    if not java_available():
        skip = pytest.mark.skip(reason="Java/JDK não encontrado")
        for it in items:
            if "spark" in it.keywords:
                it.add_marker(skip)
