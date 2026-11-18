import json
from pathlib import Path

import pytest

from oac.data import Report

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def synthetic() -> list[dict]:
    return json.loads((FIX / "synthetic_reports.json").read_text(encoding="utf-8"))["reports"]


@pytest.fixture(scope="session")
def synthetic_reports(synthetic) -> list[Report]:
    return [Report(r["case_id"], "synthetic", r["case_id"].split("-")[1], r["text"]) for r in synthetic]
