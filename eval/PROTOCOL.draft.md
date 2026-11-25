# Evaluation protocol v0.2 (DRAFT, not frozen)

v0.2 (25 Nov 2026) replaces the gold-label design of v0.1 with a registry-based design (DECISIONS D29).

Freezing:
1. this file is copied to `eval/PROTOCOL.md`;
2. its sha256 is written to `eval/PROTOCOL.lock`;
3. both are committed;
4. only then may `OAC_UNLOCK_TEST=1` be set, once, for the test-site run.

Git history must show the protocol commit before any test-site output exists.

## 1. Question
Do agents that extract findings with an LLM, verify evidence by code, calibrate confidence on held-out centres and abstain
when unsure give findings and FIGO stage bounds that are **more trustworthy at unseen centres** than:
- a rules baseline;
- the same LLM used end to end?

"Trustworthy" is measured here as:
- agreement with the registry when the agent decides;
- confidence that is calibrated and transfers across centres;
- stage bounds that are consistent with the registry.

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

The super-agent (`oac.superagent`, graph v0.1.0) is run on H-cal outputs to report review workload (§6.6). It makes no model calls.

## 4. Reference: the registry (silver)
- TCGA-OV clinical table: grade, laterality, lymphovascular invasion (LVI) and FIGO 1988 stage.
- The registry is not truth. It was abstracted by each site and can disagree with the report. Every number below is
  **agreement with the registry**, not accuracy, and is reported as such.
- Silver only checks *answered* values. It cannot score `not_stated` (a registry value does not mean the report states it).
- Grade is compared strictly and on the 2-tier scale (G1 = low grade, G2–G3 = high grade); both are reported.
- **No human gold labels** (D29). A labelling pilot (§9) showed that credible gold labels for these fields need a pathologist.

## 5. Calibration and abstention (fitted on calibration sites only, then frozen)
- **Features:** see `src/oac/calibrate.py`.
- **Model:** L2 logistic regression, C = 1.0.
- **Training labels:** registry agreement of answered grade (2-tier), laterality and LVI on the 75 calibration reports.
- **Scope:** calibrated confidence is reported only for these three fields. Other fields keep raw confidence, labelled as raw.
- **Threshold τ:** the lowest calibrated confidence such that agreement on calibration decisions is ≥ 0.95. Answers below τ
  become `abstained: low_confidence`. If no τ reaches 0.95, use the τ that maximises agreement at coverage ≥ 0.5, and
  report that it fell short.

## 6. Endpoints (test sites)
Primary (grade, laterality, LVI; per field and pooled):
1. Coverage (share answered) and registry agreement among answered values, for R, E, H-raw and H-cal.
2. Calibration of H-cal versus H-raw against registry agreement: ECE (10 tie-preserving equal-count bins), Brier score,
   reliability diagram.
3. Risk–coverage curve and AURC for H-raw and H-cal.

Secondary:

4. FIGO 1988 stage:
   - for H: the rule lower bound (`oac.staging`), checked for consistency (registry stage ≥ lower bound) and tightness
     (lower bound = registry stage);
   - for E: exact match with the registry stage.

   Registry stage IV is never reachable from the report alone; this is reported, not counted as an error.
5. Per-site results with case-level bootstrap 95% CIs (1,000 resamples, seed 20261121); the worst-site gap; calibration
   transfer (ECE on calibration sites versus test sites).
6. Super-agent workload: share of cases sent to review, and counts by reason (registry conflict, stage conflict,
   abstention on a staging field, low confidence).
7. Abstention profile: rate per field and reason (evidence not verified, model unclear, low confidence) for all 14 fields.

## 7. What this protocol cannot measure (stated up front)
- **Accuracy of fields without a registry value:** histotype, primary site, surface, tube, uterus, omentum, omental
  deposit size, node counts, cytology, residual disease. For these, only answer and abstention rates are reported.
- **Whether `not_stated` is correct** ("does the agent invent findings?"). This needs human labels or a perturbation test,
  and is future work.
- Which side is right when the report and the registry disagree.

## 8. What would count against the hypothesis (reported as found)
- H-cal no better calibrated than H-raw on test sites.
- H-cal agreement no higher than E at matched coverage.
- Calibration that fails to transfer (test ECE much higher than calibration ECE).

Decoding settings for E and H:
- vLLM 0.34.0 on an NVIDIA L4, float16;
- max_tokens 3,072, context 12,288;
- evidence bounded by the grammar (3 quotes × 200 characters);
- greedy plus 5 samples at temperature 0.7, top_p 0.8, top_k 20; seed 20261119.

The prompt and system are frozen at v0.3 for this protocol: no further prompt changes.

## 9. Already seen before freezing (disclosure)
- Dev-site outputs of prompts v0.1, v0.2 and v0.3 against the registry (DECISIONS D12, D21, D24, D25), synthetic smoke
  tests, and the super-agent's dev-site summary (D28).
- Calibration-site outputs: only finish reasons and evidence string lengths, for the v0.2 truncation check (D24). No
  calibration-site agreement has been computed.
- Labelling pilot (D26, D27, D29): the author labelled 2 test-site reports for the planned gold set, blind to model outputs, and 5 dev
  practice reports. The 2 labels are not used. The practice labels were reviewed field by field against the annotation
  guide by Claude Code (dev reports only).
