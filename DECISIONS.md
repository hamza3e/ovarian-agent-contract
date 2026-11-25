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

## 2026-11-20: first GPU run

**D20. First run on a Colab T4 (VS Code extension), facts from the saved notebook log.**
- Environment: Tesla T4 15 GB, vllm 0.34.0, torch 2.14.0+cu130. The model loaded in float16 with about 5.9 GB used, and the synthetic smoke test passed. The concern in D13 (T4 support) is resolved for this version, which is now pinned in the notebook.
- Hybrid run, dev + calibration: 96 of 184 reports written to Drive. Each batch of 32 took 35 to 45 minutes (greedy + 5 samples). The Colab server then dropped while the 4th batch was running; the in-flight batch was lost.
- Changes:
  - Results are now written every 16 reports, not 32, to lose less per disconnect.
  - The notebook explains how to resume; the runner skips finished reports.
  - Batch composition can change vLLM numerics slightly. Each invocation is recorded in the manifest. Prompt, model, mode and k are unchanged, as the runner enforces.
- Synthetic smoke outputs (3 reports, a check of the plumbing, not a result):
  - laterality was `not_stated` on the two-part bilateral example;
  - the histotype and grade rules were not followed on "papillary serous adenocarcinoma, poorly differentiated" (the model gave `high_grade_serous` and `high_grade`, where the guide says `serous_nos` and `G3`).

  The prompt is **not** changed during this run. Any prompt revision will be made on dev sites only and followed by a full re-run (logged as a new prompt version).

## 2026-11-21: prompt v0.2 from dev-site observations

**D21. Dev-site look at the v0.1 runs (development observation against silver labels, not a result).**
- Two complete v0.1 runs on dev + calibration, 184 reports each: hybrid k=5 and e2e. Both on a T4.
- Laterality, dev (cases with a silver label): rules answered 28 (10 agree, 79 unanswered); e2e answered 72 (66 agree); hybrid answered 56 (49 agree). The hypothesis from D12 holds: the LLM adds most where findings are spread across specimen parts.
- LVI agreed with silver in every answered case for all three systems.
- Residual disease was never answered (109/109 `not_stated`).
- Grade: in 33 dev reports the hybrid said `high_grade` where silver says G3. A keyword scan found 3-tier wording ("poorly differentiated", "grade 3", ...) in 23 of those 33 reports, which breaks the annotation rule. This is the same error the synthetic smoke test showed (D20).
- Histotype: 24 dev abstentions with `evidence_not_verified`. In 20 of them every word of the quote occurs in the report: the model joined text from separate places into one quote.
- **Bug: token probabilities were never computed** (`tokens_aligned` false for 109/109).
  - vLLM 0.34 returns BPE pieces ("Ġ", "Ċ") in `Logprob.decoded_token`, so the tokens did not concatenate to the output text.
  - The alignment check did its job: it recorded the features as missing rather than approximating them. But the feature is lost for v0.1, because raw.jsonl kept no token ids.
  - Checked locally with the model's tokenizer: decoding token by token reproduces the output text in 40/40 dev outputs.
- Self-consistency alone discriminates little: in 849 of 904 answered dev fields, all 5 samples agreed with the greedy answer.

**Changes in v0.2** (made on dev observations only; calibration and test sites not inspected for this):
- Prompt v0.2.0:
  - an explicit grade rule (any 3-tier grade wins over "high/low grade");
  - evidence must be continuous verbatim pieces, up to three, separated by " ... ".
- Verifier:
  - multi-part quotes are split on " ... ", and every part must be found;
  - **new guard: a fuzzy match may not differ in meaning-changing words** (left/right/bilateral, negations, positive/negative, numbers).
    - Found by a new unit test: "Ovary, right, ...: Metastatic carcinoma" fuzzy-verified at 93 against "Ovary, left, ...", so a swapped side passed.
    - Re-checking the v0.1 dev evidence with the guard rejects 16 of 248 fuzzy-verified spans. Most are numbers or words the model added to the quote.
- Backend:
  - token texts are decoded with the tokenizer;
  - token ids and greedy token logprobs are kept in raw.jsonl, so features can be recomputed without a GPU.
