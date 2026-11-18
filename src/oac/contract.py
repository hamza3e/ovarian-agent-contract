"""Agent evidence contract v0.1.

Every agent (pathology report, registry, imaging, ...) returns an ``AgentOutput``. The super-agent only ever
sees this object, so a CT model and an LLM report reader can be combined, audited and evaluated the same way.

Design rules (see DECISIONS.md, 2026-11-18):
- ``not_stated`` is an *answer* ("the source does not contain this"), ``abstained`` is a *refusal*
  ("the agent is not confident enough"). Mixing them hides failures, so they are separate states.
- Raw and calibrated confidence are separate fields: raw is what the model produced, calibrated is what a
  calibrator fitted on held-out sites maps it to. Downstream code must only threshold the calibrated value.
- Evidence spans are verified against the source text by code, never trusted from the model.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "0.1.0"

Modality = Literal["pathology_report", "registry", "imaging", "genomics", "clinical_text"]


class Status(str, Enum):
    answered = "answered"
    not_stated = "not_stated"
    abstained = "abstained"


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(description="Text the agent cites as evidence, as produced by the agent.")
    start: int | None = Field(default=None, ge=0, description="Char offset in the source, set by the verifier.")
    end: int | None = Field(default=None, ge=0)
    match_score: float | None = Field(default=None, ge=0, le=100, description="Fuzzy match score 0-100.")
    verified: bool = Field(default=False, description="True only if code located the quote in the source.")


class FieldResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    status: Status
    value: Any = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence_raw: float | None = Field(default=None, ge=0, le=1)
    confidence_calibrated: float | None = Field(default=None, ge=0, le=1)
    prediction_set: list[Any] | None = Field(
        default=None, description="Conformal prediction set (categorical fields), if computed."
    )
    abstain_reason: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> FieldResult:
        if self.status is Status.answered and self.value is None:
            raise ValueError(f"{self.field}: status 'answered' requires a value")
        if self.status is not Status.answered and self.value is not None:
            raise ValueError(f"{self.field}: only 'answered' fields may carry a value")
        if self.status is Status.abstained and not self.abstain_reason:
            raise ValueError(f"{self.field}: 'abstained' requires abstain_reason")
        return self


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    agent_version: str
    contract_version: str = CONTRACT_VERSION
    model_id: str | None = Field(default=None, description="Pinned model id incl. revision, if any.")
    prompt_sha256: str | None = None
    input_sha256: str
    code_commit: str | None = None
    created_utc: str = Field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).isoformat())


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    site_id: str | None = None
    modality: Modality
    fields: list[FieldResult]
    provenance: Provenance
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_fields(self) -> AgentOutput:
        names = [f.field for f in self.fields]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate fields: {sorted(dupes)}")
        return self

    def get(self, name: str) -> FieldResult | None:
        return next((f for f in self.fields if f.field == name), None)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_schema() -> dict:
    schema = AgentOutput.model_json_schema()
    schema["$id"] = f"https://github.com/hamza3e/ovarian-agent-contract/contract/agent_output-{CONTRACT_VERSION}.json"
    schema["title"] = f"AgentOutput v{CONTRACT_VERSION}"
    return schema


def main() -> None:
    ap = argparse.ArgumentParser(description="Export the AgentOutput JSON Schema")
    ap.add_argument("--schema", type=Path, required=True)
    args = ap.parse_args()
    args.schema.parent.mkdir(parents=True, exist_ok=True)
    args.schema.write_text(json.dumps(json_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.schema}")


if __name__ == "__main__":
    main()
