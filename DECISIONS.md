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