- Agent version 0.2.0. v0.1 runs are kept as a record. v0.2 writes to new folders (`*_p0.2_*`), and the whole v0.2 run uses one GPU type.

**D22. Evaluation building blocks (code only, no results yet).**
- `oac.staging`: FIGO 1988 lower bound from answered findings. The upper bound is always IV, because distant disease, other pelvic tissue and extra-omental peritoneum are not in schema v0.1. Test cases mirror the study guide's calculator.
- `oac.metrics`:
  - decision outcomes against gold (`not_stated` scored, `unsure` excluded) and silver (answered values only);
  - ECE, Brier, risk–coverage, AURC, case-level bootstrap.
  - Correction found by a unit test: equal-count ECE bins split tied confidences. Ties are the norm here (agreement 1.0 for most fields), so bins now never split equal values.
- `oac.calibrate`: logistic-regression calibrator on extraction features, fitted on calibration sites only.
- `eval/PROTOCOL.draft.md`: written, **not frozen**. One open decision for the author: which labels train the calibrator.

**D23. Calibrator training labels (author decision, 21 Nov):** gold (20 calibration reports) plus silver for answered grade (2-tier compatible), laterality and LVI on all 75 calibration reports. Gold wins where both exist. A gold-only fit is reported as a sensitivity analysis. Rationale: gold alone gives few errors to learn from. Grade is compared on the 2-tier scale so that correct "high grade" answers are not counted as wrong.

## 2026-11-21: v0.2 run on an L4, prompt v0.3

**D24. v0.2 results (L4, vllm 0.34.0), operational check and dev-site look; v0.3 fixes runaway evidence.**
- Both v0.2 runs are complete: 184 reports each, hybrid in 43 minutes, e2e in 15. Token features were computed for 184/184 (the D21 fix works).
- **Regression: 15/184 greedy hybrid outputs (and 13/184 e2e) hit the 2,048-token limit.** v0.1 had none. A truncated output is invalid JSON, so every field of that report abstains.
  - The truncations were counted on dev and calibration sites. Only finish reasons and string lengths were inspected, no accuracy.
  - Two failure modes in the evidence strings:
    - loops of repeated " ... " quotes (e.g. 181 parts, 2 distinct);
    - single quotes of 1,000 to 6,000 characters.

  The v0.2 instruction "up to three quotes" invited the loops.
- Dev sites, excluding the 11 reports truncated in either v0.2 run (98 left), against silver:
  - grade agreement rose from 58 to 79 of answered (hybrid), with `high_grade` answers down from 29 to 6;
  - laterality: answered 50 → 62, agreeing 43 → 56;
  - histotype abstentions halved (21 → 10);
  - LVI unchanged (all agree).
  - Evidence-not-verified abstentions rose (58 → 96, all fields), partly from the D21 guard.
- **v0.3 (schema, not wording):**
  - evidence is a JSON array of at most 3 quotes, each at most 200 characters, enforced by the decoding grammar, so a loop cannot run away;
  - e2e reasoning is capped at 400 characters;
  - max_tokens 3,072 and context 12,288.
  - The Claude API does not accept length or item bounds, so the Claude arm receives the schema without them and code checks the bounds.
  - The smoke test now checks that the bounds held and that nothing was truncated, because grammar engines can enforce length bounds unsoundly.

**D25. v0.3 runs (L4) and freezing the system.**
- Both runs are complete: hybrid in 34 minutes, e2e in 13.
- Truncations: hybrid 0/184 greedy and 0/920 samples; e2e 1/184 greedy.
- The smoke check confirmed that the evidence bounds held.
- Dev sites (all 109) against silver, answered/agreeing, hybrid:
  - grade: v0.1 98/64, v0.2 87/81, v0.3 102/91;
  - laterality: 56/49, 64/58, 79/71;
  - LVI: 29/29, 25/25, 28/28.
  - e2e v0.3: grade 101/91, laterality 85/77, LVI 31/31.
- Hybrid dev abstentions: v0.3 has 44 (41 evidence not verified, 3 model unclear). v0.1 had 82; v0.2 had 228, mostly invalid output from truncation.
- Peritoneal cytology and residual disease are `not_stated` in all 109 dev reports. This needs a gold-set check: are washings really absent from these reports?
- **Decision: prompt and system frozen at v0.3 for the evaluation protocol.** No further prompt changes before the test run. Any later change would be a new, separately reported version.

