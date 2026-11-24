"""Graph state and node functions. Pure functions of the state, so they are unit-testable without LangGraph."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from oac.metrics import grade_compatible, values_equal
from oac.staging import RANK, answered_values, stage_1988

# Fields that move the FIGO lower bound; an abstention here means the bound may be too low.
STAGING_FIELDS = frozenset({
    "laterality", "ovarian_surface_involvement", "tube_involvement", "uterus_involvement", "omentum_involvement",
    "omentum_largest_deposit_cm", "lymph_nodes_positive", "peritoneal_cytology",
})
# Report field -> silver (registry) label, compared only when both sides have a value.
REGISTRY_FIELDS = {"grade": "grade", "laterality": "laterality", "lymphovascular_invasion": "lvi"}
LOW_CONFIDENCE = 0.6  # raw self-consistency: fewer than 4 of 5 samples agreed with the greedy answer

Decision = Literal["accept_report", "accept_registry", "defer"]
DECISIONS: tuple[str, ...] = ("accept_report", "accept_registry", "defer")


class Issue(TypedDict):
    kind: str  # registry_conflict | stage_conflict | abstained | low_confidence
    field: str
    detail: str


class CaseState(TypedDict, total=False):
    case_id: str
    site_id: str | None
    report: dict  # AgentOutput as a dict (contract v0.1)
    registry: dict  # silver labels for this case (oac.data.silver_labels); may be empty
    stage: dict  # {"lower": str, "upper": str, "basis": [field, ...]}
    conflicts: list[Issue]
    flags: list[Issue]
    review: dict | None  # {"decision": Decision, "note": str} from a clinician, or None if not needed
    card: dict


def _confidence(f: dict) -> tuple[float | None, str]:
    cal = f.get("confidence_calibrated")
    if cal is not None:
        return cal, "calibrated"
    return f.get("confidence_raw"), "raw"


def stage_node(state: CaseState) -> dict[str, Any]:
    bound = stage_1988(answered_values(state["report"]))
    return {"stage": {"lower": bound.lower, "upper": bound.upper, "basis": list(bound.basis)}}


def registry_node(state: CaseState) -> dict[str, Any]:
    """Report versus registry. A disagreement is a signal for review, not a verdict on which side is wrong."""
    reg = state.get("registry") or {}
    values = answered_values(state["report"])
    conflicts: list[Issue] = []
    for field, silver in REGISTRY_FIELDS.items():
        pred, ref = values.get(field), reg.get(silver)
        if pred is None or ref is None:
            continue
        same = grade_compatible(pred, ref) if field == "grade" else values_equal(field, pred, ref)
        if not same:
            conflicts.append(Issue(kind="registry_conflict", field=field, detail=f"report: {pred}; registry: {ref}"))
    reg_stage, lower = reg.get("figo_stage"), state["stage"]["lower"]
    if reg_stage in RANK and RANK[reg_stage] < RANK[lower]:
        basis = ", ".join(state["stage"]["basis"]) or "none"
        conflicts.append(Issue(kind="stage_conflict", field="figo_stage",
                               detail=f"report findings imply at least {lower} (from {basis}); registry: {reg_stage}"))
    return {"conflicts": conflicts}


def uncertainty_node(state: CaseState) -> dict[str, Any]:
    flags: list[Issue] = []
    for f in state["report"]["fields"]:
        if f["status"] == "abstained" and f["field"] in STAGING_FIELDS:
            flags.append(Issue(kind="abstained", field=f["field"],
                               detail=f"agent abstained ({f.get('abstain_reason')}); stage lower bound may be too low"))
        elif f["status"] == "answered":
            conf, kind = _confidence(f)
            if conf is not None and conf < LOW_CONFIDENCE:
                flags.append(Issue(kind="low_confidence", field=f["field"], detail=f"{kind} confidence {conf:.2f}"))
    return {"flags": flags}


def needs_review(state: CaseState) -> Literal["review", "card"]:
    return "review" if state.get("conflicts") or state.get("flags") else "card"


def validate_decision(resume: object) -> dict:
    if not isinstance(resume, dict) or resume.get("decision") not in DECISIONS:
        raise ValueError(f"review must be {{'decision': one of {DECISIONS}, 'note': str}}, got {resume!r}")
    return {"decision": resume["decision"], "note": str(resume.get("note") or "")}


def card_node(state: CaseState) -> dict[str, Any]:
    from oac.superagent import GRAPH_VERSION

    report = state["report"]
    findings = []
    for f in report["fields"]:
        conf, kind = _confidence(f)
        findings.append({
            "field": f["field"], "status": f["status"], "value": f.get("value"),
            "confidence": conf, "confidence_kind": kind if conf is not None else None,
            "abstain_reason": f.get("abstain_reason"),
            "evidence": [{"quote": e["quote"], "start": e.get("start"), "end": e.get("end"), "verified": e.get("verified")}
                         for e in f.get("evidence", [])],
        })
    review = state.get("review")
    if state.get("conflicts") or state.get("flags"):
        status = "reviewed" if review and review["decision"] != "defer" else "needs_review"
    else:
        status = "no_issues"
    return {"card": {
        "case_id": state["case_id"], "site_id": state.get("site_id"), "status": status,
        "stage": state["stage"], "conflicts": state.get("conflicts", []), "flags": state.get("flags", []),
        "review": review, "findings": findings, "registry": state.get("registry") or {},
        "provenance": {"report_agent": report["provenance"], "graph_version": GRAPH_VERSION},
    }}
