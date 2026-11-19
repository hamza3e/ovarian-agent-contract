"""Build the Colab run notebook: ``dist/colab_extract_run.ipynb`` with the code embedded (base64 zip).

The Colab server (web or the VS Code extension) cannot see local files, so the code travels inside the notebook:
code, configs and synthetic fixtures only. No data, labels or runs. The zip carries a COMMIT file so outputs
produced on Colab record which code made them. Refuses to build from a dirty working tree.

    uv run python -m oac.bundle
    # then open dist/colab_extract_run.ipynb in VS Code and select a Colab GPU kernel
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import zipfile

from oac.data import REPO_ROOT

INCLUDE = ["pyproject.toml", "README.md", "src", "configs", "contract", "tests/fixtures"]
EXCLUDE_PARTS = {"__pycache__", ".ipynb_checkpoints"}
TEMPLATE = REPO_ROOT / "notebooks" / "colab_extract.ipynb"
PLACEHOLDER = "__BUNDLE_B64__"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def build_zip(commit: str) -> tuple[bytes, int]:
    buf, n = io.BytesIO(), 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for item in INCLUDE:
            p = REPO_ROOT / item
            files = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())
            for f in files:
                if EXCLUDE_PARTS & set(f.parts):
                    continue
                z.write(f, f.relative_to(REPO_ROOT).as_posix())
                n += 1
        z.writestr("COMMIT", commit + "\n")
    return buf.getvalue(), n


def embed(notebook: dict, payload_b64: str) -> dict:
    hits = 0
    for cell in notebook["cells"]:
        src = "".join(cell["source"])
        if PLACEHOLDER in src:
            cell["source"] = src.replace(PLACEHOLDER, payload_b64).splitlines(keepends=True)
            hits += 1
    if hits != 1:
        raise RuntimeError(f"expected exactly one {PLACEHOLDER} in the template, found {hits}")
    return notebook


def main() -> None:
    if _git("status", "--porcelain"):
        raise SystemExit("working tree is dirty: commit first so COMMIT identifies the code exactly")
    commit = _git("rev-parse", "HEAD")
    data, n = build_zip(commit)
    nb = embed(json.loads(TEMPLATE.read_text(encoding="utf-8")), base64.b64encode(data).decode("ascii"))
    out = REPO_ROOT / "dist" / "colab_extract_run.ipynb"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({n} files, {len(data) // 1024} KB zipped, commit {commit[:7]})")


if __name__ == "__main__":
    main()
