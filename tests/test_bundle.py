"""The Colab notebook carries the code: check the embedded bundle has code only and unpacks as the cell does."""

import base64
import json

import pytest

from oac import bundle


def test_bundle_has_code_and_no_data():
    data, n = bundle.build_zip("abc123")
    import io
    import zipfile

    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert n == len(names) - 1 and "COMMIT" in names
    assert "src/oac/contract.py" in names and "src/oac/run_llm.py" in names and "pyproject.toml" in names
    assert not [x for x in names if x.startswith(("data/", "runs/", "labeling/", "notebooks/", ".env"))]


def test_template_cell_unpacks_embedded_bundle(tmp_path):
    data, _ = bundle.build_zip("abc123")
    nb = bundle.embed(json.loads(bundle.TEMPLATE.read_text()), base64.b64encode(data).decode())
    cell = next("".join(c["source"]) for c in nb["cells"] if "BUNDLE_B64 =" in "".join(c["source"]))
    exec(cell.replace('"/content/oac"', repr(str(tmp_path / "oac"))), {"print": lambda *a: None})
    assert (tmp_path / "oac" / "COMMIT").read_text().strip() == "abc123"
    assert (tmp_path / "oac" / "src" / "oac" / "splits.py").exists()


def test_template_refuses_to_run_without_payload(tmp_path):
    nb = json.loads(bundle.TEMPLATE.read_text())
    cell = next("".join(c["source"]) for c in nb["cells"] if "BUNDLE_B64 =" in "".join(c["source"]))
    with pytest.raises(SystemExit, match="template"):
        exec(cell.replace('"/content/oac"', repr(str(tmp_path / "oac"))), {})


def test_embed_requires_exactly_one_placeholder():
    with pytest.raises(RuntimeError):
        bundle.embed({"cells": [{"source": ["no placeholder"]}]}, "x")
