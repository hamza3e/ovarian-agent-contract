import pytest

from oac import splits
from oac.data import Report, parse_patient_filename, read_bcr, silver_labels, site_of

from .conftest import FIX


def test_parse_patient_filename():
    assert parse_patient_filename("TCGA-24-2261.6145afd6-e7d7") == ("TCGA-24-2261", "6145afd6-e7d7")
    with pytest.raises(ValueError):
        parse_patient_filename("BAD-24.x")
    assert site_of("TCGA-24-2261") == "24"


def test_bcr_parsing_and_silver_mapping():
    rows = read_bcr(FIX / "bcr_mini.txt")
    assert set(rows) == {"TCGA-ZZ-0001", "TCGA-ZZ-0002", "TCGA-ZZ-0003"}
    s1 = silver_labels(rows["TCGA-ZZ-0001"])
    assert s1["grade"] == "G3" and s1["laterality"] == "bilateral" and s1["lvi"] is True
    assert s1["figo_stage"] == "IIIC"
    s2 = silver_labels(rows["TCGA-ZZ-0002"])
    assert s2["grade"] is None and s2["lvi"] is None  # GX and [Not Available] are missing, not a value
    s3 = silver_labels(rows["TCGA-ZZ-0003"])
    assert s3["lvi"] is False and s3["figo_stage"] is None


def test_split_assignment():
    assert splits.split_of("24") == "dev"
    assert splits.split_of("61") == "calibration"
    assert splits.split_of("29") == "test"
    assert splits.split_of("31") == "test"  # Imperial College stays unseen


def test_test_split_locked_for_models(monkeypatch, tmp_path):
    reps = [Report("TCGA-29-0001", "u", "29", "x"), Report("TCGA-24-0001", "u", "24", "y")]
    monkeypatch.setattr(splits, "PROTOCOL", tmp_path / "PROTOCOL.md")
    monkeypatch.setattr(splits, "PROTOCOL_LOCK", tmp_path / "PROTOCOL.lock")
    monkeypatch.setenv("OAC_UNLOCK_TEST", "1")
    with pytest.raises(splits.TestSetLocked):
        splits.select(reps, "test")  # protocol does not exist yet
    # humans may label test reports, blind to models
    assert [r.site for r in splits.select(reps, "test", purpose="annotation")] == ["29"]
    assert [r.site for r in splits.select(reps, "dev")] == ["24"]


def test_test_split_unlocks_only_with_frozen_protocol(monkeypatch, tmp_path):
    import hashlib

    proto, lock = tmp_path / "PROTOCOL.md", tmp_path / "PROTOCOL.lock"
    proto.write_text("protocol v1", encoding="utf-8")
    lock.write_text(hashlib.sha256(proto.read_bytes()).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(splits, "PROTOCOL", proto)
    monkeypatch.setattr(splits, "PROTOCOL_LOCK", lock)
    reps = [Report("TCGA-29-0001", "u", "29", "x")]
    monkeypatch.delenv("OAC_UNLOCK_TEST", raising=False)
    with pytest.raises(splits.TestSetLocked):
        splits.select(reps, "test")
    monkeypatch.setenv("OAC_UNLOCK_TEST", "1")
    assert len(splits.select(reps, "test")) == 1
    proto.write_text("protocol v2 (edited after freezing)", encoding="utf-8")
    with pytest.raises(splits.TestSetLocked):
        splits.select(reps, "test")
