"""LLM report agent: one greedy extraction + k sampled extractions per report, turned into contract outputs.

Two modes share the same model and prompt core:
- ``e2e`` (baseline 2): the greedy answer is taken at face value, including a directly assigned FIGO stage.
  Evidence is verified and reported, but does not change the answer. No calibration, no abstention.
- ``hybrid`` (the system): the model only extracts. Code verifies each evidence quote, computes confidence
  features (self-consistency, token probabilities) and abstains on unverified evidence or "unclear".
  Calibrated thresholds and the FIGO rule engine are applied downstream (oac.calibrate, oac.staging).

Per-sample raw records (model text, features) are written next to the contract outputs so calibration can be
refitted without re-running the model.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from oac.contract import AgentOutput, EvidenceSpan, FieldResult, Provenance, Status, sha256_text
from oac.data import Report
from oac.evidence import locate
from oac.fields import FIELD_NAMES, check_value
from oac.llm.backends import Backend, Completion, Request, parse_json
from oac.llm.features import field_probs
from oac.llm.prompt import Prompt

AGENT_NAME = "llm_extractor"
AGENT_VERSION = "0.1.0"


@dataclass(frozen=True)
class FieldAnswer:
    status: str  # answered | not_stated | unclear | invalid
    value: Any
    evidence: str

    @property
    def key(self) -> tuple[str, str]:
        """Vote key: status plus a canonical value (so 3 and 3.0, True and true compare equal)."""
        v = self.value
        if isinstance(v, bool):
            v = str(v).lower()
        elif isinstance(v, (int, float)):
            v = repr(float(v))
        return self.status, str(v)


def parse_fields(obj: dict | None) -> dict[str, FieldAnswer]:
    """Model JSON -> per-field answers. Anything malformed becomes status 'invalid' (never silently fixed)."""
    out: dict[str, FieldAnswer] = {}
    for name in FIELD_NAMES:
        raw = (obj or {}).get(name)
        if not isinstance(raw, dict) or raw.get("status") not in ("answered", "not_stated", "unclear"):
            out[name] = FieldAnswer("invalid", None, "")
            continue
        status, value, ev = raw["status"], raw.get("value"), raw.get("evidence") or ""
        if status == "answered" and not check_value(name, value):
            out[name] = FieldAnswer("invalid", None, str(ev))
            continue
        out[name] = FieldAnswer(status, value if status == "answered" else None, str(ev))
    return out


def _evidence(quote: str, text: str) -> list[EvidenceSpan]:
    return [locate(quote, text)] if quote.strip() else []


def build_output(report: Report, greedy: Completion, samples: list[Completion], *, mode: str, backend: Backend,
                 prompt: Prompt, code_commit: str | None) -> tuple[AgentOutput, dict]:
    g_obj = parse_json(greedy.text)
    g = parse_fields(g_obj)
    s_parsed = [parse_fields(parse_json(c.text)) for c in samples]
    probs = field_probs(greedy.text, greedy.tokens, list(FIELD_NAMES))

    fields: list[FieldResult] = []
    feats: dict[str, dict] = {}
    warnings: list[str] = []
    if g_obj is None:
        warnings.append(f"greedy output is not valid JSON (finish_reason={greedy.finish_reason})")

    for name in FIELD_NAMES:
        a = g[name]
        spans = _evidence(a.evidence, report.text) if a.status == "answered" else []
        verified = any(s.verified for s in spans)
        votes = Counter(sp[name].key for sp in s_parsed)
        agreement = votes[a.key] / len(s_parsed) if s_parsed else None
        feats[name] = {
            "greedy_status": a.status, "greedy_value": a.value,
            "agreement": agreement, "n_samples": len(s_parsed), "n_distinct": len(votes),
            "evidence_verified": verified, "evidence_score": spans[0].match_score if spans else None,
            "evidence_len": len(a.evidence), **probs[name],
        }

        if a.status == "invalid":
            fr = FieldResult(field=name, status=Status.abstained, abstain_reason="invalid_model_output")
        elif a.status == "unclear":
            fr = FieldResult(field=name, status=Status.abstained, abstain_reason="model_unclear", evidence=spans)
        elif a.status == "not_stated":
            fr = FieldResult(field=name, status=Status.not_stated, confidence_raw=agreement)
        elif mode == "hybrid" and not verified:
            fr = FieldResult(field=name, status=Status.abstained, abstain_reason="evidence_not_verified", evidence=spans)
        else:
            fr = FieldResult(field=name, status=Status.answered, value=a.value, evidence=spans, confidence_raw=agreement)
            if not verified:
                warnings.append(f"{name}: answered without verified evidence")
        fields.append(fr)

    out = AgentOutput(
        case_id=report.case_id, site_id=report.site, modality="pathology_report", fields=fields, warnings=warnings,
        provenance=Provenance(agent_name=f"{AGENT_NAME}.{mode}", agent_version=AGENT_VERSION, model_id=backend.model_id,
                              prompt_sha256=prompt.sha256, input_sha256=sha256_text(report.text), code_commit=code_commit),
    )
    raw = {
        "case_id": report.case_id, "site": report.site, "mode": mode,
        "greedy": {"text": greedy.text, "finish_reason": greedy.finish_reason, "meta": greedy.meta,
                   "tokens_aligned": probs[FIELD_NAMES[0]]["p_status"] is not None},
        "samples": [{"text": c.text, "finish_reason": c.finish_reason, "meta": c.meta} for c in samples],
        "features": feats,
        "figo_stage_e2e": (g_obj or {}).get("figo_stage") if mode == "e2e" else None,
    }
    return out, raw


def run_batch(reports: list[Report], backend: Backend, prompt: Prompt, *, k: int, seed: int, mode: str,
              code_commit: str | None = None) -> list[tuple[AgentOutput, dict]]:
    reqs = [Request(r.case_id, prompt.system, prompt.user(r.text), prompt.schema) for r in reports]
    greedy = backend.generate(reqs, greedy=True, n=1, seed=seed)
    sampled = backend.generate(reqs, greedy=False, n=k, seed=seed) if k > 0 else [[] for _ in reqs]
    return [build_output(r, g[0], s, mode=mode, backend=backend, prompt=prompt, code_commit=code_commit)
            for r, g, s in zip(reports, greedy, sampled, strict=True)]
