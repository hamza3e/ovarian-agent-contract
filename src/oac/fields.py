"""Report-agent schema v0.1: the fields extracted from an ovarian cancer pathology report.

Kept deliberately small (what a pathology report can actually support). FIGO stage is NOT a field here: it
is derived by rules from these fields, because a pathology report alone cannot establish stage IV.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SCHEMA_VERSION = "0.1.0"

Kind = Literal["categorical", "boolean", "number", "count"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: Kind
    description: str
    allowed: tuple[str, ...] | None = None
    silver: str | None = None  # name of the silver label derived from the TCGA clinical table, if any


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "primary_site", "categorical",
        "Site of origin stated or concluded in the report.",
        ("ovary", "fallopian_tube", "peritoneum", "undetermined"),
    ),
    FieldSpec(
        "histotype", "categorical",
        "Histological type of the carcinoma.",
        ("high_grade_serous", "low_grade_serous", "serous_nos", "endometrioid", "clear_cell", "mucinous",
         "carcinosarcoma", "mixed", "other"),
    ),
    FieldSpec(
        "grade", "categorical",
        "Histological grade as written: 3-tier G1-G3 (incl. well/moderately/poorly differentiated) or 2-tier "
        "low/high grade when no 3-tier grade is given.",
        ("G1", "G2", "G3", "low_grade", "high_grade"),
        silver="grade",
    ),
    FieldSpec(
        "laterality", "categorical",
        "Which ovaries contain carcinoma (primary or metastatic).",
        ("left", "right", "bilateral"),
        silver="laterality",
    ),
    FieldSpec("ovarian_surface_involvement", "boolean", "Tumour on the ovarian surface or capsule ruptured/breached."),
    FieldSpec("tube_involvement", "boolean", "Carcinoma in a fallopian tube."),
    FieldSpec("uterus_involvement", "boolean", "Carcinoma in uterus (serosa, myometrium, endometrium) or cervix."),
    FieldSpec("omentum_involvement", "boolean", "Carcinoma in the omentum."),
    FieldSpec("omentum_largest_deposit_cm", "number", "Largest omental tumour deposit, in cm, if measured."),
    FieldSpec("lymph_nodes_positive", "count", "Number of lymph nodes with metastatic carcinoma."),
    FieldSpec("lymph_nodes_examined", "count", "Number of lymph nodes examined."),
    FieldSpec("lymphovascular_invasion", "boolean", "Lymphovascular (lymphatic or vascular) invasion present.",
              silver="lvi"),
    FieldSpec("peritoneal_cytology", "categorical", "Peritoneal washings / ascites cytology result.",
              ("positive", "negative", "atypical")),
    FieldSpec("residual_disease", "categorical",
              "Residual disease after debulking surgery. A surgical finding: usually NOT in pathology reports.",
              ("none_macroscopic", "le_1cm", "gt_1cm")),
)

FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in FIELDS)
BY_NAME: dict[str, FieldSpec] = {f.name: f for f in FIELDS}


def check_value(name: str, value: object) -> bool:
    """True if ``value`` is a legal value for field ``name``."""
    spec = BY_NAME[name]
    if spec.kind == "categorical":
        return isinstance(value, str) and spec.allowed is not None and value in spec.allowed
    if spec.kind == "boolean":
        return isinstance(value, bool)
    if spec.kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    if spec.kind == "count":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return False
