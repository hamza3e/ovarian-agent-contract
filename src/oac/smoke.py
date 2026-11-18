"""Smoke run for CI: baseline agent on synthetic reports, contract + JSON Schema validation. No data, no API key."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from oac.agents import rules_baseline
from oac.contract import json_schema
from oac.data import REPO_ROOT, Report
from oac.evidence import verify_output

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "synthetic_reports.json"


def main(path: Path = FIXTURES) -> None:
    schema = json_schema()
    cases = json.loads(path.read_text(encoding="utf-8"))["reports"]
    for c in cases:
        rep = Report(c["case_id"], "synthetic", c["case_id"].split("-")[1], c["text"])
        out = verify_output(rules_baseline.run(rep), rep.text)
        jsonschema.validate(out.model_dump(mode="json"), schema)
        answered = sum(f.status.value == "answered" for f in out.fields)
        print(f"{rep.case_id}: {answered}/{len(out.fields)} answered, warnings={len(out.warnings)}")
    print("smoke ok")


if __name__ == "__main__":
    main()
