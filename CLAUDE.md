# CLAUDE.md: rules for AI-assisted work in this repo

This repo is built with Claude Code as the engineering assistant. The human author owns every decision; Claude Code
proposes, implements and tests. Every non-trivial choice is logged in `DECISIONS.md`: what the AI proposed, what was
checked, what was changed.

## What this repo is
- An agent evidence contract (`src/oac/contract.py`).
- A pathology-report agent and its baselines (`src/oac/agents/`).
- An agent evaluation protocol (`eval/`), on public TCGA-OV data.

It is a research prototype on retrospective public data and is not for clinical use.

## Hard rules
1. **No test-site peeking.**
   - Test-site reports are locked for model code (`oac.splits.select` raises `TestSetLocked`) until `eval/PROTOCOL.md` is frozen (`eval/PROTOCOL.lock`).
   - The single final run sets `OAC_UNLOCK_TEST=1`.
   - Never weaken this guard, and never read test-site report text to tune prompts, rules or thresholds.
   - Humans may label test reports, blind to model outputs.
2. **No report text in git, logs, issues, prompts to external services other than the configured extraction backend, or chat summaries.**
   - Report text lives in `data/` and `labeling/out/` (git-ignored).
   - Commit derived outputs only (labels, statuses, offsets, metrics).
3. **No fabricated numbers.** Every number in README or docs comes from a script in this repo run on the stated data. If a result is bad, report it.
4. **Pinned everything:** data sha256 (`oac.fetch`), model id and revision, prompt hash, seeds, schema and contract versions.
5. **The system under test is a pinned model run by a script.** Claude Code or Codex sessions never act as the extractor.
6. **Evidence is verified by code** (`oac.evidence.locate`), never trusted from a model.
7. Silver labels (TCGA clinical table) are registry values, not truth: report them as agreement, never as accuracy. There is no human gold set in this version (D29).

## How to run
```
uv sync --extra eval
uv run python -m oac.fetch          # download + sha256-check the public data
uv run pytest -q && uv run ruff check .
```

## Coding standards
- Python ≥ 3.10, type hints, pydantic models at boundaries, small pure functions, tests for every module.
- Synthetic fixtures only in `tests/` (clearly marked).
- Every new field or status must update `fields.py`, the annotation guide and the contract version if the schema changes.

## When finishing a step
Run the tests and lint, update `DECISIONS.md` (dated), and update the README results only from regenerated outputs.
