import pytest

from oac.agents import rules_baseline
from oac.contract import Status
from oac.fields import FIELD_NAMES, check_value


@pytest.fixture(scope="module")
def outputs(synthetic_reports):
    return {r.case_id: rules_baseline.run(r) for r in synthetic_reports}


def test_every_field_present_and_legal(outputs):
    for out in outputs.values():
        assert [f.field for f in out.fields] == list(FIELD_NAMES)
        for f in out.fields:
            if f.status is Status.answered:
                assert check_value(f.field, f.value), (f.field, f.value)


def test_expected_values(outputs, synthetic):
    for case in synthetic:
        out = outputs[case["case_id"]]
        for name, want in case["expected"].items():
            got = out.get(name)
            if want in ("not_stated", "abstained"):
                assert got.status.value == want, (case["case_id"], name, got)
            else:
                assert got.status is Status.answered and got.value == want, (case["case_id"], name, got)


def test_evidence_offsets_point_into_text(outputs, synthetic_reports):
    texts = {r.case_id: r.text for r in synthetic_reports}
    for cid, out in outputs.items():
        for f in out.fields:
            for e in f.evidence:
                assert texts[cid][e.start:e.end] == e.quote
