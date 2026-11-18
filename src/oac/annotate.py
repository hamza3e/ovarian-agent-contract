"""Gold-set sampling and the offline labelling tool.

    python -m oac.annotate sample                       # -> configs/gold_sample.json (case ids only)
    python -m oac.annotate build --annotator NAME --set gold|pathologist
                                                        # -> labeling/out/label_<set>_<NAME>.html (git-ignored)

Humans label blind to model outputs; the tool never shows registry (silver) values.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from oac.data import REPO_ROOT, load_ov_reports
from oac.fields import FIELDS, SCHEMA_VERSION
from oac.splits import select

SEED = 20261118
GOLD_TARGET = {"dev": 15, "calibration": 20, "test": 35}
PATHOLOGIST_N = 15  # drawn from the test part of the gold set
GOLD_FILE = REPO_ROOT / "configs" / "gold_sample.json"
TEMPLATE = REPO_ROOT / "labeling" / "template.html"
OUT_DIR = REPO_ROOT / "labeling" / "out"
GUIDELINE_VERSION = "0.1"

# Short per-field rules shown inside the tool (full guide: docs/ANNOTATION_GUIDE.md).
RULES: dict[str, str] = {
    "primary_site": "ovary if the diagnosis is an ovarian carcinoma and no other origin is suggested; tube/peritoneum "
                    "only if stated; undetermined if the report says origin is unclear (e.g. 'tubo-ovarian', 'Mullerian').",
    "histotype": "As written. 'Serous carcinoma, poorly differentiated' = serous_nos (grade goes to the grade field). "
                 "high_grade_serous only if the words 'high grade serous' appear.",
    "grade": "G1/G2/G3 from 'grade 1-3' or well/moderately/poorly differentiated. Several grades: take the highest. "
             "Use high_grade/low_grade only if no 3-tier grade is given. Only nuclear grade given: use it, note 'nuclear'.",
    "laterality": "Which ovaries contain carcinoma (primary or metastatic). Side cannot be told: not stated.",
    "ovarian_surface_involvement": "Yes: surface involvement, tumour on surface, capsule ruptured/breached. "
                                   "No: capsule intact / no surface involvement.",
    "tube_involvement": "Yes: carcinoma (incl. STIC, note it) in a tube. No: tube examined and free of tumour.",
    "uterus_involvement": "Serosa, myometrium, endometrium or cervix involved by carcinoma. No: uterus free of tumour.",
    "omentum_involvement": "Yes: carcinoma in omentum (any size). No: omentum examined and negative.",
    "omentum_largest_deposit_cm": "Largest dimension of the largest omental TUMOUR deposit in cm (not the omentum "
                                  "specimen size). Microscopic only: not stated + note 'microscopic'.",
    "lymph_nodes_positive": "Sum over all node groups ('2/11' -> 2). Positive but count missing: unsure + note.",
    "lymph_nodes_examined": "Sum over all node groups ('2/11' -> 11).",
    "lymphovascular_invasion": "Yes: lymphovascular / lymphatic / vascular / angiolymphatic invasion present. "
                               "No: explicitly absent. Otherwise not stated.",
    "peritoneal_cytology": "Washings / ascites / peritoneal fluid. Suspicious = atypical.",
    "residual_disease": "Only if the report states disease left after surgery. 'Optimal' = le_1cm, 'suboptimal' = "
                        "gt_1cm (note it). Usually NOT stated in pathology reports: that is the expected answer.",
}


def _allocate(counts: dict[str, int], target: int) -> dict[str, int]:
    """Largest-remainder allocation with at least one case per site (if the target allows)."""
    sites = sorted(counts, key=lambda s: (-counts[s], s))
    alloc = {s: 0 for s in sites}
    base = sites if len(sites) <= target else sites[:target]
    for s in base:
        alloc[s] = 1
    rest = target - sum(alloc.values())
    if rest > 0:
        total = sum(counts[s] - alloc[s] for s in sites)
        quotas = {s: rest * (counts[s] - alloc[s]) / total for s in sites}
        for s in sites:
            alloc[s] += int(quotas[s])
        left = target - sum(alloc.values())
        for s in sorted(sites, key=lambda s: -(quotas[s] - int(quotas[s])))[:left]:
            alloc[s] += 1
    return {s: min(alloc[s], counts[s]) for s in sites if alloc[s]}


def sample() -> dict:
    reports = load_ov_reports()
    rng = random.Random(SEED)
    gold: dict[str, list[str]] = {}
    for split, target in GOLD_TARGET.items():
        by_site: dict[str, list[str]] = defaultdict(list)
        for r in select(reports, split, purpose="annotation"):
            by_site[r.site].append(r.case_id)
        alloc = _allocate({s: len(v) for s, v in by_site.items()}, target)
        chosen = []
        for site in sorted(alloc):
            chosen += rng.sample(sorted(by_site[site]), alloc[site])
        gold[split] = sorted(chosen)
    test_by_site: dict[str, list[str]] = defaultdict(list)
    for cid in gold["test"]:
        test_by_site[cid.split("-")[1]].append(cid)
    order = sorted(test_by_site, key=lambda s: (-len(test_by_site[s]), s))
    patho: list[str] = []
    while len(patho) < PATHOLOGIST_N:  # round-robin over sites, so the overlap spans centres
        for s in order:
            if test_by_site[s] and len(patho) < PATHOLOGIST_N:
                patho.append(test_by_site[s].pop(rng.randrange(len(test_by_site[s]))))
    out = {"seed": SEED, "schema_version": SCHEMA_VERSION, "gold": gold, "pathologist_overlap": sorted(patho)}
    GOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    GOLD_FILE.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def build(annotator: str, which: str) -> Path:
    spec = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    ids = [c for part in spec["gold"].values() for c in part] if which == "gold" else spec["pathologist_overlap"]
    texts = {r.case_id: r.text for r in load_ov_reports()}
    rng = random.Random(f"{SEED}-{which}")
    ids = sorted(ids)
    rng.shuffle(ids)  # interleave splits so the annotator cannot tell dev from test
    payload = {
        "tool_version": "0.1",
        "schema_version": SCHEMA_VERSION,
        "guideline_version": GUIDELINE_VERSION,
        "annotator": annotator,
        "set": which,
        "fields": [
            {"name": f.name, "kind": f.kind, "allowed": list(f.allowed) if f.allowed else None,
             "description": f.description, "rule": RULES[f.name]}
            for f in FIELDS
        ],
        "cases": [{"case_id": c, "text": texts[c]} for c in ids],
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("__PAYLOAD__", data)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"label_{which}_{annotator}.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sample")
    b = sub.add_parser("build")
    b.add_argument("--annotator", required=True)
    b.add_argument("--set", dest="which", choices=["gold", "pathologist"], default="gold")
    args = ap.parse_args()
    if args.cmd == "sample":
        out = sample()
        sizes = {k: len(v) for k, v in out["gold"].items()}
        print(f"gold sample {sizes}, pathologist overlap {len(out['pathologist_overlap'])} -> {GOLD_FILE}")
    else:
        print(f"wrote {build(args.annotator, args.which)}")


if __name__ == "__main__":
    main()
