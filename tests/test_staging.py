"""FIGO 1988 rule engine. Cases mirror the study guide's calculator (both must agree)."""

import pytest

from oac.staging import STAGES_1988, StageBound, answered_values, stage_1988


@pytest.mark.parametrize(
    "values, lower",
    [
        ({}, "IA"),
        ({"laterality": "left"}, "IA"),
        ({"laterality": "bilateral"}, "IB"),
        ({"laterality": "left", "ovarian_surface_involvement": True}, "IC"),
        ({"laterality": "left", "peritoneal_cytology": "positive"}, "IC"),
        ({"laterality": "left", "peritoneal_cytology": "atypical"}, "IA"),  # suspicious is not positive
        ({"uterus_involvement": True}, "IIA"),
        ({"tube_involvement": True, "ovarian_surface_involvement": True}, "IIC"),  # 1988-only stage
        ({"omentum_involvement": True}, "IIIA"),  # size unknown: at least microscopic
        ({"omentum_involvement": True, "omentum_largest_deposit_cm": 1.5}, "IIIB"),
        ({"omentum_involvement": True, "omentum_largest_deposit_cm": 4.5}, "IIIC"),
        ({"lymph_nodes_positive": 2, "omentum_involvement": False}, "IIIC"),  # study guide Q1 (2014: IIIA1)
        ({"lymph_nodes_positive": 0, "omentum_involvement": False, "laterality": "bilateral"}, "IB"),
        ({"omentum_involvement": False, "uterus_involvement": False, "laterality": "right"}, "IA"),
    ],
)
def test_lower_bounds(values, lower):
    b = stage_1988(values)
    assert b.lower == lower and b.upper == "IV"


def test_synthetic_report_one_is_at_least_iiic():
    # TCGA-ZZ-0001 (synthetic): bilateral, surface, omentum 4.5 cm, nodes 2/11, washings positive
    b = stage_1988({"laterality": "bilateral", "ovarian_surface_involvement": True, "omentum_involvement": True,
                    "omentum_largest_deposit_cm": 4.5, "lymph_nodes_positive": 2, "peritoneal_cytology": "positive"})
    assert b.lower == "IIIC" and b.basis == ("lymph_nodes_positive",)


def test_bound_contains_and_order():
    assert StageBound("IIIA").contains("IIIC") and StageBound("IIIA").contains("IV")
    assert not StageBound("IIIC").contains("IIC")
    assert STAGES_1988.index("IIC") < STAGES_1988.index("IIIA")


def test_only_answered_fields_count():
    out = {"fields": [
        {"field": "lymph_nodes_positive", "status": "abstained", "value": None},
        {"field": "omentum_involvement", "status": "answered", "value": True},
        {"field": "omentum_largest_deposit_cm", "status": "not_stated", "value": None},
    ]}
    assert stage_1988(answered_values(out)).lower == "IIIA"
