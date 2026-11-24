"""Super-agent v0 (LangGraph). Synthetic contract outputs only (clearly fake case ids, no report text)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("langgraph")

from oac.contract import AgentOutput  # noqa: E402
from oac.fields import FIELD_NAMES  # noqa: E402
from oac.superagent.graph import build_graph, run_case  # noqa: E402
from oac.superagent.nodes import registry_node, stage_node, uncertainty_node, validate_decision  # noqa: E402
from oac.superagent.render import card_fhir, card_html  # noqa: E402

PROV = {"agent_name": "llm_extractor.hybrid", "agent_version": "0.3.0", "contract_version": "0.1.0",
        "model_id": "synthetic", "prompt_sha256": "0" * 64, "input_sha256": "1" * 64, "code_commit": None,
        "created_utc": "2026-11-24T00:00:00+00:00"}


def output(case_id: str = "TCGA-XX-0001", **answered) -> dict:
    """Synthetic AgentOutput: given fields answered (value, confidence), everything else not_stated."""
    fields = []
    for name in FIELD_NAMES:
        if name in answered:
            value, conf = answered[name]
            if value == "ABSTAIN":
                fields.append({"field": name, "status": "abstained", "abstain_reason": "evidence_not_verified"})
                continue
            fields.append({"field": name, "status": "answered", "value": value, "confidence_raw": conf,
                           "evidence": [{"quote": f"synthetic quote for {name}", "start": 0, "end": 10, "verified": True}]})
        else:
            fields.append({"field": name, "status": "not_stated", "confidence_raw": 1.0})
    out = {"case_id": case_id, "site_id": "XX", "modality": "pathology_report", "fields": fields, "provenance": PROV}
    return AgentOutput.model_validate(out).model_dump(mode="json")  # must satisfy the contract


def case(report: dict, registry: dict | None = None) -> dict:
    return {"case_id": report["case_id"], "site_id": "XX", "report": report, "registry": registry or {}}


def test_clean_case_runs_to_card_without_interrupt():
    rep = output(grade=("G3", 1.0), laterality=("bilateral", 1.0), lymph_nodes_positive=(2, 1.0))
    state, payload = run_case(build_graph(), case(rep, {"grade": "G3", "laterality": "bilateral", "figo_stage": "IIIC"}))
    assert payload is None
    assert state["card"]["status"] == "no_issues"
    assert state["card"]["stage"] == {"lower": "IIIC", "upper": "IV", "basis": ["lymph_nodes_positive"]}


def test_two_tier_grade_and_stage_iv_are_not_conflicts():
    rep = output(grade=("high_grade", 1.0), omentum_involvement=(True, 1.0), omentum_largest_deposit_cm=(5.0, 1.0))
    st = case(rep, {"grade": "G3", "figo_stage": "IV"})
    st |= stage_node(st)
    assert registry_node(st)["conflicts"] == []  # IV is above the report's lower bound IIIC: consistent


def test_conflict_interrupts_and_resume_records_the_review():
    rep = output("TCGA-XX-0002", laterality=("left", 1.0), lymph_nodes_positive=(3, 1.0))
    graph = build_graph()
    state, payload = run_case(graph, case(rep, {"laterality": "bilateral", "figo_stage": "IIC"}))
    assert "card" not in state  # paused at the review node
    kinds = {(i["kind"], i["field"]) for i in payload["conflicts"]}
    assert kinds == {("registry_conflict", "laterality"), ("stage_conflict", "figo_stage")}
    state, _ = run_case(graph, case(rep, {"laterality": "bilateral", "figo_stage": "IIC"}),
                        reviewer=lambda p: {"decision": "accept_report", "note": "right ovary uninvolved"})
    assert state["card"]["status"] == "reviewed"
    assert state["card"]["review"] == {"decision": "accept_report", "note": "right ovary uninvolved"}


def test_defer_keeps_card_open():
    rep = output("TCGA-XX-0003", tube_involvement=("ABSTAIN", None))
    state, payload = run_case(build_graph(), case(rep), reviewer=lambda p: {"decision": "defer"})
    assert payload["flags"][0]["kind"] == "abstained"
    assert state["card"]["status"] == "needs_review"


def test_low_confidence_flag_uses_raw_when_uncalibrated():
    st = case(output(laterality=("right", 0.4)))
    flags = uncertainty_node(st)["flags"]
    assert flags == [{"kind": "low_confidence", "field": "laterality", "detail": "raw confidence 0.40"}]


def test_abstention_outside_staging_fields_is_not_flagged():
    st = case(output(histotype=("ABSTAIN", None)))
    assert uncertainty_node(st)["flags"] == []


def test_invalid_review_is_rejected():
    with pytest.raises(ValueError):
        validate_decision({"decision": "approve"})


def test_fhir_bundle_carries_offsets_not_text():
    rep = output("TCGA-XX-0004", laterality=("left", 1.0), omentum_largest_deposit_cm=(1.5, 0.8), omentum_involvement=(True, 1.0))
    state, _ = run_case(build_graph(), case(rep, {"laterality": "bilateral"}), reviewer=lambda p: {"decision": "defer"})
    bundle = card_fhir(state["card"])
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert types[0] == "DiagnosticReport" and types[-1] == "Provenance"
    assert types.count("Observation") == len(FIELD_NAMES) + 1  # every field + the stage lower bound
    assert types.count("Flag") == 1
    assert "synthetic quote" not in json.dumps(bundle)
    html = card_html(state["card"])
    assert "synthetic quote for laterality" in html and "≥ IIIB" in html
