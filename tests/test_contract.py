import jsonschema
import pytest
from pydantic import ValidationError

from oac.contract import AgentOutput, FieldResult, Provenance, Status, json_schema, sha256_text


def _prov() -> Provenance:
    return Provenance(agent_name="t", agent_version="0", input_sha256=sha256_text("x"))


def test_answered_requires_value():
    with pytest.raises(ValidationError):
        FieldResult(field="grade", status=Status.answered)


def test_not_stated_must_not_carry_value():
    with pytest.raises(ValidationError):
        FieldResult(field="grade", status=Status.not_stated, value="G3")


def test_abstained_requires_reason():
    with pytest.raises(ValidationError):
        FieldResult(field="grade", status=Status.abstained)
    FieldResult(field="grade", status=Status.abstained, abstain_reason="low confidence")


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        FieldResult(field="grade", status=Status.answered, value="G3", confidence_raw=1.2)


def test_duplicate_fields_rejected():
    f = FieldResult(field="grade", status=Status.not_stated)
    with pytest.raises(ValidationError):
        AgentOutput(case_id="c", modality="pathology_report", fields=[f, f], provenance=_prov())


def test_extra_keys_rejected():
    with pytest.raises(ValidationError):
        FieldResult(field="grade", status=Status.not_stated, colour="red")


def test_json_schema_validates_real_output():
    out = AgentOutput(
        case_id="c", modality="imaging", provenance=_prov(),
        fields=[FieldResult(field="pcs_response", status=Status.answered, value="responder",
                            confidence_raw=0.7, confidence_calibrated=0.62)],
    )
    jsonschema.validate(out.model_dump(mode="json"), json_schema())
