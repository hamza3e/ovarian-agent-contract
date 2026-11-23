# Evaluation protocol v0.1 (DRAFT, not frozen)

Freezing:
1. this file is copied to `eval/PROTOCOL.md`;
2. its sha256 is written to `eval/PROTOCOL.lock`;
3. both are committed;
4. only then may `OAC_UNLOCK_TEST=1` be set, once, for the test-site run.

Git history must show the protocol commit before any test-site output exists.

## 1. Question
Do agents that extract findings with an LLM, verify evidence by code, calibrate confidence on held-out centres and
abstain when unsure produce **more trustworthy** report findings and FIGO stage bounds at **unseen centres** than:
- a rules baseline;
- the same LLM used end to end?

"Trustworthy" here means:
- correct when they decide;
- honest about absence (`not_stated`);
- calibrated confidence that transfers across centres.

## 2. Data and splits (fixed 18 Nov 2026, D4)
- 371 TCGA-OV pathology reports, 20 tissue-source sites.
- Dev: sites 24, 42, 13 (109 reports). Prompt and rule development only.
- Calibration: sites 61, 10, 57 (75 reports). Calibrator and threshold fitting only.
- Test: the 14 other sites (187 reports). One run, after freezing.

## 3. Systems (all pinned)
| ID | System | Notes |
|---|---|---|
| R | rules baseline (`agents/rules_baseline.py` v0.1.0) | no model |
| E | Qwen3-8B-AWQ @ 4da05a8, prompt v0.3.0, end to end, greedy | answers taken at face value; stages directly |
| H-raw | same model and prompt, hybrid: greedy + 5 samples, code-verified evidence | confidence = self-consistency |
| H-cal | H-raw + calibrator (§5) + abstention threshold (§5) | the proposed system |
| C (optional) | Claude API arm, same prompt v0.3.0 | only if a key is available; reported separately |

## 4. References
- **Gold:** human labels, blind to model outputs.
  - 70 reports: 15 dev, 20 calibration, 35 test, by the author, following `docs/ANNOTATION_GUIDE.md`.
  - 15 test reports are double-labelled by a pathologist (inter-annotator agreement: Cohen's κ per field).
  - Gold `unsure` labels are excluded from scoring.
  - Annotator training: before the gold set, the author labels 5 practice reports from dev sites (`configs/practice_sample.json`, outside the gold set) and gets field-by-field feedback from Claude Code. Gold labels themselves get no AI feedback on values; only format, evidence-span and timing checks.
- **Silver:** TCGA clinical table: grade, laterality, LVI and FIGO 1988 stage, for all reports.
  - Used only to check answered values, never to score `not_stated`.
  - Silver is a registry, not truth: disagreements are reported as such, and a sample is adjudicated (§7).

## 5. Calibration and abstention (fitted on calibration sites only, then frozen)
- **Features:** see `src/oac/calibrate.py`.
- **Model:** L2 logistic regression, C = 1.0.
- **Training labels (decided 21 Nov, author):**
  - gold decisions on the 20 calibration reports;
  - plus silver checks on all 75 calibration reports, for answered grade (2-tier compatible), laterality and LVI.

  When gold and silver both exist for the same field, gold wins. Sensitivity analysis: the same calibrator fitted on gold only, reported next to it.
- **Threshold τ:** the lowest calibrated confidence such that selective accuracy on calibration decisions is ≥ 0.95. Decisions below τ become `abstained: low_confidence`. If no τ reaches 0.95, use the τ that maximises selective accuracy at coverage ≥ 0.5, and report that it fell short.

## 6. Endpoints (test sites)
Primary, on gold test reports, per field and pooled over fields:
1. Coverage and selective accuracy (decisions = answered + not_stated), for R, E, H-raw, H-cal.
2. Hallucination rate: answered when gold says `not_stated`.
3. Calibration of H-cal versus H-raw: ECE (10 tie-preserving equal-count bins), Brier score, reliability diagram.
4. Risk–coverage curve and AURC for H-raw and H-cal.

Secondary:
5. Silver agreement on all 187 test reports (grade strict and 2-tier compatible, laterality, LVI): answered / agree / not answered.
6. FIGO 1988 stage:
   - for H: the rule lower bound (`oac.staging`), checked for consistency (silver stage ≥ lower bound) and tightness (lower bound = silver stage);
   - for E: exact match with silver.
   Silver stage IV is never reachable from the report alone; this is reported, not counted as an error.
7. Per-site results: selective accuracy and calibration per test site, with case-level bootstrap 95% CIs (1,000 resamples, seed 20261121); the worst-site gap.
8. Calibration transfer: ECE on calibration sites (in-sample) versus test sites.
9. Abstention profile: rate per field and reason (evidence not verified, model unclear, low confidence). Residual disease is expected to be `not_stated`.

Exploratory (labelled as such):
- prompt-injection and OCR-noise perturbation on calibration reports;
- report-versus-registry conflict review with the pathologist.

## 7. Adjudication
- The pathologist reviews up to 20 report-versus-registry conflicts on test sites, blind to which system produced the conflict.
- Outcomes are reported as counts (report right / registry right / unclear).

## 8. What would count against the hypothesis (reported as found)
- H-cal no better calibrated than H-raw on test sites.
- H-cal selective accuracy no higher than E at matched coverage.
- Calibration that fails to transfer (test ECE much higher than calibration ECE).

Decoding settings for E and H:
- vLLM 0.34.0 on an NVIDIA L4, float16;
- max_tokens 3,072, context 12,288;
- evidence bounded by the grammar (3 quotes × 200 characters);
- greedy plus 5 samples at temperature 0.7, top_p 0.8, top_k 20; seed 20261119.

The prompt and system are frozen at v0.3 for this protocol: no further prompt changes.

## 9. Already seen before freezing (disclosure)
- Dev-site outputs of prompts v0.1, v0.2 and v0.3 against silver (DECISIONS D12, D21, D24, D25), and synthetic smoke tests.
- Calibration-site outputs: only finish reasons and evidence string lengths, for the v0.2 truncation check (D24). No calibration-site accuracy.
- No calibration-site or test-site metric has been computed. The calibration-site v0.1 outputs exist on disk but were not analysed.
