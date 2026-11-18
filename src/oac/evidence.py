"""Deterministic evidence verification: a quote counts only if code can find it in the source text."""

from __future__ import annotations

from rapidfuzz import fuzz

from oac.contract import AgentOutput, EvidenceSpan, Status

MIN_SCORE = 90.0  # fuzzy threshold; OCR text and model quotes differ in spacing/case, rarely more


def locate(quote: str, text: str, min_score: float = MIN_SCORE) -> EvidenceSpan:
    q = quote.strip()
    if len(q) < 3:
        return EvidenceSpan(quote=quote, verified=False, match_score=0.0)
    i = text.find(q)
    if i >= 0:
        return EvidenceSpan(quote=quote, start=i, end=i + len(q), match_score=100.0, verified=True)
    lt, lq = text.lower(), " ".join(q.lower().split())
    i = lt.find(lq)
    if i >= 0:
        return EvidenceSpan(quote=quote, start=i, end=i + len(lq), match_score=100.0, verified=True)
    res = fuzz.partial_ratio_alignment(lq, lt, score_cutoff=min_score)
    if res is None:
        return EvidenceSpan(quote=quote, verified=False, match_score=round(fuzz.partial_ratio(lq, lt), 1))
    return EvidenceSpan(quote=quote, start=res.dest_start, end=res.dest_end, match_score=round(res.score, 1),
                        verified=True)


def verify_output(output: AgentOutput, text: str) -> AgentOutput:
    """Re-locate every evidence quote in ``text``; add a warning for answered fields without verified evidence."""
    warnings = list(output.warnings)
    fields = []
    for f in output.fields:
        spans = [locate(e.quote, text) for e in f.evidence]
        if f.status is Status.answered and not any(s.verified for s in spans):
            warnings.append(f"{f.field}: answered without verified evidence")
        fields.append(f.model_copy(update={"evidence": spans}))
    return output.model_copy(update={"fields": fields, "warnings": warnings})
