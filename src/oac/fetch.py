"""Download the public inputs into data/raw and check their sha256 (pinned 2026-11-18).

Sources:
- TCGA-Reports (Kefeli & Tatonetti 2024; data CC BY 4.0, code MIT): github.com/jkefeli/tcga-path-reports
- TCGA-OV clinical patient table, GDC open access, file id 30c149ac-9ac2-4f51-88a3-68bb4afb50a9
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

from oac.data import BCR_PATIENT, REPORTS_CSV

SOURCES = [
    (
        "https://github.com/jkefeli/tcga-path-reports/raw/main/TCGA_Reports.csv.zip",
        REPORTS_CSV.with_suffix(".csv.zip"),
        "bbbc0ee0c75d8feb0bb246b4fa40e8e29bba9775d4a9e4f41e0b73a7955e1c12",
    ),
    (
        "https://api.gdc.cancer.gov/data/30c149ac-9ac2-4f51-88a3-68bb4afb50a9",
        BCR_PATIENT,
        "92b45c6e71f4087a8a25be2b7100fc44c9cae0041c67e418c214d4d235048329",
    ),
]
REPORTS_CSV_SHA256 = "9ee5c9cd65f76ba97a864a7465ab969b6e70c28a7860129434daa9a915294507"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ovarian-agent-contract/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:  # noqa: S310 (fixed URLs)
        shutil.copyfileobj(resp, out)


def main() -> None:
    for url, dest, digest in SOURCES:
        if not dest.exists() or sha256_file(dest) != digest:
            print(f"downloading {url}")
            _download(url, dest)
        got = sha256_file(dest)
        if got != digest:
            raise SystemExit(f"sha256 mismatch for {dest.name}: {got}")
        print(f"ok {dest.name}")
    if not REPORTS_CSV.exists() or sha256_file(REPORTS_CSV) != REPORTS_CSV_SHA256:
        with zipfile.ZipFile(REPORTS_CSV.with_suffix(".csv.zip")) as zf:
            with zf.open("TCGA_Reports.csv") as src, REPORTS_CSV.open("wb") as out:
                shutil.copyfileobj(src, out)
    if sha256_file(REPORTS_CSV) != REPORTS_CSV_SHA256:
        raise SystemExit("sha256 mismatch for TCGA_Reports.csv")
    print(f"ok {REPORTS_CSV.name}")


if __name__ == "__main__":
    main()
