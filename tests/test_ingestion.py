"""Tests for dataset verification (Phase 1 slice of the ingestion module)."""

import numpy as np
import pandas as pd
import pytest

from datalens.config import load_config
from datalens.ingestion.verify import discover_files, scan_file, verify_dataset


def _write_csv(path, df, encoding="utf-8"):
    df.to_csv(path, index=False, encoding=encoding)


@pytest.fixture
def base_df():
    # Headers deliberately carry leading spaces, like the real CIC-IDS2017 CSVs.
    return pd.DataFrame(
        {
            " Flow Duration": [1, 2, 3, 4],
            " Flow Bytes/s": [1.0, np.inf, np.nan, 4.0],
            " Label": ["BENIGN", "BENIGN", "DoS", "BENIGN"],
        }
    )


def test_config_loads():
    cfg = load_config()
    assert cfg["project"]["random_seed"] == 42
    assert cfg["ingestion"]["label_column"] == "Label"


def test_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_discover_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        discover_files(tmp_path / "missing")


def test_discover_empty_dir_raises_helpful_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="README"):
        discover_files(tmp_path)


def test_scan_counts_rows_nan_inf_and_labels(tmp_path, base_df):
    f = tmp_path / "a.csv"
    _write_csv(f, base_df)
    r = scan_file(f, label_column="Label", chunk_size=2)  # forces multiple chunks
    assert r["error"] is None
    assert r["rows"] == 4
    assert r["n_columns"] == 3
    assert r["columns"][0] == "Flow Duration"  # whitespace stripped
    assert r["nan_cells"] == 1
    assert r["inf_cells"] == 1
    assert r["label_counts"] == {"BENIGN": 3, "DoS": 1}


def test_scan_chunked_matches_unchunked(tmp_path, base_df):
    f = tmp_path / "a.csv"
    _write_csv(f, base_df)
    a = scan_file(f, chunk_size=1)
    b = scan_file(f, chunk_size=1000)
    for key in ("rows", "nan_cells", "inf_cells", "label_counts"):
        assert a[key] == b[key]


def test_scan_encoding_fallback(tmp_path):
    df = pd.DataFrame({" Flow Duration": [1, 2], " Label": ["Web Attack – XSS", "BENIGN"]})
    f = tmp_path / "latin.csv"
    _write_csv(f, df, encoding="cp1252")  # en dash is byte 0x96: invalid UTF-8
    r = scan_file(f)
    assert r["error"] is None
    assert r["encoding"] in ("latin-1", "cp1252")
    assert r["rows"] == 2


def test_scan_missing_label_column_reported(tmp_path):
    f = tmp_path / "nolabel.csv"
    _write_csv(f, pd.DataFrame({"a": [1, 2], "b": [3, 4]}))
    r = scan_file(f, label_column="Label")
    assert "Label column" in r["error"]
    assert r["has_label_column"] is False


def test_scan_empty_file_reported_not_raised(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("")
    r = scan_file(f)
    assert r["error"] is not None


def test_scan_flags_non_numeric_feature_columns(tmp_path):
    f = tmp_path / "mixed.csv"
    _write_csv(f, pd.DataFrame({"x": [1, 2], "ip": ["a", "b"], "Label": ["BENIGN", "DoS"]}))
    r = scan_file(f)
    assert r["non_numeric_columns"] == ["ip"]


def test_verify_dataset_aggregates_and_detects_schema_mismatch(tmp_path, base_df):
    _write_csv(tmp_path / "a.csv", base_df)
    _write_csv(tmp_path / "b.csv", base_df)
    rep = verify_dataset(tmp_path)
    assert rep["n_files"] == 2
    assert rep["total_rows"] == 8
    assert rep["schema_consistent_across_files"] is True
    assert rep["label_counts"] == {"BENIGN": 6, "DoS": 2}

    _write_csv(tmp_path / "c.csv", base_df.rename(columns={" Flow Duration": " Duration"}))
    rep2 = verify_dataset(tmp_path)
    assert rep2["schema_consistent_across_files"] is False
