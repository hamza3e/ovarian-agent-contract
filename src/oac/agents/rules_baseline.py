"""Baseline 1: regular expressions over sentences. No confidence, no learning.

It exists to answer "do you even need an LLM?" with a number. It is written once, on synthetic examples and
dev-site reports only, and is not tuned on calibration or test sites.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from oac.contract import AgentOutput, EvidenceSpan, FieldResult, Provenance, Status, sha256_text
from oac.data import Report

AGENT_NAME = "rules_baseline"
AGENT_VERSION = "0.1.0"

_NEG = re.compile(
    r"\b(no|not|negative|without|free of|absent|benign|unremarkable|uninvolved)\b", re.I
)
_MALIG = re.compile(r"carcinoma|adenocarcinoma|malignan|metasta|tumou?r (?:is )?(?:present|involv)|involved by", re.I)


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    text: str


def sentences(text: str) -> Iterator[Sentence]:
    for m in re.finditer(r"[^.;\n]+[.;]?", text):
        s = m.group(0)
        if s.strip():
            yield Sentence(m.start(), m.end(), s)


def _span(text: str, start: int, end: int) -> EvidenceSpan:
    return EvidenceSpan(quote=text[start:end], start=start, end=end, match_score=100.0, verified=True)


def _answer(name: str, value: object, spans: list[EvidenceSpan]) -> FieldResult:
    return FieldResult(field=name, status=Status.answered, value=value, evidence=spans)


def _not_stated(name: str) -> FieldResult:
    return FieldResult(field=name, status=Status.not_stated)


def _abstain(name: str, reason: str) -> FieldResult:
    return FieldResult(field=name, status=Status.abstained, abstain_reason=reason)


# ---- grade -------------------------------------------------------------------------------------------------
_GRADE_NUM = re.compile(r"\b(?:histologic(?:al)?\s+|figo\s+)?grade\s*[:\-]?\s*(3|iii|three|2|ii|two|1|i|one)\b", re.I)
_DIFF = re.compile(r"\b(poorly|moderately|well)[\s-]+differentiated\b", re.I)
_TWO_TIER = re.compile(r"\b(high|low)[\s-]+grade\b", re.I)
_NUM = {"3": "G3", "iii": "G3", "three": "G3", "2": "G2", "ii": "G2", "two": "G2", "1": "G1", "i": "G1", "one": "G1"}
_DIFF_MAP = {"poorly": "G3", "moderately": "G2", "well": "G1"}


def grade(text: str) -> FieldResult:
    hits: list[tuple[str, EvidenceSpan]] = []
    for m in _GRADE_NUM.finditer(text):
        hits.append((_NUM[m.group(1).lower()], _span(text, m.start(), m.end())))
    if not hits:
        for m in _DIFF.finditer(text):
            hits.append((_DIFF_MAP[m.group(1).lower()], _span(text, m.start(), m.end())))
    if hits:  # grade by the worst component, as pathologists do
        best = max(hits, key=lambda h: h[0])
        return _answer("grade", best[0], [h[1] for h in hits if h[0] == best[0]][:3])
    m = _TWO_TIER.search(text)
    if m:
        return _answer("grade", f"{m.group(1).lower()}_grade", [_span(text, m.start(), m.end())])
    return _not_stated("grade")


# ---- histotype ---------------------------------------------------------------------------------------------
_HISTO = [
    ("high_grade_serous", re.compile(r"high[\s-]+grade\s+(?:papillary\s+)?serous", re.I)),
    ("low_grade_serous", re.compile(r"low[\s-]+grade\s+(?:papillary\s+)?serous", re.I)),
    ("serous_nos", re.compile(r"serous\s+(?:papillary\s+)?(?:(?:cyst)?adeno)?carcinoma|papillary\s+serous", re.I)),
    ("endometrioid", re.compile(r"endometrioid\s+(?:adeno)?carcinoma", re.I)),
    ("clear_cell", re.compile(r"clear[\s-]+cell\s+(?:adeno)?carcinoma", re.I)),
    ("mucinous", re.compile(r"mucinous\s+(?:cyst)?(?:adeno)?carcinoma", re.I)),
    ("carcinosarcoma", re.compile(r"carcinosarcoma|malignant\s+mixed\s+m[uü]llerian", re.I)),
]


def histotype(text: str) -> FieldResult:
    found: dict[str, EvidenceSpan] = {}
    for name, pat in _HISTO:
        m = pat.search(text)
        if m:
            found[name] = _span(text, m.start(), m.end())
    if "serous_nos" in found and ("high_grade_serous" in found or "low_grade_serous" in found):
        found.pop("serous_nos")  # "high grade serous carcinoma" also matches the generic pattern
    if not found:
        return _not_stated("histotype")
    if len(found) > 1:
        return _answer("histotype", "mixed", list(found.values())[:3])
    (name, span), = found.items()
    return _answer("histotype", name, [span])


# ---- organ involvement by sentence -------------------------------------------------------------------------
def _organ(text: str, name: str, organ: re.Pattern[str]) -> FieldResult:
    pos, neg = [], []
    for s in sentences(text):
        if not organ.search(s.text):
            continue
        if _MALIG.search(s.text) and not _NEG.search(s.text):
            pos.append(_span(text, s.start, s.end))
        elif _NEG.search(s.text):
            neg.append(_span(text, s.start, s.end))
    if pos:
        return _answer(name, True, pos[:3])
    if neg:
        return _answer(name, False, neg[:3])
    return _not_stated(name)


_OMENTUM = re.compile(r"\boment(?:um|al)\b", re.I)
_TUBE = re.compile(r"fallopian|\btubes?\b|salpin", re.I)
_UTERUS = re.compile(r"\buter(?:us|ine)\b|myometri|\bendometrium\b|\bcervix\b", re.I)
_SURFACE = re.compile(r"(?:ovarian|ovary)\s+surface|surface\s+(?:of\s+(?:the\s+)?ovary|involvement)|capsul", re.I)
_OVARY_SIDE = re.compile(r"\b(left|right)\b[^.;]{0,25}\b(?:ovary|ovarian|adnex)|(?:ovary|ovarian|adnex\w*)[,\s]+(left|right)\b",
                         re.I)


def laterality(text: str) -> FieldResult:
    sides: dict[str, list[EvidenceSpan]] = {"left": [], "right": []}
    for s in sentences(text):
        if not (_MALIG.search(s.text) and not _NEG.search(s.text)):
            continue
        for m in _OVARY_SIDE.finditer(s.text):
            side = (m.group(1) or m.group(2)).lower()
            sides[side].append(_span(text, s.start, s.end))
    if sides["left"] and sides["right"]:
        return _answer("laterality", "bilateral", sides["left"][:1] + sides["right"][:1])
    for side in ("left", "right"):
        if sides[side]:
            return _answer("laterality", side, sides[side][:2])
    return _not_stated("laterality")


# ---- lymphovascular invasion -------------------------------------------------------------------------------
_LVI = re.compile(r"(?:lympho-?vascular|lymphatic|vascular|angiolymphatic|lymph-vascular)(?:\s+space)?\s+invasion", re.I)
_LVI_NEG = re.compile(r"\b(no|not|negative|absent|without|none)\b", re.I)


def lvi(text: str) -> FieldResult:
    pos, neg = [], []
    for s in sentences(text):
        if not _LVI.search(s.text):
            continue
        (neg if _LVI_NEG.search(s.text) else pos).append(_span(text, s.start, s.end))
    if pos:
        return _answer("lymphovascular_invasion", True, pos[:2])
    if neg:
        return _answer("lymphovascular_invasion", False, neg[:2])
    return _not_stated("lymphovascular_invasion")


# ---- lymph nodes -------------------------------------------------------------------------------------------
_LN_FRAC = re.compile(r"\(?\b(\d{1,2})\s*(?:/|of)\s*(\d{1,2})\)?\s*(?:lymph\s*)?nodes?", re.I)
_LN_AFTER = re.compile(r"lymph\s*nodes?[^.;]{0,60}?\(\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\)", re.I)


def lymph_nodes(text: str) -> tuple[FieldResult, FieldResult]:
    pos = exam = 0
    spans: list[EvidenceSpan] = []
    seen: set[tuple[int, int]] = set()
    for pat in (_LN_FRAC, _LN_AFTER):
        for m in pat.finditer(text):
            if (m.start(), m.end()) in seen:
                continue
            a, b = int(m.group(1)), int(m.group(2))
            if a > b or b == 0:
                continue
            seen.add((m.start(), m.end()))
            pos, exam = pos + a, exam + b
            spans.append(_span(text, m.start(), m.end()))
    if not spans:
        return _not_stated("lymph_nodes_positive"), _not_stated("lymph_nodes_examined")
    return _answer("lymph_nodes_positive", pos, spans[:4]), _answer("lymph_nodes_examined", exam, spans[:4])


# ---- cytology ----------------------------------------------------------------------------------------------
_CYTO = re.compile(r"washing|cytolog|ascit|peritoneal fluid", re.I)
_CYTO_POS = re.compile(r"positive for (?:malignan|carcinoma|tumou?r)|malignant cells (?:are )?(?:present|identified|seen)|"
                       r"consistent with (?:metastatic )?(?:adeno)?carcinoma", re.I)
_CYTO_NEG = re.compile(r"negative for (?:malignan|carcinoma|tumou?r)|no malignant cells", re.I)
_CYTO_ATYP = re.compile(r"atypical", re.I)


def cytology(text: str) -> FieldResult:
    for s in sentences(text):
        if not _CYTO.search(s.text):
            continue
        if _CYTO_NEG.search(s.text):
            return _answer("peritoneal_cytology", "negative", [_span(text, s.start, s.end)])
        if _CYTO_POS.search(s.text):
            return _answer("peritoneal_cytology", "positive", [_span(text, s.start, s.end)])
        if _CYTO_ATYP.search(s.text):
            return _answer("peritoneal_cytology", "atypical", [_span(text, s.start, s.end)])
    return _not_stated("peritoneal_cytology")


# ---- primary site / residual / omental size ----------------------------------------------------------------
_PRIMARY = [
    ("peritoneum", re.compile(r"primary\s+peritoneal|peritoneal\s+primary", re.I)),
    ("fallopian_tube", re.compile(r"(?:primary\s+(?:fallopian\s+)?tub(?:e|al))|(?:tubal|fallopian tube)\s+primary|"
                                  r"tubal\s+origin", re.I)),
    ("ovary", re.compile(r"primary\s+ovarian|ovarian\s+primary|ovarian\s+origin|primary\s+(?:site|tumou?r)[^.;]{0,20}ovary",
                         re.I)),
]
_RESIDUAL = re.compile(r"residual\s+(?:tumou?r|disease)", re.I)


def primary_site(text: str) -> FieldResult:
    for name, pat in _PRIMARY:
        m = pat.search(text)
        if m:
            return _answer("primary_site", name, [_span(text, m.start(), m.end())])
    return _not_stated("primary_site")


def residual(text: str) -> FieldResult:
    if _RESIDUAL.search(text):
        return _abstain("residual_disease", "mention found; rules baseline cannot interpret it")
    return _not_stated("residual_disease")


def run(report: Report) -> AgentOutput:
    t = report.text
    ln_pos, ln_exam = lymph_nodes(t)
    fields = [
        primary_site(t),
        histotype(t),
        grade(t),
        laterality(t),
        _organ(t, "ovarian_surface_involvement", _SURFACE),
        _organ(t, "tube_involvement", _TUBE),
        _organ(t, "uterus_involvement", _UTERUS),
        _organ(t, "omentum_involvement", _OMENTUM),
        _abstain("omentum_largest_deposit_cm", "rules baseline does not extract sizes"),
        ln_pos,
        ln_exam,
        lvi(t),
        cytology(t),
        residual(t),
    ]
    return AgentOutput(
        case_id=report.case_id,
        site_id=report.site,
        modality="pathology_report",
        fields=fields,
        provenance=Provenance(agent_name=AGENT_NAME, agent_version=AGENT_VERSION, input_sha256=sha256_text(t)),
    )
