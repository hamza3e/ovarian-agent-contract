"""Evaluation metrics: per-field decision outcomes, calibration (ECE, Brier), selective prediction (risk-coverage,
AURC) and case-level bootstrap confidence intervals.

A *decision* is a contract status that commits to something: ``answered`` (a value) or ``not_stated`` (the
report does not say). ``abstained`` is not a decision; it lowers coverage instead of accuracy.

Reference labels:
- gold (human): ``{"status": "answered"|"not_stated"|"unsure", "value": ...}``; ``unsure`` is excluded;
- silver (registry): a value or None. A registry value does not mean the report states it, so silver is only
  used to check answered values ("agree / disagree / not answered"), never to score ``not_stated``.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

# 3-tier -> 2-tier (MD Anderson convention for serous carcinoma: G1 low grade, G2-G3 high grade)
TWO_TIER = {"G1": "low_grade", "G2": "high_grade", "G3": "high_grade", "low_grade": "low_grade", "high_grade": "high_grade"}


def values_equal(field: str, pred: object, ref: object) -> bool:
    if isinstance(ref, bool) or isinstance(pred, bool):
        return pred is ref
    if isinstance(ref, (int, float)) and isinstance(pred, (int, float)):
        return abs(float(pred) - float(ref)) < 1e-9
    return pred == ref


def grade_compatible(pred: object, ref: object) -> bool:
    """Same grade on the 2-tier scale (used only for silver comparisons, reported next to strict agreement)."""
    return pred in TWO_TIER and ref in TWO_TIER and TWO_TIER[pred] == TWO_TIER[ref]  # type: ignore[index]


@dataclass(frozen=True)
class Outcome:
    case_id: str
    site: str
    field: str
    status: str  # predicted contract status
    decided: bool  # answered or not_stated
    correct: bool | None  # None when not decided
    confidence: float | None


def gold_outcome(case_id: str, site: str, pred: dict, ref: dict) -> Outcome | None:
    """Compare one predicted FieldResult (dict) with one gold label. None if the gold label is unusable."""
    if not ref or ref.get("status") not in ("answered", "not_stated"):
        return None
    status = pred["status"]
    conf = pred.get("confidence_calibrated")
    conf = pred.get("confidence_raw") if conf is None else conf
    if status == "abstained":
        return Outcome(case_id, site, pred["field"], status, False, None, conf)
    if status == "not_stated":
        ok = ref["status"] == "not_stated"
    else:
        ok = ref["status"] == "answered" and values_equal(pred["field"], pred["value"], ref["value"])
    return Outcome(case_id, site, pred["field"], status, True, ok, conf)


def summarize(outcomes: Sequence[Outcome]) -> dict[str, float | int | None]:
    n = len(outcomes)
    dec = [o for o in outcomes if o.decided]
    correct = sum(bool(o.correct) for o in dec)
    return {
        "n": n,
        "coverage": len(dec) / n if n else None,
        "selective_accuracy": correct / len(dec) if dec else None,
        "abstention_rate": (n - len(dec)) / n if n else None,
        "errors": len(dec) - correct,
    }


# ------------------------------------------------------------------------------------------- calibration
def brier(conf: Sequence[float], correct: Sequence[bool]) -> float:
    return sum((c - float(y)) ** 2 for c, y in zip(conf, correct, strict=True)) / len(conf)


def _bins(conf: Sequence[float], correct: Sequence[bool], n_bins: int) -> list[list[tuple[float, bool]]]:
    """Equal-count bins that never split identical confidences (ties are common: many fields have agreement 1.0)."""
    pairs = sorted(zip(conf, correct, strict=True))
    if not pairs:
        raise ValueError("no predictions")
    target = len(pairs) / n_bins
    bins: list[list[tuple[float, bool]]] = [[]]
    for i, p in enumerate(pairs):
        bins[-1].append(p)
        nxt = pairs[i + 1][0] if i + 1 < len(pairs) else None
        if len(bins[-1]) >= target and nxt is not None and nxt != p[0]:
            bins.append([])
    return [b for b in bins if b]


def ece(conf: Sequence[float], correct: Sequence[bool], n_bins: int = 10) -> float:
    """Expected calibration error with equal-count (adaptive), tie-preserving bins."""
    n = len(conf)
    return sum(abs(sum(c for c, _ in b) / len(b) - sum(float(y) for _, y in b) / len(b)) * len(b) / n
               for b in _bins(conf, correct, n_bins))


def reliability_bins(conf: Sequence[float], correct: Sequence[bool], n_bins: int = 10) -> list[tuple[float, float, int]]:
    """(mean confidence, accuracy, count) per bin, for reliability diagrams."""
    return [(sum(c for c, _ in b) / len(b), sum(float(y) for _, y in b) / len(b), len(b)) for b in _bins(conf, correct, n_bins)]


# ------------------------------------------------------------------------------------------- selective prediction
def risk_coverage(conf: Sequence[float], correct: Sequence[bool]) -> list[tuple[float, float]]:
    """(coverage, risk) after keeping the k most confident decisions, k = 1..n. Ties are kept together."""
    pairs = sorted(zip(conf, correct, strict=True), key=lambda p: -p[0])
    n, out, errors, i = len(pairs), [], 0, 0
    while i < n:
        j = i
        while j < n and pairs[j][0] == pairs[i][0]:
            errors += not pairs[j][1]
            j += 1
        out.append((j / n, errors / j))
        i = j
    return out


def aurc(conf: Sequence[float], correct: Sequence[bool]) -> float:
    """Area under the risk-coverage curve (step function over coverage). Lower is better."""
    area, prev = 0.0, 0.0
    for cov, risk in risk_coverage(conf, correct):
        area += (cov - prev) * risk
        prev = cov
    return area


def accuracy_at_coverage(conf: Sequence[float], correct: Sequence[bool], target: float) -> float | None:
    best = None
    for cov, risk in risk_coverage(conf, correct):
        if cov <= target + 1e-12:
            best = 1 - risk
    return best


# ------------------------------------------------------------------------------------------- uncertainty
def bootstrap_ci(case_ids: Sequence[str], stat: Callable[[dict[str, int]], float | None], *, n_boot: int = 1000,
                 seed: int = 20261121, alpha: float = 0.05) -> tuple[float | None, float | None]:
    """Percentile CI from resampling *cases* (all fields of a case move together).

    ``stat`` receives the resampled multiset of case ids as {case_id: multiplicity}.
    """
    uniq = sorted(set(case_ids))
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        sample = [uniq[rng.randrange(len(uniq))] for _ in uniq]
        counts: dict[str, int] = {}
        for c in sample:
            counts[c] = counts.get(c, 0) + 1
        v = stat(counts)
        if v is not None:
            vals.append(v)
    if not vals:
        return None, None
    vals.sort()
    lo = vals[int(alpha / 2 * (len(vals) - 1))]
    hi = vals[int((1 - alpha / 2) * (len(vals) - 1))]
    return lo, hi


def weighted_accuracy(outcomes: Iterable[Outcome]) -> Callable[[dict[str, int]], float | None]:
    """Statistic for ``bootstrap_ci``: selective accuracy over the resampled cases."""
    dec = [o for o in outcomes if o.decided]

    def f(counts: dict[str, int]) -> float | None:
        num = den = 0
        for o in dec:
            w = counts.get(o.case_id, 0)
            num += w * bool(o.correct)
            den += w
        return num / den if den else None

    return f