## 2026-11-23: label tool v0.2 (active-time timer)

**D26. Annotation time is measured as active time.**
- The author's first gold case showed 1,463 s. Tool v0.1 counted wall-clock time from page load, so this included reading the guide and idle time. It was not a usable annotation-cost number.
- Claude Code proposed and implemented a timer that counts a second only while:
  - the tab is visible and focused;
  - there was mouse, keyboard, scroll or selection input in the last 2 minutes.

  Each tick adds at most 5 s, so a sleeping laptop cannot add a gap. Time is flushed when the tab is hidden or closed.
- Cases timed under v0.1 keep their seconds but are flagged `timing: wallclock_v0.1` and are excluded from cost statistics. New cases are flagged `active_v0.2`.
- Checked:
  - case order is unchanged after rebuilding (same seed), and browser-stored labels carry over (same storage key);
  - the step logic is unit-tested via node (`tests/test_label_tool.py`: hidden tab, unfocused window, 2-minute idle edge, sleep cap, clock going back);
  - the page renders in headless Chromium.
- Limitation: reading without touching mouse or keyboard for more than 2 minutes is under-counted. This is reported with the cost numbers.

**D27. Annotator training round before gold labelling (23 Nov).**
- After two gold cases the author asked for feedback on the values, because the field terms were unfamiliar. One case took 17 active minutes.
- Claude Code declined to review gold values. Test and calibration gold is the reference for the system, and AI corrections would make it partly AI-labelled.
- Instead, Claude Code proposed a training round:
  - 5 practice reports (`configs/practice_sample.json`): dev sites, outside the gold set and the pathologist overlap, ordered short to long, spread over the three dev sites;
  - selection by keyword coverage of the fields;
  - the author labels them and gets field-by-field feedback with explanations;
  - practice labels are never scored.

  The author approved it.
- Checks: `practice_ids()` refuses any case that is in the gold set, in the overlap, or outside dev sites, and a unit test checks this.
- After training, the author re-reviews their own first two gold cases without AI input.

## 2026-11-24: super-agent v0 with LangGraph

**D28. Super-agent v0 as a LangGraph state graph over saved contract outputs.**
- Why now: the Cambridge person specification lists "familiarity with agentic frameworks" as essential, and the author
  had not used one. The author asked for a small, real LangGraph component rather than a claim.
- Claude Code proposed and implemented it; the author approved the design before coding:
  - nodes: FIGO rules (`oac.staging`), registry check, uncertainty triage, clinician review, case card;
  - a conditional edge sends a case to review only when there is a conflict or a flag;
  - review is a LangGraph `interrupt()` with an in-memory checkpointer, resumed with `Command(resume=...)`;
  - no LLM calls in the graph: the model work is done by the pinned report agent, so the graph is deterministic and free to run.
- Choices and why:
  - **Dev sites only.** The CLI refuses test sites until the protocol is frozen. Calibration sites are not used either, so
    no calibration-site accuracy is seen before calibration is fitted (protocol disclosure, §9 of the draft).
  - **Raw confidence for now.** No calibrator has been fitted; the card labels the confidence as raw. Threshold 0.6
    (fewer than 4 of 5 samples agree) is a development choice, not tuned.
  - **FHIR bundle without text.** Evidence is carried as offsets and the report sha256, so the system-facing output never
    contains report text. The HTML card shows quotes and is written only to git-ignored `runs/`.
  - **Stage IV in the registry is not a conflict.** The report can only set a lower bound, so a higher registry stage is consistent.
- Checked: 8 unit tests on synthetic outputs (clean case, 2-tier grade, stage IV, interrupt and resume, defer, raw-confidence
  flag, invalid review, FHIR without text); the dev run's 8 laterality conflicts match the D25 count (79 answered, 71 agree).
- Version: langgraph 1.2.24 (optional extra `agent`; CI installs it).

## 2026-11-25: no gold set; history rewritten before publication

