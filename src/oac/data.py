"""Load TCGA-OV pathology reports (TCGA-Reports, CC BY 4.0) and the TCGA-OV clinical table (GDC BCR Biotab).

Never print or log report text from this module; callers decide what to show.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("OAC_DATA_DIR", REPO_ROOT / "data"))
REPORTS_CSV = DATA_DIR / "raw" / "tcga-reports" / "TCGA_Reports.csv"
BCR_PATIENT = DATA_DIR / "raw" / "gdc" / "clinical_patient_ov.txt"

# TCGA tissue source site codes for the OV reports (GDC code table, checked 2026-11-18).
SITE_NAMES: dict[str, str] = {
    "24": "Washington University", "61": "University of Pittsburgh", "29": "Duke", "23": "Cedars Sinai",
    "09": "UCSF", "36": "BC Cancer Agency", "30": "Harvard", "10": "MD Anderson Cancer Center",
    "59": "Roswell Park", "57": "International Genomics Consortium", "31": "Imperial College",
    "20": "Fox Chase Cancer Center", "42": "Christiana Healthcare", "13": "Memorial Sloan Kettering",
    "25": "Mayo Clinic - Rochester", "OY": "University of North Carolina",
    "VG": "Institute of Human Virology Nigeria", "5X": "University of Alabama", "3P": "Greenville Health System",
    "WR": "University of Kansas",
}

_MISSING = {"", "[Not Available]", "[Unknown]", "[Not Applicable]", "[Not Evaluated]", "[Discrepancy]"}


@dataclass(frozen=True)
class Report:
    case_id: str  # TCGA-XX-XXXX
    report_uuid: str
    site: str  # tissue source site code (XX)
    text: str


def parse_patient_filename(name: str) -> tuple[str, str]:
    """'TCGA-24-2261.6145afd6-...' -> ('TCGA-24-2261', '6145afd6-...')."""
    case_id, _, uuid = name.partition(".")
    if not (case_id.startswith("TCGA-") and len(case_id) == 12):
        raise ValueError(f"unexpected patient_filename: {name!r}")
    return case_id, uuid


def site_of(case_id: str) -> str:
    return case_id.split("-")[1]


def read_bcr(path: Path = BCR_PATIENT) -> dict[str, dict[str, str]]:
    """BCR Biotab: row 0 = column names, rows 1-2 = CDE descriptors, data from row 3."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    out: dict[str, dict[str, str]] = {}
    for line in lines[3:]:
        row = dict(zip(header, line.split("\t"), strict=False))
        out[row["bcr_patient_barcode"]] = row
    return out


def load_ov_reports(reports_csv: Path = REPORTS_CSV, bcr_path: Path = BCR_PATIENT) -> list[Report]:
    """All TCGA-Reports rows whose case is in the TCGA-OV clinical table, sorted by case id."""
    csv.field_size_limit(10**9)
    ov_cases = set(read_bcr(bcr_path))
    reports: list[Report] = []
    with reports_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            case_id, uuid = parse_patient_filename(row["patient_filename"])
            if case_id in ov_cases:
                reports.append(Report(case_id, uuid, site_of(case_id), row["text"]))
    reports.sort(key=lambda r: r.case_id)
    return reports


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if value in _MISSING else value


def silver_labels(row: dict[str, str]) -> dict[str, object]:
    """Map one BCR clinical row to silver labels. None = not available in the registry.

    These are registry values, not ground truth: they were abstracted by each site and may disagree with the
    report (that disagreement is itself measured, see eval/PROTOCOL.md).
    """
    grade = _clean(row.get("tumor_grade"))
    lat = _clean(row.get("anatomic_neoplasm_subdivision"))
    lvi = _clean(row.get("lymphovascular_invasion_indicator"))
    stage = _clean(row.get("clinical_stage"))
    return {
        "grade": grade if grade in {"G1", "G2", "G3"} else None,
        "laterality": {"Bilateral": "bilateral", "Left": "left", "Right": "right"}.get(lat or ""),
        "lvi": {"YES": True, "NO": False}.get(lvi or ""),
        "figo_stage": stage.replace("Stage ", "") if stage else None,
        "residual_largest_nodule": _clean(row.get("residual_disease_largest_nodule")),
        "dx_year": _clean(row.get("initial_pathologic_dx_year")),
    }
