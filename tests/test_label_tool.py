"""Label tool (labeling/template.html): active-time timer logic, checked with node when it is available."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[1] / "labeling" / "template.html"


def _snippet(name: str) -> str:
    src = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(rf"function {name}\(.*?\n}}\n", src, re.S)
    assert m, name
    consts = re.search(r"const IDLE_MS = .*?;\n", src).group(0)
    return consts + m.group(0)


def test_template_has_payload_slot_and_timer():
    src = TEMPLATE.read_text(encoding="utf-8")
    assert src.count("__PAYLOAD__") == 1
    assert 'id="timer"' in src and "visibilitychange" in src


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_active_step():
    cases = {  # (now, lastTick, lastInput, visible, focused) -> ms counted
        "active": ([10_000, 9_000, 9_500, True, True], 1000),
        "hidden tab": ([10_000, 9_000, 9_500, False, True], 0),
        "other window focused": ([10_000, 9_000, 9_500, True, False], 0),
        "idle 2 min": ([200_000, 199_000, 80_000, True, True], 0),
        "idle just under 2 min": ([200_000, 199_000, 80_001, True, True], 1000),
        "laptop slept 1 h": ([3_600_000, 0, 3_599_000, True, True], 5000),
        "clock went back": ([1_000, 2_000, 1_000, True, True], 0),
    }
    args = json.dumps([a for a, _ in cases.values()])
    js = _snippet("activeStep") + f"console.log(JSON.stringify({args}.map(a => activeStep(...a))));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [want for _, want in cases.values()]


def test_practice_cases_are_unscored_dev_reports():
    from oac.annotate import GOLD_FILE, PRACTICE_FILE
    from oac.splits import DEV_SITES

    practice = json.loads(PRACTICE_FILE.read_text(encoding="utf-8"))["cases"]
    spec = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    scored = {c for part in spec["gold"].values() for c in part} | set(spec["pathologist_overlap"])
    assert practice and len(set(practice)) == len(practice)
    assert all(c.split("-")[1] in DEV_SITES for c in practice)
    assert not scored & set(practice)
