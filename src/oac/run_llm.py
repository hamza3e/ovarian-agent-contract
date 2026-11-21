"""Run the LLM report agent over one or more splits. Resumable: cases already in outputs.jsonl are skipped.

    python -m oac.run_llm --backend vllm --model Qwen/Qwen3-8B-AWQ --revision <sha> \
        --splits dev,calibration --mode hybrid --k 5 --out runs/qwen3-8b-hybrid

Writes to --out:
- manifest.json   run config, versions, prompt hash, data pins, code commit (one entry per invocation)
- outputs.jsonl   one AgentOutput (contract v0.1) per report
- raw.jsonl       model texts and confidence features per report (contains report quotes: git-ignored)

Test-site reports go through oac.splits.select, so they stay locked until the protocol is frozen.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from oac.agents import llm_extractor
from oac.data import REPO_ROOT, Report, load_ov_reports
from oac.llm import prompt as prompt_mod
from oac.llm.backends import AnthropicBackend, Backend, VLLMBackend
from oac.splits import select

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "synthetic_reports.json"


def code_commit() -> str | None:
    f = REPO_ROOT / "COMMIT"  # written into the Colab bundle by oac.bundle
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO_ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def synthetic_reports() -> list[Report]:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))["reports"]
    return [Report(c["case_id"], "synthetic", c["case_id"].split("-")[1], c["text"]) for c in cases]


def make_backend(args: argparse.Namespace) -> Backend:
    if args.backend == "vllm":
        return VLLMBackend(args.model, args.revision, dtype=args.dtype, max_model_len=args.max_model_len,
                           gpu_memory_utilization=args.gpu_mem)
    if args.backend == "anthropic":
        return AnthropicBackend(args.model, effort=args.effort)
    raise SystemExit(f"unknown backend {args.backend}")


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(json.loads(line)["case_id"])
    return ids


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["vllm", "anthropic"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--revision", default=None, help="HF commit sha (required for vllm)")
    ap.add_argument("--splits", default="dev,calibration")
    ap.add_argument("--synthetic", action="store_true", help="run on the synthetic fixtures only (smoke test)")
    ap.add_argument("--mode", choices=["hybrid", "e2e"], default="hybrid")
    ap.add_argument("--k", type=int, default=5, help="sampled extractions per report (self-consistency)")
    ap.add_argument("--seed", type=int, default=20261119)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dtype", default="half")
    ap.add_argument("--max-model-len", type=int, default=12288)
    ap.add_argument("--gpu-mem", type=float, default=0.90)
    ap.add_argument("--effort", default="medium", help="Claude API effort level")
    args = ap.parse_args(argv)
    if args.backend == "vllm" and not args.revision:
        raise SystemExit("--revision is required for vllm (pin the model)")

    if args.synthetic:
        reports = synthetic_reports()
    else:
        all_reports = load_ov_reports()
        reports = [r for s in args.splits.split(",") for r in select(all_reports, s.strip())]  # type: ignore[arg-type]
    if args.limit:
        reports = reports[: args.limit]

    args.out.mkdir(parents=True, exist_ok=True)
    outputs_p, raw_p = args.out / "outputs.jsonl", args.out / "raw.jsonl"
    seen = done_ids(outputs_p)
    todo = [r for r in reports if r.case_id not in seen]
    print(f"{len(reports)} reports, {len(seen)} already done, {len(todo)} to run", flush=True)
    if not todo:
        return

    prompt = prompt_mod.build(args.mode)
    backend = make_backend(args)
    commit = code_commit()
    entry = {
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "argv": sys.argv[1:] if argv is None else argv,
        "mode": args.mode, "k": args.k, "seed": args.seed, "splits": "synthetic" if args.synthetic else args.splits,
        "n_reports": len(reports), "prompt_version": prompt_mod.PROMPT_VERSION, "prompt_sha256": prompt.sha256,
        "agent": f"{llm_extractor.AGENT_NAME}@{llm_extractor.AGENT_VERSION}", "code_commit": commit,
        "backend": backend.describe(),
    }
    man_p = args.out / "manifest.json"
    manifest = json.loads(man_p.read_text(encoding="utf-8")) if man_p.exists() else {"runs": []}
    prev = manifest["runs"][0] if manifest["runs"] else None
    if prev and (prev["prompt_sha256"], prev["backend"]["model_id"], prev["mode"], prev["k"]) != (
            prompt.sha256, backend.model_id, args.mode, args.k):
        raise SystemExit("output dir holds a run with a different prompt/model/mode/k: use a new --out")
    manifest["runs"].append(entry)
    man_p.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for i in range(0, len(todo), args.batch):
        chunk = todo[i: i + args.batch]
        results = llm_extractor.run_batch(chunk, backend, prompt, k=args.k, seed=args.seed, mode=args.mode,
                                          code_commit=commit)
        with outputs_p.open("a", encoding="utf-8") as fo, raw_p.open("a", encoding="utf-8") as fr:
            for out, raw in results:
                fo.write(out.model_dump_json() + "\n")
                fr.write(json.dumps(raw, ensure_ascii=False) + "\n")
        print(f"  {min(i + args.batch, len(todo))}/{len(todo)} written", flush=True)

    entry["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    man_p.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("done", flush=True)


if __name__ == "__main__":
    main()
