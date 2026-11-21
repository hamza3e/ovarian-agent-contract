"""Metric definitions on small hand-checked examples."""

import pytest

from oac import metrics as m


def test_gold_outcomes():
    ans = {"field": "grade", "status": "answered", "value": "G3", "confidence_raw": 0.9}
    assert m.gold_outcome("c", "s", ans, {"status": "answered", "value": "G3"}).correct is True
    assert m.gold_outcome("c", "s", ans, {"status": "answered", "value": "G2"}).correct is False
    assert m.gold_outcome("c", "s", ans, {"status": "not_stated", "value": None}).correct is False  # hallucinated
    ns = {"field": "grade", "status": "not_stated", "value": None, "confidence_raw": 1.0}
    assert m.gold_outcome("c", "s", ns, {"status": "not_stated"}).correct is True
    assert m.gold_outcome("c", "s", ns, {"status": "answered", "value": "G3"}).correct is False  # missed
    ab = {"field": "grade", "status": "abstained", "value": None, "abstain_reason": "x"}
    o = m.gold_outcome("c", "s", ab, {"status": "answered", "value": "G3"})
    assert o.decided is False and o.correct is None
    assert m.gold_outcome("c", "s", ans, {"status": "unsure"}) is None
    calib = {**ans, "confidence_calibrated": 0.6}
    assert m.gold_outcome("c", "s", calib, {"status": "answered", "value": "G3"}).confidence == 0.6


def test_value_equality_types():
    assert m.values_equal("x", True, True) and not m.values_equal("x", 1, True)
    assert m.values_equal("x", 3, 3.0) and not m.values_equal("x", 4.5, 4.0)
    assert m.grade_compatible("high_grade", "G3") and m.grade_compatible("G2", "high_grade")
    assert not m.grade_compatible("low_grade", "G3") and not m.grade_compatible(None, "G3")


def test_summary():
    o = [m.Outcome("a", "s", "f", "answered", True, True, 0.9), m.Outcome("b", "s", "f", "answered", True, False, 0.6),
         m.Outcome("c", "s", "f", "abstained", False, None, None)]
    s = m.summarize(o)
    assert s["coverage"] == pytest.approx(2 / 3) and s["selective_accuracy"] == 0.5 and s["errors"] == 1


def test_brier_and_ece():
    assert m.brier([1.0, 0.0], [True, False]) == 0.0
    assert m.brier([0.5, 0.5], [True, False]) == pytest.approx(0.25)
    assert m.ece([0.9] * 10, [True] * 9 + [False]) == pytest.approx(0.0)
    assert m.ece([0.9] * 10, [True] * 5 + [False] * 5, n_bins=1) == pytest.approx(0.4)
    bins = m.reliability_bins([0.1, 0.2, 0.8, 0.9], [False, False, True, True], n_bins=2)
    assert bins == [(pytest.approx(0.15), 0.0, 2), (pytest.approx(0.85), 1.0, 2)]


def test_risk_coverage_and_aurc():
    conf, correct = [0.9, 0.8, 0.7, 0.6], [True, True, False, False]
    rc = m.risk_coverage(conf, correct)
    assert rc == [(0.25, 0.0), (0.5, 0.0), (0.75, pytest.approx(1 / 3)), (1.0, 0.5)]
    assert m.aurc(conf, correct) == pytest.approx(0.25 * (1 / 3) + 0.25 * 0.5)
    assert m.aurc([0.9, 0.1], [True, False]) < m.aurc([0.1, 0.9], [True, False])  # better ranking, lower AURC
    assert m.accuracy_at_coverage(conf, correct, 0.5) == 1.0
    ties = m.risk_coverage([0.5, 0.5], [True, False])
    assert ties == [(1.0, 0.5)]


def test_bootstrap_ci_brackets_point_estimate():
    o = [m.Outcome(f"c{i}", "s", "f", "answered", True, i % 4 != 0, 0.9) for i in range(40)]
    stat = m.weighted_accuracy(o)
    point = stat({f"c{i}": 1 for i in range(40)})
    lo, hi = m.bootstrap_ci([x.case_id for x in o], stat, n_boot=300)
    assert point == 0.75 and lo <= point <= hi and hi - lo < 0.4
    assert m.bootstrap_ci(["a"], lambda c: None, n_boot=5) == (None, None)


def test_ece_bins_keep_ties_together():
    conf = [1.0] * 8 + [0.6, 0.4]
    correct = [True] * 7 + [False] + [True, False]
    bins = m.reliability_bins(conf, correct, n_bins=5)
    assert [b[2] for b in bins] == [2, 8]  # the eight 1.0 predictions stay in one bin
    assert m.ece(conf, correct, n_bins=5) == pytest.approx(0.2 * 0.0 + 0.8 * 0.125)  # bin 1: conf 0.5, acc 0.5