**D29. Gold labelling is dropped; the evaluation uses the registry (protocol draft v0.2).**
- Pilot (23 Nov):
  - the author labelled 2 test-site reports for the gold set and 5 dev practice reports;
  - active time per practice report was 7 to 11 minutes;
  - a field-by-field review of the practice labels against the annotation guide (by Claude Code, dev reports only) disagreed on 16 of 70 fields, mostly LVI, uterus involvement, omental deposit size and histotype.
- Author's conclusion: these fields need pathology training to label reliably. A non-pathologist gold set would be a weak reference, and 70 reports would cost about 12 hours. The planned pathologist overlap was not available in time.
- Decision (author, 24 Nov): no gold set for this version.
  - Primary endpoints use registry agreement for grade, laterality and LVI.
  - The calibrator is trained on registry agreement only.
  - Fields without a registry value report answer and abstention rates only.
  - What cannot be measured is listed in §7 of the protocol, including whether `not_stated` is correct.
- The 2 gold labels are not used. The tool, guide and practice set stay for a future pathologist-led round.

**D30. Commit author e-mail rewritten before the repo goes public (25 Nov).**
- The author asked that the personal e-mail address not appear in a public history.
- All 13 commits were rewritten to the GitHub noreply address. Content and messages are unchanged, but commit ids changed.
- Run manifests in `runs/` (git-ignored) record the old ids. The mapping, old → new:

  | old | new | commit |
  |---|---|---|
  | c056157 | be707fb | Day 1: agent contract v0.1, data pipeline, site splits, labe… |
  | 5ac11c4 | 21e9c60 | Day 2: LLM extractor (vLLM + Claude API backends), confidenc… |
  | c07c346 | 0c29d77 | Colab notebook for the VS Code Colab extension: embedded cod… |
  | c1eb030 | 0ef09fb | Notebook: pin vllm 0.34.0, write every 16 reports, resume in… |
  | ef0a624 | 0d4b743 | Prompt v0.2, multi-part evidence, meaning-word guard on fuzz… |
  | abb9e1d | 7a6d403 | FIGO 1988 lower-bound rules, metrics (tie-preserving ECE, ri… |
  | 7e80b94 | f68bff8 | Protocol draft: calibrator trained on gold + silver, gold-on… |
  | dedf797 | d4cb22c | Prompt v0.3: evidence as a grammar-bounded list (max 3 quote… |
  | 287b38f | 27413aa | Notebook smoke check tolerates truncated outputs… |
  | d9ad1f7 | e1cf214 | Freeze system at prompt v0.3 in the protocol draft; log v0.3… |
  | 827ec4c | 9c6bd61 | Label tool v0.2: active-time timer (idle > 2 min and hidden/… |
  | 0eacb59 | 4d18c19 | Practice set for annotator training (5 unscored dev reports)… |
  | 0ff688b | 627d6eb | Super-agent v0 as a LangGraph graph: FIGO rules, registry co… |


**D31. README shows the example case card as an image (25 Nov).**
- Reviewer feedback the author passed on: GitHub shows `docs/example_case_card.html` as source, not as a page, so the card was invisible from the README.
- Claude Code rendered the synthetic card with headless Chrome to `docs/example_case_card.png` and embedded it under the super-agent heading.
- Checked on the screenshot: every evidence offset was the placeholder 100 and the prompt hash was empty. Both looked like bugs.
- Fix in `oac.superagent.demo`: the invented quotes now sit in an invented report string, so their offsets are real, and the example carries a synthetic prompt hash and an input hash of that string. Still no TCGA text.

**D32. Study guide published (26 Nov).**
- The author asked Claude Code for a single study guide on 19 Nov because the first background notes were hard to follow, worked through it step by step, and asked for it to be published with the repo.
- Translated from Turkish and updated to the current state: no gold set (D29), L4 runs, super-agent built, calibrator as in protocol §5.
- Removed before publishing: notes on the hiring panel and interview questions, personal to-do items and Colab steps, labelling file names.
- Checked against the data and sources before publishing: registry grades (G3 313, G2 42, G1 6), 16 stage IIC patients, 63 reports mentioning "residual", Imperial College among the test centres, and the O-RADS numbers (arXiv 2608.23061: 99.2% hybrid, 65.6–95.9% end to end, 390 masses).
- Served with GitHub Pages from `docs/`, because GitHub shows HTML files as source.
