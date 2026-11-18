# ovarian-agent-contract

**Calibrated, auditable agents for ovarian cancer evidence: an agent output contract, a pathology-report agent and an
agent evaluation protocol, tested across 20 centres on public TCGA-OV data.**

> Status: work in progress (contract v0.1, data pipeline, splits, annotation tooling and rules baseline done; LLM agent
> and evaluation in progress). No results are reported until they come from the frozen protocol.

## The problem, in the terms of a multi-agent clinical system
A multi-agent decision-support system (imaging, pathology, genomics, clinical text) only works if every agent:
- answers in the same auditable form;
- says how sure it is in a way that holds at **other hospitals**;
- can say "the source does not say" or "I am not sure" instead of guessing.

This repo builds and tests that layer on a real task: pathology reports of high-grade serous ovarian cancer from
20 TCGA centres.

| Piece | Where | State |
|---|---|---|
| Agent output contract v0.1 (value, verified evidence spans, raw + calibrated confidence, abstention, provenance; JSON Schema) | `src/oac/contract.py`, `contract/` | done |
| Report schema v0.1 (14 findings; FIGO stage derived by rules, not extracted) | `src/oac/fields.py` | done |
| Site-level splits with a code-enforced test-set lock | `src/oac/splits.py` | done |
| Annotation guide + offline labelling tool (gold set, pathologist overlap) | `docs/ANNOTATION_GUIDE.md`, `labeling/` | done |
| Baseline 1: rules | `src/oac/agents/rules_baseline.py` | done |
| Baseline 2: end-to-end LLM; system: hybrid LLM extraction + evidence verification + calibration + FIGO rules | `src/oac/agents/` | next |
| Evaluation protocol (calibration, selective prediction, per-site, conformal, robustness) | `eval/` | next |
| Super-agent v0 (report + registry, conflict detection, case card) | | planned |

## Reproduce
```
uv sync --extra eval
uv run python -m oac.fetch        # public data, sha256-checked
uv run pytest -q
```

## Data
TCGA-Reports (Kefeli & Tatonetti, Patterns 2024; CC BY 4.0) joined with the TCGA-OV clinical table (GDC open access).
371 reports from 20 sites. See [DATA_CARD.md](DATA_CARD.md).

## How this was built
Built with Claude Code as the engineering assistant under the rules in [CLAUDE.md](CLAUDE.md). Decisions, including what the
AI proposed and what was corrected, are in [DECISIONS.md](DECISIONS.md).

Research prototype on retrospective public data. Not for clinical use.
