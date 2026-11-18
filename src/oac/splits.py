"""Site-level splits: developed at one centre, calibrated at a second, tested at unseen centres.

Assignment fixed on 2026-11-18 *before* any model output existed (DECISIONS.md). Test-site reports are locked
for model use until eval/PROTOCOL.md is frozen (eval/PROTOCOL.lock holds its sha256).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from oac.data import REPO_ROOT, Report

Split = Literal["dev", "calibration", "test"]
Purpose = Literal["model", "annotation", "registry"]

DEV_SITES = frozenset({"24", "42", "13"})  # Washington Univ., Christiana, MSK
CALIBRATION_SITES = frozenset({"61", "10", "57"})  # Pittsburgh, MD Anderson, IGC
# every other site is a test site

PROTOCOL = REPO_ROOT / "eval" / "PROTOCOL.md"
PROTOCOL_LOCK = REPO_ROOT / "eval" / "PROTOCOL.lock"


class TestSetLocked(RuntimeError):
    """Raised when model code tries to read test-site reports before the protocol is frozen."""


def split_of(site: str) -> Split:
    if site in DEV_SITES:
        return "dev"
    if site in CALIBRATION_SITES:
        return "calibration"
    return "test"


def protocol_frozen(protocol: Path | None = None, lock: Path | None = None) -> bool:
    # resolved at call time (not as default args) so the module-level paths can be swapped in tests
    protocol = protocol or PROTOCOL
    lock = lock or PROTOCOL_LOCK
    if not (protocol.exists() and lock.exists()):
        return False
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    return lock.read_text(encoding="utf-8").strip() == digest


def select(reports: Iterable[Report], split: Split, purpose: Purpose = "model") -> list[Report]:
    """Reports of one split.

    purpose="annotation" (humans labelling, blind to models) may read any split.
    purpose="model" may read test reports only when the protocol is frozen AND OAC_UNLOCK_TEST=1.
    """
    if split == "test" and purpose == "model":
        if not protocol_frozen():
            raise TestSetLocked("eval/PROTOCOL.md is not frozen (missing or stale eval/PROTOCOL.lock)")
        if os.environ.get("OAC_UNLOCK_TEST") != "1":
            raise TestSetLocked("set OAC_UNLOCK_TEST=1 for the single, final test-site run")
    return [r for r in reports if split_of(r.site) == split]
