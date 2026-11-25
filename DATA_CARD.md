# Data card

| | |
|---|---|
| Reports | TCGA-Reports: Kefeli J, Tatonetti N. *TCGA-Reports: A machine-readable pathology report resource for benchmarking text-based AI models.* Patterns 2024. Data: Mendeley Data 10.17632/hyg5xkznpx.1, **CC BY 4.0**. Code: github.com/jkefeli/tcga-path-reports (MIT). |
| Clinical table | GDC TCGA-OV BCR Biotab `nationwidechildrens.org_clinical_patient_ov.txt` (file id 30c149ac-9ac2-4f51-88a3-68bb4afb50a9), open access. |
| Subset used | 371 reports whose case appears in the TCGA-OV clinical table (one report per case), 20 tissue-source sites. |
| Text | OCR of scanned PDF reports, cleaned by the dataset authors. OCR errors remain ("lort ovary", "Quentum"). Median 5,848 characters (217–18,743). |
| Population | Serous ovarian cystadenocarcinoma (TCGA-OV), mostly diagnosed 1999–2009, US sites plus BC Cancer (CA), Imperial College (UK), IHV Nigeria. Almost all FIGO 1988 stage III–IV, grade 3. Not representative of current practice (pre-2014 FIGO, little tubal-origin language, few BRCA/IHC mentions). |
| Silver labels | Grade, laterality, lymphovascular invasion and stage, from the registry table. They were abstracted by each site and can disagree with the report; agreement is measured, not assumed. |
| Gold labels | None. A 70-report gold set was planned and paused after a pilot (DECISIONS D29): credible labels for these fields need a pathologist. The evaluation uses the registry (silver) instead. |
| Splits | By site (see `src/oac/splits.py`): dev 109 / calibration 75 / test 187 reports. |
| PHI | The reports are de-identified public data. Still, no report text is committed, logged or pasted into issues. |
| Known biases | Site formats differ (templates, synoptic sections), so models can learn site style. Older terminology. English only. Very few low-stage or low-grade cases, so metrics on those classes are unstable. |
