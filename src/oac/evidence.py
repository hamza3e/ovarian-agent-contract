"""Deterministic evidence verification: a quote counts only if code can find it in the source text."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from oac.contract import AgentOutput, EvidenceSpan, Status

MIN_SCORE = 90.0  # fuzzy threshold; OCR text and model quotes differ in spacing/case, rarely more

# Words that change the meaning of a finding. A fuzzy match may differ in OCR noise, never in these
# ("Ovary, right" must not verify against "Ovary, left"; "no tumor" not against "tumor"). DECISIONS D21.
GUARD = re.compile(r"\b(?:left|right|bilateral|both|no|not|non|negative|positive|absent|present|without|"
                   r"free|benign|malignant|metastatic|suspicious|atypical|\d+(?:\.\d+)?)\b", re.I)


def _guard_words(s: str) -> list[str]:
    return [w.lower() for w in GUARD.findall(s)]


def guard_ok(quote: str, matched: str) -> bool:
    """Every meaning-changing word of the quote occurs in the matched source text, the same number of times or more."""
    have = _guard_words(matched)
    return all(have.count(w) >= n for w, n in {w: _guard_words(quote).count(w) for w in _guard_words(quote)}.items())


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
    ok = guard_ok(lq, lt[res.dest_start:res.dest_end])
    return EvidenceSpan(quote=quote, start=res.dest_start, end=res.dest_end, match_score=round(res.score, 1),
                        verified=ok)


SEPARATOR = re.compile(r"\s*(?:\.\.\.|\u2026)\s*")


def locate_parts(quote: str, text: str, min_score: float = MIN_SCORE) -> list[EvidenceSpan]:
    """Split a quote on " ... " (separate places in the report) and locate every part.

    The answer counts as supported only if every part is found (see ``all_verified``).
    """
    parts = [p for p in SEPARATOR.split(quote.strip()) if p.strip()]
    return [locate(p, text, min_score) for p in parts]


def all_verified(spans: list[EvidenceSpan]) -> bool:
    return bool(spans) and all(s.verified for s in spans)


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
