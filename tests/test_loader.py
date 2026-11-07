"""Tests for the dataset loader (sampling, schema checks, metadata, fingerprint)."""

import numpy as np
import pandas as pd
import pytest

from datalens.ingestion.loader import clean_columns, dataset_fingerprint, load_dataset


def _csv(path, n=100, seed=0, extra_col=None, label_col=" Label"):
    rng = np.random.default_rng(seed)
    d = {" Flow Duration": rng.integers(1, 1000, n), " Pkts": rng.random(n), label_col: rng.choice(["BENIGN", "DoS"], n)}
    if extra_col:
        d[extra_col] = 1
    pd.DataFrame(d).to_csv(path, index=False)


@pytest.fixture
def raw(tmp_path):
    _csv(tmp_path / "monday.csv", 100, 0)
    _csv(tmp_path / "tuesday.csv", 60, 1)
    return tmp_path


def test_clean_columns_strips_and_rejects_duplicates():
    assert clean_columns(pd.Index([" a", "b "])) == ["a", "b"]
    with pytest.raises(ValueError, match="Duplicate"):
        clean_columns(pd.Index([" a", "a"]))


def test_full_load_metadata_and_source_column(raw):
    df, meta = load_dataset(raw, chunk_size=40)
    assert len(df) == 160 == meta["rows_loaded"] == meta["rows_in_files"]
    assert meta["is_full_dataset"] is True and meta["sample_fraction"] is None
    assert set(df["source_file"]) == {"monday.csv", "tuesday.csv"}
    assert "Label" in df.columns and "Flow Duration" in df.columns


def test_sampling_is_recorded_and_reproducible(raw):
    a, ma = load_dataset(raw, chunk_size=40, sample_fraction=0.5, seed=7)
    b, mb = load_dataset(raw, chunk_size=40, sample_fraction=0.5, seed=7)
    c, _ = load_dataset(raw, chunk_size=40, sample_fraction=0.5, seed=8)
    assert ma["is_full_dataset"] is False and ma["sample_fraction"] == 0.5
    assert 0 < len(a) < 160 and ma["rows_in_files"] == 160
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(c)


def test_sample_fraction_one_means_full(raw):
    _, meta = load_dataset(raw, sample_fraction=1)
    assert meta["is_full_dataset"] is True


@pytest.mark.parametrize("bad", [0, -0.1, 1.5])
def test_invalid_sample_fraction(raw, bad):
    with pytest.raises(ValueError, match="sample_fraction"):
        load_dataset(raw, sample_fraction=bad)


def test_schema_mismatch_across_files_raises(raw):
    _csv(raw / "wednesday.csv", 10, 2, extra_col="surprise")
    with pytest.raises(ValueError, match="columns differ"):
        load_dataset(raw)


def test_missing_label_column_raises(tmp_path):
    _csv(tmp_path / "a.csv", 10, label_col="NotLabel")
    with pytest.raises(ValueError, match="label column"):
        load_dataset(tmp_path)


def test_empty_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path)


def test_fingerprint_stable_and_sensitive_to_content(raw):
    files = sorted(raw.glob("*.csv"))
    f1 = dataset_fingerprint(files)
    assert f1 == dataset_fingerprint(files)
    (raw / "monday.csv").write_text((raw / "monday.csv").read_text().replace("BENIGN", "BENIGM", 1))
    assert dataset_fingerprint(files) != f1


def test_label_whitespace_stripped(tmp_path):
    pd.DataFrame({"x": [1, 2], " Label": ["  BENIGN ", "DoS"]}).to_csv(tmp_path / "a.csv", index=False)
    df, _ = load_dataset(tmp_path)
    assert sorted(df["Label"]) == ["BENIGN", "DoS"]


def test_cp1252_file_decodes_en_dash_not_control_char(tmp_path):
    """Regression: latin-1 before cp1252 turned byte 0x96 into '\\x96' instead of an en dash,
    creating a second spelling of the same label across files."""
    label = "Web Attack – XSS"
    pd.DataFrame({"x": [1, 2], " Label": [label, "BENIGN"]}).to_csv(
        tmp_path / "a.csv", index=False, encoding="cp1252")
    pd.DataFrame({"x": [3, 4], " Label": [label, "BENIGN"]}).to_csv(
        tmp_path / "b.csv", index=False, encoding="utf-8")
    df, meta = load_dataset(tmp_path)
    assert sorted(df["Label"].unique()) == sorted([label, "BENIGN"])  # one spelling only
    assert {p["file"]: p["encoding"] for p in meta["files"]}["a.csv"] == "cp1252"
