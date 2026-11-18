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
