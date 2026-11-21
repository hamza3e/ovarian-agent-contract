"""Confidence calibration: map per-field features to P(decision is correct), fitted on calibration sites only.

Features (from raw.jsonl, computed at extraction time):
- self-consistency agreement of k samples with the greedy answer;
- token probability of the generated status and value (log, clipped; missing -> flag);
- evidence match score (answered fields) and number of quote parts;
- decision type (answered / not_stated) and field (one-hot).

Model: L2 logistic regression (Platt-style, with features). Fitted once on calibration-site decisions with
reference labels; then frozen and applied unchanged to test sites (calibration transfer).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from oac.fields import FIELD_NAMES

LOG_FLOOR = -20.0


def featurize(field: str, status: str, feats: dict) -> list[float]:
    agree = feats.get("agreement")
    pj = feats.get("p_joint")
    lp = math.log(max(pj, math.exp(LOG_FLOOR))) if pj is not None else 0.0
    ev = feats.get("evidence_score")
    return [
        1.0 if agree is None else float(agree),
        float(agree is None),
        lp / -LOG_FLOOR,
        float(pj is None),
        (ev or 0.0) / 100.0 if status == "answered" else 0.0,
        float(feats.get("evidence_parts") or 0) if status == "answered" else 0.0,
        float(status == "not_stated"),
        *[float(field == f) for f in FIELD_NAMES],
    ]


FEATURE_NAMES = ["agreement", "agreement_missing", "logp_joint_scaled", "p_joint_missing", "evidence_score",
                 "evidence_parts", "is_not_stated", *[f"field={f}" for f in FIELD_NAMES]]


@dataclass
class Calibrator:
    model: object  # sklearn LogisticRegression
    n_train: int
    train_accuracy: float

    def predict(self, field: str, status: str, feats: dict) -> float:
        return float(self.model.predict_proba([featurize(field, status, feats)])[0][1])  # type: ignore[attr-defined]


def fit(rows: Sequence[tuple[str, str, dict]], correct: Sequence[bool], *, C: float = 1.0, seed: int = 20261121) -> Calibrator:
    """rows: (field, status, features) for decided fields on calibration sites; correct: reference outcome."""
    from sklearn.linear_model import LogisticRegression

    if len(set(correct)) < 2:
        raise ValueError("calibration needs both correct and incorrect decisions")
    X = [featurize(f, s, x) for f, s, x in rows]
    model = LogisticRegression(C=C, max_iter=1000, random_state=seed)
    model.fit(X, [int(c) for c in correct])
    return Calibrator(model, len(rows), sum(correct) / len(correct))


def apply(output: dict, raw: dict, cal: Calibrator) -> dict:
    """Return a copy of an AgentOutput dict with confidence_calibrated set on decided fields."""
    fields = []
    for f in output["fields"]:
        g = dict(f)
        if f["status"] in ("answered", "not_stated"):
            g["confidence_calibrated"] = round(cal.predict(f["field"], f["status"], raw["features"][f["field"]]), 6)
        fields.append(g)
    return {**output, "fields": fields}
