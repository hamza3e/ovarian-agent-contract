# ovarian-agent-contract

**Calibrated, auditable agents for ovarian cancer evidence: an agent output contract, a pathology-report agent and an
agent evaluation protocol, tested across 20 centres on public TCGA-OV data.**

> Status: work in progress. Done: contract v0.1, data pipeline, splits, annotation tooling, rules baseline, LLM extractor
> and Colab runner. In progress: first model runs and the evaluation protocol. No results are reported until they come
> from the frozen protocol.

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
| LLM extractor: open-weight model on vLLM (schema-constrained, token logprobs) or Claude API; greedy + k samples | `src/oac/llm/`, `src/oac/agents/llm_extractor.py` | done, first runs pending |
| Baseline 2: end-to-end LLM (extracts and stages directly, answers taken at face value) | `--mode e2e` | done, runs pending |
| System: hybrid extraction + evidence verification + calibration + FIGO rules | `--mode hybrid`, `src/oac/` | extraction done; calibration and rules next |
| Colab runner (resumable, pinned model/prompt/code) | `notebooks/colab_extract.ipynb`, `src/oac/run_llm.py` | done |
| Evaluation protocol (calibration, selective prediction, per-site, conformal, robustness) | `eval/` | next |
| Super-agent v0 (LangGraph): FIGO rules, report-vs-registry conflicts, uncertainty triage, clinician review interrupt, case card (HTML + FHIR) | `src/oac/superagent/` | v0 done on saved outputs |

## Super-agent v0 (LangGraph)
The report agent extracts; this graph decides what a clinician needs to look at. Every node is deterministic code over
contract outputs, so there are no extra model calls and the same inputs always give the same card.

```
report output ─► stage (FIGO 1988 rules) ─► registry check ─► uncertainty triage ─┬─► case card (HTML + FHIR)
                                                                                  └─► clinician review ─► case card
                                                                                      (LangGraph interrupt)
```

- **Registry check:** answered grade (2-tier compatible), laterality and LVI against the TCGA clinical table, and the
  report's FIGO lower bound against the registry stage. A disagreement is a reason to look, not a verdict.
- **Uncertainty triage:** abstentions on fields that move the stage, and answered findings with low confidence
  (calibrated when a calibrator exists, raw self-consistency otherwise, and the card says which).
- **Clinician review:** the graph pauses with `interrupt()` and a checkpointer, and resumes with
  `accept_report`, `accept_registry` or `defer` plus a note, which is written into the card and its provenance.
- **Outputs:** an HTML card with evidence quotes and offsets (kept in git-ignored `runs/`), and FHIR R4-shaped JSON
  (DiagnosticReport, Observations, Flags, Provenance) that carries evidence as offsets plus the report hash, never text.
  Not validated against a FHIR server.

Synthetic example (invented case and quotes): [docs/example_case_card.html](docs/example_case_card.html),
[docs/example_case_card.fhir.json](docs/example_case_card.fhir.json).

```
uv sync --extra agent
uv run python -m oac.superagent --run runs/<run> --out runs/superagent_dev                 # batch, reviews deferred
uv run python -m oac.superagent --run runs/<run> --out runs/sa --case <id> --interactive   # answer reviews at the terminal
uv run python -m oac.superagent.demo                                                        # regenerate the synthetic example
```

Development observation (dev sites only, prompt v0.3 hybrid run, not an evaluation result): 109 cases, 67 cards with no
issues, 42 sent to review. Most common reasons: abstentions on omentum (11) and tube (9) involvement, and 8
laterality disagreements with the registry. Test sites stay locked; the graph refuses them until the protocol is frozen.

## Reproduce
```
uv sync --extra eval
uv run python -m oac.fetch        # public data, sha256-checked
uv run pytest -q

# LLM runs (GPU): writes dist/colab_extract_run.ipynb with the code embedded;
# open it in VS Code (Google Colab extension) or Colab web and pick a GPU runtime
uv run python -m oac.bundle
# Claude API comparison arm (key in a git-ignored .env, see .env.example)
uv sync --extra api && set -a && . ./.env && set +a
uv run python -m oac.run_llm --backend anthropic --model claude-opus-5-5 --splits dev,calibration --k 3 --out runs/claude-opus-5-5_hybrid_k3
```

## Data
TCGA-Reports (Kefeli & Tatonetti, Patterns 2024; CC BY 4.0) joined with the TCGA-OV clinical table (GDC open access).
371 reports from 20 sites. See [DATA_CARD.md](DATA_CARD.md).

## How this was built
Built with Claude Code as the engineering assistant under the rules in [CLAUDE.md](CLAUDE.md). Decisions, including what the
AI proposed and what was corrected, are in [DECISIONS.md](DECISIONS.md).

Research prototype on retrospective public data. Not for clinical use.
