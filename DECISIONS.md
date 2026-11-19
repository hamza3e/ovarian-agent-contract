# DECISIONS.md

Dated log of design decisions. "AI" = Claude Code (engineering assistant); "Author" = the human owner.

## 2026-11-18: Scope, data, splits

**D1. Task framing: agent contract + report agent + evaluation protocol (not a bigger model).**
- AI proposed: frame the project as the month-1/2 deliverables of a multi-agent ovarian cancer system: a common output contract, a reference agent, and an evaluation protocol for calibration, abstention and per-centre performance.
- Checked: the target group already publishes LLM extraction from pathology reports and agentic pathology systems. The calibrated, contract-based layer is the missing piece.
- Author: approved.

**D2. Data: TCGA-Reports (OCR'd TCGA pathology reports) × TCGA-OV clinical table.**
- Checked: data license CC BY 4.0 (Mendeley 10.17632/hyg5xkznpx.1), code MIT; GDC clinical table is open access.
- Real counts: 371 OV reports, 20 tissue-source sites, one report per case.
- sha256 values are pinned in `oac.fetch`.

**D3. Staging version.**
- AI found that the TCGA clinical table contains stage IIC (16 cases), which exists only in FIGO 1988, and that diagnosis years are mostly 1999–2009.
- Decision: compare derived stage with FIGO 1988 rules. Keep a 2014 mapping only as a documented extension.

**D4. Site-level splits** (fixed before any model output existed):
- dev = 24, 42, 13 (109 reports);
- calibration = 61, 10, 57 (75);
- test = 14 other sites (187).

Rationale: it mirrors a consortium ("built at one centre, calibrated at a second, tested at unseen centres") and makes calibration transfer measurable.
- Alternative rejected: a random report-level split. It would hide site shift, which is the thing the grant must evaluate.

**D5. `not_stated` and `abstained` are separate states in the contract.**
- `not_stated` = the source lacks the information (a correct answer); `abstained` = the agent declines.
- Merging them would let an agent score well by refusing, or hide missing evidence.

**D6. FIGO stage is derived by rules, not extracted.**
- An abdominal pathology report cannot show stage IV. The report agent will output a lower bound or a range; imaging and clinical agents are needed for the rest.
- Design principle supported by external evidence: hybrid (extract, then rules) beat end-to-end LLMs on O-RADS (arXiv 2608.23061).

**D7. LLM backends.**
- Primary: an open-weight model on Colab GPU (vLLM, schema-guided decoding, logprobs). Comparison arm: Claude API.
- Rejected: using a chat or coding-assistant session as the extractor (not pinned, not reproducible, circular).

**D8. Gold set: 70 reports (15 dev / 20 calibration / 35 test)**, largest-remainder allocation with at least one per site, seed 20261118. The pathologist overlap is 15 test reports, round-robin across sites. The labelling order is shuffled so annotators cannot tell splits apart.

**D9. Bug caught by tests.**
- AI's first `protocol_frozen()` bound file paths as default arguments, so the test-set lock could not be redirected in tests.
- The test `test_test_split_unlocks_only_with_frozen_protocol` failed. Fixed by resolving paths at call time.

**D10. Rules baseline written on synthetic examples only.** It is not tuned on calibration or test sites. Known weakness, kept on purpose: sentence-level negation ("tube involved, no surface involvement" is read as negative).

**D11. Lint line length 130.** Keeping regexes on one line is more readable than splitting them.

**D12. First look at the baseline, dev sites only** (development observation, not a result).
- Grade agrees with the registry on most answered dev cases.
- Laterality is the weak spot: unanswered on most dev reports, and wrong more often than right when it answers. Laterality is spread across specimen parts ("Part 2: sigmoid colon/left ovary"), which sentence regexes cannot assemble.
- Peritoneal cytology is never found (likely in separate cytology reports or phrased differently).

These are the places where an LLM extractor should show its value. They become hypotheses for the protocol, checked on calibration and test sites, not tuned on them.

## 2026-11-19: LLM extractor, backends, Colab runner

**D13. Primary model: `Qwen/Qwen3-8B-AWQ` @ `4da05a8edb55c6046cce958586c33b61da07bb79` (Apache-2.0), vLLM, float16, non-thinking mode.**
- Chosen so the system under test fits a 16 GB T4. Colab assigns T4, L4 or A100 at random; the model must not change with it.
- Larger models on A100 are allowed only as a labelled ablation, never mixed into the main results.
- Checked: the revision via the Hugging Face API; vLLM's install docs list compute capability 7.5 (T4) as supported.
- Not yet verified: whether the current vLLM release runs this model on a T4 without problems. A forum log from mid-2025 shows the V1 engine falling back on compute capability below 8.0. The notebook runs a synthetic smoke test first, and the vLLM version is pinned after the first successful run.

**D14. The model-facing schema is not the contract.**
- The model may say `answered`, `not_stated` or `unclear` and must quote its evidence. Code decides the contract status.
  - Hybrid mode: an unverified quote becomes `abstained: evidence_not_verified`.
  - `unclear` becomes `abstained: model_unclear`.
  - Malformed output becomes `abstained: invalid_model_output` and is never silently repaired.
- End-to-end baseline: same model and prompt core, plus a directly assigned FIGO 1988 stage. Answers are taken at face value; unverified evidence only adds a warning.
- Schema property order is fixed, so constrained decoders generate fields in a known order.

**D15. Confidence features recorded per field, before any calibration.**
- Self-consistency: agreement of k=5 samples with the greedy answer. Sampling uses Qwen3's recommended non-thinking settings: temperature 0.7, top_p 0.8, top_k 20. Per-report seeds come from the case id.
- Token probabilities of the generated status and value: raw logprobs, located by character span in the JSON text.
- Evidence match score.
- `confidence_raw` is the agreement for now. Mapping features to `confidence_calibrated` will be fitted on calibration sites only (next step).
- If decoded tokens do not concatenate to the output text, the token features are recorded as missing, not approximated.

**D16. Claude API comparison arm: `claude-opus-5-5`, effort `medium`, structured outputs (`output_config.format`).**
- This model accepts no temperature, so samples are independent calls.
- The server-side refusal fallback is on. The model that actually served each call is recorded; calls served by a fallback model are flagged and do not count as the pinned arm.
- Checked: parameter names against the installed SDK (anthropic 2.10.0). Tested only with a mocked client so far; no key yet.

**D17. Reproducible Colab runs.**
- `oac.bundle` builds a code-only zip, only from a clean commit, and stamps it with that commit hash. Every output records the hash.
- The runner is resumable (skips finished cases). It refuses to mix prompt, model, mode or k in one output directory.
- Correction made while writing the notebook: the AI first wrote an expected run time ("20 to 40 minutes on a T4"). It was removed because it was not measured; the manifest records real start and finish times.

**D18. Notebooks are excluded from ruff** (Colab shell magics); the code they call is linted and tested.

**D19. Colab runs from VS Code; the code travels inside the notebook.**
- The author runs the notebook from VS Code through Google's official Colab extension (kernel: Colab GPU server). Cell outputs are saved in the notebook file in this repo, so Claude Code can read errors and fix cells. Claude Code cannot start the Colab kernel itself.
- The Colab server cannot read local files. So `oac.bundle` now writes `dist/colab_extract_run.ipynb`: the template notebook with a base64 code zip embedded, taken from a clean commit and stamped with it. Nothing has to be uploaded.
- Results go to Google Drive. Third-party write-ups say `drive.mount()` does not work in the extension; the extension's own docs list a "Mount Google Drive to Server" command. The notebook tries `drive.mount()` first, then tells the user to run that command. Not yet verified on this machine.
- Tests check that the embedded bundle has code only (no data, runs or labels) and that the notebook cell unpacks it.
