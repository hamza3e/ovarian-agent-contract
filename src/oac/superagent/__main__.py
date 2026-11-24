"""Run the super-agent over saved report-agent outputs.

    uv run --extra agent python -m oac.superagent --run runs/qwen3-8b-awq_p0.3_hybrid_k5 --out runs/superagent_dev
    uv run --extra agent python -m oac.superagent --run ... --case TCGA-24-1436 --interactive

Reads only saved contract outputs and the registry table. Test sites are refused until the protocol is frozen.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from oac.data import BCR_PATIENT, read_bcr, silver_labels
from oac.splits import protocol_frozen, split_of
from oac.superagent.graph import build_graph, run_case
from oac.superagent.render import card_fhir, card_html


def ask(payload: dict) -> dict:
    print(f"\n=== review needed: {payload['case_id']} (FIGO >= {payload['stage']['lower']}) ===")
    for i in payload["conflicts"] + payload["flags"]:
        print(f"  - {i['kind']} | {i['field']}: {i['detail']}")
    while True:
        d = input(f"decision {payload['options']}: ").strip()
        if d in payload["options"]:
            return {"decision": d, "note": input("note (optional): ").strip()}


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="Super-agent v0 over saved contract outputs")
    ap.add_argument("--run", type=Path, required=True, help="run folder with outputs.jsonl")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", choices=("dev", "test"), default="dev")
    ap.add_argument("--case", help="one case id")
    ap.add_argument("--interactive", action="store_true", help="answer review interrupts at the terminal")
    ap.add_argument("--bcr", type=Path, default=BCR_PATIENT)
    args = ap.parse_args(argv)
    if args.split == "test" and not protocol_frozen():
        raise SystemExit("test sites are locked until eval/PROTOCOL.md is frozen")

    outputs = [json.loads(line) for line in (args.run / "outputs.jsonl").read_text(encoding="utf-8").splitlines() if line]
    outputs = [o for o in outputs if split_of(o["site_id"]) == args.split and (not args.case or o["case_id"] == args.case)]
    registry = read_bcr(args.bcr)
    graph = build_graph()
    reviewer = ask if args.interactive else (lambda p: {"decision": "defer", "note": "batch run: no reviewer"})

    args.out.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    issue_counts: Counter = Counter()
    for o in outputs:
        reg = silver_labels(registry[o["case_id"]]) if o["case_id"] in registry else {}
        state, _ = run_case(graph, {"case_id": o["case_id"], "site_id": o["site_id"], "report": o, "registry": reg},
                            reviewer)
        card = state["card"]
        counts[card["status"]] += 1
        issue_counts.update(f"{i['kind']}:{i['field']}" for i in card["conflicts"] + card["flags"])
        (args.out / f"{o['case_id']}.html").write_text(card_html(card), encoding="utf-8")
        (args.out / f"{o['case_id']}.fhir.json").write_text(json.dumps(card_fhir(card), indent=1), encoding="utf-8")
    summary = {"run": str(args.run), "split": args.split, "n_cases": len(outputs), "card_status": dict(counts),
               "issues": dict(sorted(issue_counts.items(), key=lambda kv: -kv[1]))}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
