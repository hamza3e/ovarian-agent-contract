"""Calibrator on synthetic features: it must learn that low agreement means low accuracy."""

import random

import pytest

pytest.importorskip("sklearn")

from oac import calibrate as cal  # noqa: E402
from oac import metrics as m  # noqa: E402


def _data(n, seed):
    rng = random.Random(seed)
    rows, y = [], []
    for _ in range(n):
        agree = rng.choice([0.2, 0.4, 0.6, 0.8, 1.0])
        p = min(0.98, 0.3 + 0.65 * agree)  # true accuracy rises with agreement
        rows.append(("grade", "answered", {"agreement": agree, "p_joint": None, "evidence_score": 100.0, "evidence_parts": 1}))
        y.append(rng.random() < p)
    return rows, y


def test_calibrator_learns_and_reduces_ece():
    rows, y = _data(600, 1)
    c = cal.fit(rows, y)
    lo = c.predict("grade", "answered", {"agreement": 0.2, "p_joint": None, "evidence_score": 100.0, "evidence_parts": 1})
    hi = c.predict("grade", "answered", {"agreement": 1.0, "p_joint": None, "evidence_score": 100.0, "evidence_parts": 1})
    assert lo < hi
    test_rows, test_y = _data(600, 2)
    raw_conf = [r[2]["agreement"] for r in test_rows]
    cal_conf = [c.predict(*r) for r in test_rows]
    assert m.ece(cal_conf, test_y) < m.ece(raw_conf, test_y)


def test_feature_vector_shape_and_missing_flags():
    v = cal.featurize("grade", "not_stated", {"agreement": None, "p_joint": None})
    assert len(v) == len(cal.FEATURE_NAMES)
    assert v[cal.FEATURE_NAMES.index("agreement_missing")] == 1.0 and v[cal.FEATURE_NAMES.index("is_not_stated")] == 1.0
    assert v[cal.FEATURE_NAMES.index("evidence_score")] == 0.0


def test_fit_refuses_single_class():
    rows, _ = _data(10, 3)
    with pytest.raises(ValueError):
        cal.fit(rows, [True] * 10)


def test_apply_sets_calibrated_only_on_decisions():
    rows, y = _data(200, 4)
    c = cal.fit(rows, y)
    out = {"fields": [{"field": "grade", "status": "answered", "value": "G3"},
                      {"field": "laterality", "status": "abstained", "value": None, "abstain_reason": "x"}]}
    raw = {"features": {"grade": {"agreement": 1.0, "p_joint": 0.9, "evidence_score": 100.0, "evidence_parts": 1},
                        "laterality": {}}}
    res = cal.apply(out, raw, c)
    assert 0 < res["fields"][0]["confidence_calibrated"] < 1 and "confidence_calibrated" not in res["fields"][1]
