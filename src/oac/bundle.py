"""Build ``dist/oac-code.zip`` for Colab: code, configs and synthetic fixtures only. No data, labels or runs.

Upload the zip to Google Drive (MyDrive/oac/) and run notebooks/colab_extract.ipynb. The zip carries a COMMIT
file so outputs produced on Colab record which code made them. Refuses to build from a dirty working tree.
"""

from __future__ import annotations

import subprocess
import zipfile

from oac.data import REPO_ROOT

INCLUDE = ["pyproject.toml", "README.md", "src", "configs", "contract", "tests/fixtures", "notebooks"]
EXCLUDE_PARTS = {"__pycache__", ".ipynb_checkpoints"}


def main() -> None:
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True,
                           check=True).stdout.strip()
    if dirty:
        raise SystemExit("working tree is dirty: commit first so COMMIT identifies the code exactly")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    out = REPO_ROOT / "dist" / "oac-code.zip"
    out.parent.mkdir(exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in INCLUDE:
            p = REPO_ROOT / item
            files = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())
            for f in files:
                if EXCLUDE_PARTS & set(f.parts):
                    continue
                z.write(f, f.relative_to(REPO_ROOT).as_posix())
                n += 1
        z.writestr("COMMIT", commit + "\n")
    print(f"wrote {out} ({n} files, commit {commit[:7]})")


if __name__ == "__main__":
    main()
