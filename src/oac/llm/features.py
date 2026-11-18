"""Token-level confidence features: the model's own probability for each field's status and value.

Given the generated JSON text and its tokens (with logprobs), find the character span of
``"<field>": {"status": <here>, "value": <here>`` and sum the logprobs of the tokens that overlap it.
exp(sum) is the probability the model assigned to exactly that status / value, given the text before it.
"""

from __future__ import annotations

import json
import math
import re

_DEC = json.JSONDecoder()


def token_offsets(tokens: list[tuple[str, float]]) -> list[tuple[int, int, float]]:
    out, pos = [], 0
    for tok, lp in tokens:
        out.append((pos, pos + len(tok), lp))
        pos += len(tok)
    return out


def _literal_span(text: str, key: str, start: int) -> tuple[int, int] | None:
    m = re.compile(r'"' + re.escape(key) + r'"\s*:\s*').search(text, start)
    if not m:
        return None
    try:
        _, end = _DEC.raw_decode(text, m.end())
    except json.JSONDecodeError:
        return None
    return m.end(), end


def field_spans(text: str, field: str) -> dict[str, tuple[int, int]]:
    """Char spans of the status and value literals of ``field`` in the generated JSON text."""
    m = re.compile(r'"' + re.escape(field) + r'"\s*:\s*\{').search(text)
    if not m:
        return {}
    spans = {}
    for key in ("status", "value"):
        s = _literal_span(text, key, m.end())
        if s:
            spans[key] = s
    return spans


def span_logprob(offsets: list[tuple[int, int, float]], span: tuple[int, int]) -> float | None:
    a, b = span
    lps = [lp for s, e, lp in offsets if s < b and e > a]
    return sum(lps) if lps else None


def field_probs(text: str, tokens: list[tuple[str, float]] | None, fields: list[str]) -> dict[str, dict[str, float | None]]:
    """For each field: probability of the generated status, of the generated value, and their product."""
    out: dict[str, dict[str, float | None]] = {}
    if not tokens or "".join(t for t, _ in tokens) != text:
        return {f: {"p_status": None, "p_value": None, "p_joint": None} for f in fields}
    offsets = token_offsets(tokens)
    for f in fields:
        spans = field_spans(text, f)
        ls = span_logprob(offsets, spans["status"]) if "status" in spans else None
        lv = span_logprob(offsets, spans["value"]) if "value" in spans else None
        ps = math.exp(ls) if ls is not None else None
        pv = math.exp(lv) if lv is not None else None
        out[f] = {"p_status": ps, "p_value": pv, "p_joint": ps * pv if ps is not None and pv is not None else None}
    return out
