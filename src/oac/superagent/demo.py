"""Write a synthetic example card (fake case, invented quotes) to docs/, for the README. No TCGA text involved.

    uv run --extra agent python -m oac.superagent.demo
"""

from __future__ import annotations

import json

from oac.contract import AgentOutput
from oac.data import REPO_ROOT
from oac.fields import FIELD_NAMES
from oac.superagent.graph import build_graph, run_case
from oac.superagent.render import card_fhir, card_html

SYNTHETIC = {  # field -> (value, raw confidence, invented quote)
    "primary_site": ("ovary", 1.0, "Primary ovarian carcinoma"),
    "histotype": ("high_grade_serous", 1.0, "high-grade serous carcinoma"),
    "grade": ("G3", 1.0, "poorly differentiated (grade 3)"),
    "laterality": ("left", 0.8, "Left ovary: involved by carcinoma"),
    "omentum_involvement": (True, 1.0, "Omentum: metastatic carcinoma"),
    "omentum_largest_deposit_cm": (1.5, 0.4, "largest deposit 1.5 cm"),
    "lymph_nodes_positive": (0, 1.0, "Lymph nodes: 0/12 positive"),
    "lymph_nodes_examined": (12, 1.0, "0/12"),
}


def synthetic_output() -> dict:
    fields = []
    for name in FIELD_NAMES:
        if name in SYNTHETIC:
            v, c, q = SYNTHETIC[name]
            fields.append({"field": name, "status": "answered", "value": v, "confidence_raw": c,
                           "evidence": [{"quote": q, "start": 100, "end": 100 + len(q), "verified": True}]})
        elif name == "tube_involvement":
            fields.append({"field": name, "status": "abstained", "abstain_reason": "evidence_not_verified"})
        else:
            fields.append({"field": name, "status": "not_stated", "confidence_raw": 1.0})
    prov = {"agent_name": "llm_extractor.hybrid", "agent_version": "0.3.0", "model_id": "SYNTHETIC EXAMPLE",
            "input_sha256": "0" * 64, "created_utc": "2026-11-24T00:00:00+00:00"}
    out = {"case_id": "SYNTHETIC-0001", "site_id": "XX", "modality": "pathology_report", "fields": fields, "provenance": prov}
    return AgentOutput.model_validate(out).model_dump(mode="json")


def main() -> None:
    rep = synthetic_output()
    registry = {"grade": "G3", "laterality": "bilateral", "figo_stage": "IIIA"}
    state, _ = run_case(build_graph(), {"case_id": rep["case_id"], "site_id": "XX", "report": rep, "registry": registry},
                        reviewer=lambda p: {"decision": "accept_report", "note": "example note: right ovary benign on review"})
    docs = REPO_ROOT / "docs"
    (docs / "example_case_card.html").write_text(card_html(state["card"]), encoding="utf-8")
    (docs / "example_case_card.fhir.json").write_text(json.dumps(card_fhir(state["card"]), indent=1) + "\n", encoding="utf-8")
    print("wrote docs/example_case_card.html and .fhir.json")


if __name__ == "__main__":
    main()
