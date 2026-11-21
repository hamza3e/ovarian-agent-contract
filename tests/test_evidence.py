from oac.contract import AgentOutput, EvidenceSpan, FieldResult, Provenance, Status, sha256_text
from oac.evidence import locate, verify_output

TEXT = "OVARY, LEFT, EXCISION - ADENOCARCINOMA, POORLY DIFFERENTIATED. EXTENSIVE LYMPHATIC INVASION IDENTIFIED."


def test_exact_match_offsets():
    s = locate("POORLY DIFFERENTIATED", TEXT)
    assert s.verified and TEXT[s.start:s.end] == "POORLY DIFFERENTIATED"


def test_case_and_whitespace_insensitive():
    s = locate("adenocarcinoma,   poorly differentiated", TEXT)
    assert s.verified and s.match_score == 100.0


def test_fuzzy_ocr_like_quote():
    s = locate("extensive lymphatic invasion identifed", TEXT)  # model fixed/introduced a typo
    assert s.verified and s.match_score >= 90


def test_hallucinated_quote_rejected():
    s = locate("well differentiated mucinous carcinoma of the appendix", TEXT)
    assert not s.verified


def test_verify_output_warns_on_unverified_answer():
    out = AgentOutput(
        case_id="c", modality="pathology_report",
        provenance=Provenance(agent_name="t", agent_version="0", input_sha256=sha256_text(TEXT)),
        fields=[FieldResult(field="grade", status=Status.answered, value="G1",
                            evidence=[EvidenceSpan(quote="well differentiated tumour of low grade")])],
    )
    checked = verify_output(out, TEXT)
    assert not checked.fields[0].evidence[0].verified
    assert any("without verified evidence" in w for w in checked.warnings)


def test_fuzzy_match_cannot_flip_meaning_words():
    from oac.evidence import guard_ok, locate

    text = "B. Ovary, left, salpingo-oophorectomy: Metastatic carcinoma. Omentum: no tumor identified. Nodes 0/6."
    assert not locate("Ovary, right, salpingo-oophorectomy: Metastatic carcinoma", text).verified
    assert locate("Ovary, left, salpingo-oophorectomy: Metastatic carcinma", text).verified  # OCR-style typo is fine
    assert not locate("Omentum: tumor identified. Nodes 2/6", text).verified
    assert guard_ok("no tumor in 2 nodes", "no tumour in 2 nodes") and not guard_ok("2 nodes", "0 nodes")
