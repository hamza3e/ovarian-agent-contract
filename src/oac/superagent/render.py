"""Case card renderers: a single-file HTML card for a clinician, and FHIR R4-shaped JSON for systems.

The HTML card shows evidence quotes (report text), so it is written only to git-ignored output folders.
The FHIR bundle carries evidence as character offsets plus the report's sha256, never the text itself.
It follows the R4 resource shapes but has not been validated against a FHIR server.
"""

from __future__ import annotations

import html
from typing import Any

EXT = "https://github.com/hamza3e/ovarian-agent-contract/fhir"


def _esc(x: object) -> str:
    return html.escape("" if x is None else str(x))


def card_html(card: dict) -> str:
    rows = []
    for f in card["findings"]:
        if f["status"] == "answered":
            val = _esc(f["value"])
        elif f["status"] == "not_stated":
            val = '<span class="muted">not stated in report</span>'
        else:
            val = f'<span class="warn">abstained: {_esc(f["abstain_reason"])}</span>'
        conf = "" if f["confidence"] is None else f'{f["confidence"]:.2f} ({f["confidence_kind"]})'
        ev = "<br>".join(
            f'“{_esc(e["quote"])}” <span class="muted">[{e["start"]}–{e["end"]}{"" if e["verified"] else ", unverified"}]</span>'
            for e in f["evidence"])
        rows.append(f"<tr><td>{_esc(f['field'])}</td><td>{val}</td><td>{conf}</td><td class='ev'>{ev}</td></tr>")
    issues = card["conflicts"] + card["flags"]
    issue_html = "".join(f"<li><b>{_esc(i['kind'])}</b> · {_esc(i['field'])}: {_esc(i['detail'])}</li>" for i in issues)
    review = card.get("review")
    review_html = (f"<p><b>Clinician review:</b> {_esc(review['decision'])}"
                   f"{' · ' + _esc(review['note']) if review.get('note') else ''}</p>") if review else ""
    st = card["stage"]
    prov = card["provenance"]["report_agent"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Case card {_esc(card['case_id'])}</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;background:#fff;color:#1b1f24;max-width:1000px}}
h1{{font-size:20px;margin:0 0 4px}} .muted{{color:#5a6470}} .warn{{color:#9a3412}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;background:#e5e7eb}}
.badge.needs_review{{background:#fde68a}} .badge.reviewed{{background:#bbf7d0}} .badge.no_issues{{background:#dbeafe}}
.stage{{font-size:18px;margin:10px 0}} table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border-bottom:1px solid #e5e7eb;padding:5px 6px;text-align:left;vertical-align:top}}
td.ev{{font-size:12px;color:#374151}} ul{{padding-left:18px}}
</style></head><body>
<h1>{_esc(card['case_id'])} <span class="badge {card['status']}">{_esc(card['status'].replace('_', ' '))}</span></h1>
<div class="muted">Site {_esc(card.get('site_id'))} · research prototype on public TCGA data, not for clinical use</div>
<div class="stage">FIGO 1988 stage: <b>≥ {_esc(st['lower'])}</b> <span class="muted">(upper bound {_esc(st['upper'])};
set by: {_esc(', '.join(st['basis']) or 'no positive finding')})</span></div>
<h2 style="font-size:15px">Issues for review ({len(issues)})</h2>
<ul>{issue_html or '<li class="muted">none</li>'}</ul>{review_html}
<h2 style="font-size:15px">Findings</h2>
<table><tr><th>Field</th><th>Value</th><th>Confidence</th><th>Evidence (verified offsets)</th></tr>{''.join(rows)}</table>
<p class="muted" style="font-size:12px">Report agent {_esc(prov['agent_name'])} {_esc(prov['agent_version'])} ·
model {_esc(prov.get('model_id'))} · prompt {_esc((prov.get('prompt_sha256') or '')[:12])} ·
graph {_esc(card['provenance']['graph_version'])}</p>
</body></html>"""


def _value(f: dict) -> dict[str, Any]:
    v = f["value"]
    if isinstance(v, bool):
        return {"valueBoolean": v}
    if isinstance(v, int):
        return {"valueInteger": v}
    if isinstance(v, float):
        return {"valueQuantity": {"value": v, "unit": "cm", "system": "http://unitsofmeasure.org", "code": "cm"}}
    return {"valueString": str(v)}


def card_fhir(card: dict) -> dict:
    cid, prov = card["case_id"], card["provenance"]["report_agent"]
    patient = f"Patient/{cid}"
    entries: list[dict] = []
    obs_refs = []
    for f in card["findings"]:
        oid = f"{cid}-{f['field']}"
        obs: dict[str, Any] = {
            "resourceType": "Observation", "id": oid, "status": "preliminary",
            "code": {"text": f["field"]}, "subject": {"reference": patient}, "extension": [],
        }
        if f["status"] == "answered":
            obs.update(_value(f))
        else:
            reason = "not stated in report" if f["status"] == "not_stated" else f"agent abstained: {f['abstain_reason']}"
            obs["dataAbsentReason"] = {"text": reason}
        if f["confidence"] is not None:
            obs["extension"].append({"url": f"{EXT}/confidence-{f['confidence_kind']}", "valueDecimal": f["confidence"]})
        for e in f["evidence"]:
            if e["verified"]:
                obs["extension"].append({"url": f"{EXT}/evidence-offset",
                                         "valueRange": {"low": {"value": e["start"]}, "high": {"value": e["end"]}}})
        if not obs["extension"]:
            del obs["extension"]
        entries.append({"resource": obs})
        obs_refs.append({"reference": f"Observation/{oid}"})
    st = card["stage"]
    entries.append({"resource": {
        "resourceType": "Observation", "id": f"{cid}-figo1988-lower-bound", "status": "preliminary",
        "code": {"text": "FIGO 1988 stage, lower bound from report findings"}, "subject": {"reference": patient},
        "valueString": f">= {st['lower']}", "derivedFrom": [{"reference": f"Observation/{cid}-{b}"} for b in st["basis"]],
    }})
    obs_refs.append({"reference": f"Observation/{cid}-figo1988-lower-bound"})
    for n, issue in enumerate(card["conflicts"] + card["flags"]):
        entries.append({"resource": {
            "resourceType": "Flag", "id": f"{cid}-issue-{n}", "status": "active",
            "code": {"text": f"{issue['kind']}: {issue['field']}: {issue['detail']}"}, "subject": {"reference": patient},
        }})
    entries.insert(0, {"resource": {
        "resourceType": "DiagnosticReport", "id": f"{cid}-agent-findings", "status": "preliminary",
        "code": {"text": "Ovarian cancer pathology report findings (agent-extracted, rule-staged)"},
        "subject": {"reference": patient}, "result": obs_refs,
        "conclusion": f"FIGO 1988 >= {st['lower']}; card status {card['status']}",
    }})
    review = card.get("review")
    entries.append({"resource": {
        "resourceType": "Provenance", "id": f"{cid}-provenance",
        "target": [{"reference": f"DiagnosticReport/{cid}-agent-findings"}],
        "recorded": prov.get("created_utc"),
        "agent": [{"who": {"display": f"{prov['agent_name']}@{prov['agent_version']} ({prov.get('model_id')})"}},
                  {"who": {"display": f"superagent graph@{card['provenance']['graph_version']}"}}]
                 + ([{"who": {"display": f"clinician review: {review['decision']}"}}] if review else []),
        "entity": [{"role": "source", "what": {"display": f"report sha256 {prov['input_sha256']}"}}],
    }})
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}
