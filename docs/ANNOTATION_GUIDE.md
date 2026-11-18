# Annotation guide v0.1: ovarian cancer pathology reports (TCGA-OV)

Who: the gold-set annotator (70 reports) and the pathologist (15-report overlap). Read once (~15 min) before starting.
The tool shows a short rule per field; this guide is the full version.

## Principles
1. **Label what the report says, not what is true.** No outside knowledge, no registry values, no guessing from typical HGSC behaviour.
2. **Three answers per field:**
   - **Answered:** the report supports a value.
   - **Not stated:** the report does not contain it. This is a normal, correct answer; most reports do not state residual disease.
   - **Unsure:** the report mentions it but it is ambiguous or contradictory. Give your best value if you have one, and write why in notes.
3. **Evidence:** for every answered field, select the shortest text span(s) that support it and click "+ evidence". Two short spans are better than one long paragraph.
4. **OCR noise:** read through it ("lort ovary" = left ovary; "Quentum" = omentum). If OCR destroys the meaning, use Unsure and write "OCR" in notes.
5. **Whole report:** final diagnosis, gross description, addenda and synoptic sections all count. If they conflict, the final diagnosis or addendum wins. Note the conflict.
6. Work at a steady pace; ~3–4 minutes per report. The tool records time per case, and we report annotation cost.

## Fields

| Field | Answer with | Notes and edge cases |
|---|---|---|
| primary_site | ovary / fallopian_tube / peritoneum / undetermined | `ovary` when the diagnosis is an ovarian carcinoma and no other origin is suggested. `fallopian_tube` / `peritoneum` only when stated ("primary peritoneal", "tubal origin"). `undetermined` when the report says origin is unclear ("tubo-ovarian", "Müllerian origin"). |
| histotype | high_grade_serous, low_grade_serous, serous_nos, endometrioid, clear_cell, mucinous, carcinosarcoma, mixed, other | As written. "Papillary serous adenocarcinoma, poorly differentiated" = `serous_nos` (the differentiation goes to grade). `mixed` only when two types are named for the same tumour. `other` e.g. "adenocarcinoma NOS", "undifferentiated carcinoma". |
| grade | G1, G2, G3, low_grade, high_grade | Grade 1–3 or well / moderately / poorly differentiated → G1 / G2 / G3. Several grades → the highest. Only two-tier wording ("high-grade serous") and no 3-tier grade → `high_grade`. Only nuclear grade given → use it and write "nuclear" in notes. |
| laterality | left, right, bilateral | Ovaries containing carcinoma (primary or metastatic). If the side cannot be told, use Not stated. |
| ovarian_surface_involvement | yes / no | Yes: "surface involvement", papillary growth on the surface, capsule ruptured or breached. No: "capsule intact", "no surface involvement". |
| tube_involvement | yes / no | Yes: carcinoma in a tube, including STIC (serous tubal intraepithelial carcinoma); note "STIC". No: tube examined and free of tumour. Not mentioned → Not stated. |
| uterus_involvement | yes / no | Uterine serosa, myometrium, endometrium or cervix involved by carcinoma. No: uterus examined and negative. |
| omentum_involvement | yes / no | Any carcinoma in the omentum. No: omentum examined and negative. |
| omentum_largest_deposit_cm | number (cm) | Largest dimension of the largest **tumour** deposit in the omentum. It is **not** the size of the omentum specimen. Convert mm to cm. "Omentum replaced by tumour 15 × 10 × 8 cm" → 15. Microscopic only → Not stated + note "microscopic". |
| lymph_nodes_positive | integer | Sum over all node groups ("pelvic 2/11, para-aortic 0/4" → 2). Positive but no count → Unsure + note. |
| lymph_nodes_examined | integer | Same sum (→ 15 above). |
| lymphovascular_invasion | yes / no | Lymphovascular / lymphatic / vascular / angiolymphatic invasion present → yes; explicitly absent → no; otherwise Not stated. |
| peritoneal_cytology | positive / negative / atypical | Washings, ascites or peritoneal fluid. "Suspicious" → atypical. A separate cytology report that is not included → Not stated. |
| residual_disease | none_macroscopic / le_1cm / gt_1cm | Only when the report states the disease left after surgery. "Optimal" → le_1cm; "suboptimal" → gt_1cm (note it). Usually Not stated, because this is a **surgical** finding. |

## Why these fields: FIGO staging in one page
FIGO stage is not labelled directly. The system derives it by rules from the fields above, so you only label findings.
TCGA-OV cases were staged with **FIGO 1988**. The TCGA clinical table contains stage IIC, which does not exist in FIGO 2014.

| Stage | FIGO 1988 (used by TCGA) | FIGO 2014 (current) |
|---|---|---|
| I | IA one ovary; IB both; IC + surface tumour, rupture or positive washings/ascites | IA / IB as before; IC1 surgical spill, IC2 rupture before surgery or surface tumour, IC3 positive washings/ascites |
| II | IIA uterus/tubes; IIB other pelvic tissue; IIC = IIA/B + surface, rupture or positive cytology | IIA uterus/tubes/ovaries; IIB other pelvic intraperitoneal tissue (no IIC) |
| III | IIIA microscopic peritoneal metastases beyond the pelvis; IIIB macroscopic ≤ 2 cm; **IIIC > 2 cm and/or positive regional lymph nodes** | IIIA1 positive retroperitoneal nodes only (i ≤ 10 mm, ii > 10 mm); IIIA2 microscopic extrapelvic peritoneal; IIIB ≤ 2 cm; IIIC > 2 cm (incl. liver/spleen capsule) |
| IV | Distant metastasis (incl. liver parenchyma, positive pleural cytology) | IVA pleural effusion with positive cytology; IVB parenchymal or extra-abdominal metastases (incl. inguinal nodes) |

Consequences for the system:
- The omentum lies above the pelvic brim, so omental carcinoma means stage ≥ III.
- Positive nodes alone mean IIIC in 1988 but IIIA1 in 2014.
- **Stage IV usually cannot be shown by an abdominal pathology report.** A report-only agent should give a lower bound ("≥ IIIC") and leave stage IV to imaging or clinical agents. That is one concrete reason for a multi-agent design.
