"""FIGO 1988 stage from extracted report findings, by rules (the "rules decide" half of the hybrid design).

A pathology report can establish a *lower bound* only:
- distant metastasis (stage IV: pleural effusion cytology, liver/spleen parenchyma, extra-abdominal) is not in an
  abdominal surgical pathology report;
- schema v0.1 has no field for other pelvic tissues (IIB) or extra-pelvic peritoneum outside the omentum.

So the agent outputs ``>= lower`` with the findings that established it, and the upper bound stays IV. Only
*answered* findings count; ``not_stated`` and ``abstained`` establish nothing. TCGA used FIGO 1988 (DECISIONS D3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

STAGES_1988 = ("IA", "IB", "IC", "IIA", "IIB", "IIC", "IIIA", "IIIB", "IIIC", "IV")
RANK = {s: i for i, s in enumerate(STAGES_1988)}


@dataclass(frozen=True)
class StageBound:
    lower: str
    upper: str = "IV"
    basis: tuple[str, ...] = field(default_factory=tuple)  # findings that set the lower bound

    def contains(self, stage: str) -> bool:
        return RANK[self.lower] <= RANK[stage] <= RANK[self.upper]


def _get(values: dict[str, object], name: str) -> object:
    return values.get(name)


def stage_1988(values: dict[str, object]) -> StageBound:
    """``values``: field name -> answered value (absent or None = not established)."""
    nodes = _get(values, "lymph_nodes_positive")
    omentum = _get(values, "omentum_involvement")
    size = _get(values, "omentum_largest_deposit_cm")
    surface = _get(values, "ovarian_surface_involvement") is True
    cyto = _get(values, "peritoneal_cytology") == "positive"
    pelvic = [n for n in ("tube_involvement", "uterus_involvement") if _get(values, n) is True]

    if isinstance(nodes, int) and nodes > 0:
        return StageBound("IIIC", basis=("lymph_nodes_positive",))
    if omentum is True:
        if isinstance(size, (int, float)) and size > 2:
            return StageBound("IIIC", basis=("omentum_involvement", "omentum_largest_deposit_cm"))
        if isinstance(size, (int, float)):
            return StageBound("IIIB", basis=("omentum_involvement", "omentum_largest_deposit_cm"))
        return StageBound("IIIA", basis=("omentum_involvement",))  # involved, size unknown: at least microscopic
    extra = tuple(n for n, v in (("ovarian_surface_involvement", surface), ("peritoneal_cytology", cyto)) if v)
    if pelvic:
        return StageBound("IIC" if extra else "IIA", basis=tuple(pelvic) + extra)
    both = _get(values, "laterality") == "bilateral"
    if extra:
        return StageBound("IC", basis=extra + (("laterality",) if both else ()))
    if both:
        return StageBound("IB", basis=("laterality",))
    return StageBound("IA", basis=())


def answered_values(output: dict) -> dict[str, object]:
    """AgentOutput (as a dict) -> {field: value} for answered fields only."""
    return {f["field"]: f["value"] for f in output["fields"] if f["status"] == "answered"}
