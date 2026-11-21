"""JSON Schema the LLM must fill (constrained decoding on vLLM, structured outputs on the Claude API).

This is the *model-facing* schema, not the agent contract. The model may say a field is answered, not stated, or
unclear, and must quote its evidence. Whether the agent finally answers or abstains is decided by code
(evidence verification now, calibrated thresholds later), never by the model alone.

Property order is fixed and matters: constrained decoders emit properties in schema order, which lets
``oac.llm.features`` find each field's value tokens in the generated text.
"""

from __future__ import annotations

from oac.fields import FIELDS, FieldSpec

MODEL_STATUSES = ("answered", "not_stated", "unclear")

# Evidence is a bounded list of short quotes (v0.3). Bounds live in the grammar, so a decoding loop cannot run
# away: in v0.2, free-text evidence ran into the token limit on 15/184 greedy outputs (DECISIONS D24).
MAX_QUOTES = 3
MAX_QUOTE_CHARS = 200
EVIDENCE_SCHEMA = {"type": "array", "items": {"type": "string", "maxLength": MAX_QUOTE_CHARS}, "maxItems": MAX_QUOTES}

# FIGO 1988 stages (TCGA era). Used only by the end-to-end baseline, which is asked to stage directly.
FIGO_1988_STAGES = ("IA", "IB", "IC", "IIA", "IIB", "IIC", "IIIA", "IIIB", "IIIC", "IV")


def _value_schema(spec: FieldSpec) -> dict:
    if spec.kind == "categorical":
        assert spec.allowed is not None
        typed: dict = {"type": "string", "enum": list(spec.allowed)}
    elif spec.kind == "boolean":
        typed = {"type": "boolean"}
    elif spec.kind == "number":
        typed = {"type": "number"}
    else:
        typed = {"type": "integer"}
    return {"anyOf": [typed, {"type": "null"}]}


def _field_schema(spec: FieldSpec) -> dict:
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": list(MODEL_STATUSES)},
            "value": _value_schema(spec),
            "evidence": EVIDENCE_SCHEMA,
        },
        "required": ["status", "value", "evidence"],
        "additionalProperties": False,
    }


def without_length_bounds(schema: object) -> object:
    """Copy of a schema without min/max length and item bounds (the Claude API rejects them; code checks them)."""
    if isinstance(schema, dict):
        return {k: without_length_bounds(v) for k, v in schema.items()
                if k not in ("maxLength", "minLength", "maxItems", "minItems")}
    if isinstance(schema, list):
        return [without_length_bounds(v) for v in schema]
    return schema


def extraction_schema(with_stage: bool = False) -> dict:
    props: dict[str, dict] = {f.name: _field_schema(f) for f in FIELDS}
    if with_stage:
        props["figo_stage"] = {
            "type": "object",
            "properties": {  # reasoning first, so the stage is generated after it
                "reasoning": {"type": "string", "maxLength": 400},
                "value": {"anyOf": [{"type": "string", "enum": list(FIGO_1988_STAGES)}, {"type": "null"}]},
            },
            "required": ["reasoning", "value"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }
