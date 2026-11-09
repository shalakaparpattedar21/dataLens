"""Tests for streaming investigation. Fixtures are SYNTHETIC with planted, hand-checkable facts."""

import json

import numpy as np
import pandas as pd
import pytest

from datalens.profiling.investigate import (
    best_decode, classify_label_bytes, combine_missing_inf, duplicate_stats_from_hashes,
    inspect_label_bytes, investigate_dataset, label_encoding_report, scan_duplicates, scan_missing_inf,
)
from datalens.reporting.investigation_report import write_investigation_outputs
from datalens.resources import estimate_matrix_gb, hardware_summary, total_ram_gb

DASH = "–"


def _write(path, df, encoding="utf-8"):
    df.to_csv(path, index=False, encoding=encoding)


def _frame(labels, dur=None, bytes_s=None, pkts=None):
    n = len(labels)
    return pd.DataFrame({
        " Flow Duration": dur if dur is not None else list(range(1, n + 1)),
        " Flow Bytes/s": bytes_s if bytes_s is not None else [1.0] * n,
        " Flow Packets/s": pkts if pkts is not None else [2.0] * n,
        " Label": labels,
    })


# ------------------------------------------------------------------ C. label bytes
def test_classify_label_bytes():
    assert classify_label_bytes(b"BENIGN") == "ascii"
    assert classify_label_bytes(b"Web Attack \x96 XSS") == "cp1252_dash_byte"
    assert classify_label_bytes("Web Attack � XSS".encode("utf-8")) == "utf8_replacement_char_in_file"
    assert classify_label_bytes(f"Web Attack {DASH} XSS".encode("utf-8")) == "utf8_dash"
    assert classify_label_bytes(b"x\xe9") == "other_non_ascii"


def test_best_decode_mirrors_loader_order():
    assert best_decode(b"Web Attack \x96 XSS") == f"Web Attack {DASH} XSS"       # cp1252, not latin-1 control char
    assert best_decode(f"Web Attack {DASH} XSS".encode("utf-8")) == f"Web Attack {DASH} XSS"


def test_inspect_label_bytes_cp1252_file(tmp_path):
    f = tmp_path / "tue.csv"
    _write(f, _frame([f"Web Attack {DASH} XSS", "BENIGN", "BENIGN"]), encoding="cp1252")
    recs = {r["raw_bytes_hex"]: r for r in inspect_label_bytes(f, chunk_size=2)}
    xss = recs[b"Web Attack \x96 XSS".hex()]
    assert xss["kind"] == "cp1252_dash_byte" and xss["rows"] == 1
    assert "\x96" in xss["decodings"]["latin-1"]                       # latin-1 would give a control char
    assert xss["loader_style_decoding"] == f"Web Attack {DASH} XSS"
    assert recs[b"BENIGN".hex()]["rows"] == 2


def test_label_report_cp1252_only_has_no_replacement_char_and_no_split(tmp_path):
    f = tmp_path / "a.csv"
    _write(f, _frame([f"Web Attack {DASH} XSS", "BENIGN"]), encoding="cp1252")
    rep = label_encoding_report([inspect_label_bytes(f)])
    assert rep["original_files_contain_utf8_replacement_char"] is False
    assert rep["class_counts_split_by_inconsistent_encoding"] is False


def test_label_report_detects_replacement_char_and_split_counts(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, _frame([f"Web Attack {DASH} XSS", "BENIGN"]), encoding="cp1252")
    _write(b, _frame(["Web Attack � XSS", "Web Attack � XSS"]), encoding="utf-8")
    rep = label_encoding_report([inspect_label_bytes(a), inspect_label_bytes(b)])
    assert rep["original_files_contain_utf8_replacement_char"] is True
    assert rep["class_counts_split_by_inconsistent_encoding"] is True
    assert rep["clean_label_counts"]["Web Attack XSS"] == 3            # 1 + 2 merged, nothing lost
    assert len(rep["distinct_raw_forms_per_clean_label"]["Web Attack XSS"]) == 2


# ------------------------------------------------------------------ A/B. missing + inf
@pytest.fixture
def mi_file(tmp_path):
    inf = np.inf
    f = tmp_path / "wed.csv"
    _write(f, _frame(
        ["DoS", "DoS", "BENIGN", "BENIGN", "BENIGN", "PortScan"],
        dur=[0, 5, 6, 0, 8, 9],
        bytes_s=[inf, -inf, 1.0, 1.0, 1.0, 1.0],
        pkts=[inf, 2.0, np.nan, 2.0, np.nan, 2.0],
    ))
    return f


def test_scan_missing_inf_counts_by_column_class_and_zero_duration(mi_file):
    r = scan_missing_inf(mi_file, chunk_size=2)           # 3 chunks: accumulation must be exact
    assert r["rows"] == 6
    assert r["pos_inf_by_column"] == {"Flow Bytes/s": 1, "Flow Packets/s": 1}
    assert r["neg_inf_by_column"] == {"Flow Bytes/s": 1}
    assert r["nan_by_column"] == {"Flow Packets/s": 2}
    assert r["inf_cells_with_zero_flow_duration"] == {"Flow Bytes/s": 1, "Flow Packets/s": 1}  # row 0 only
    assert r["rows_by_class"] == {"DoS": 2, "BENIGN": 3, "PortScan": 1}
    assert r["rows_with_inf_by_class"] == {"DoS": 2}
    assert r["rows_with_nan_by_class"] == {"BENIGN": 2}
    assert r["inf_cells_by_class_column"] == {"DoS|Flow Bytes/s": 2, "DoS|Flow Packets/s": 1}
    assert r["examples"][0]["csv_line"] == 2 and r["examples"][0]["label"] == "DoS"


def test_scan_missing_inf_chunking_is_irrelevant(mi_file):
    a, b = scan_missing_inf(mi_file, chunk_size=1), scan_missing_inf(mi_file, chunk_size=1000)
    for k in ("nan_by_column", "pos_inf_by_column", "neg_inf_by_column", "rows_by_class", "inf_cells_by_class_column"):
        assert a[k] == b[k]


def test_scan_reports_unparseable_text_cells(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text(" Flow Duration, Label\n1,A\nabc,A\n3,B\n", encoding="utf-8")
    r = scan_missing_inf(f)
    assert r["unparseable_by_column"] == {"Flow Duration": 1}


def test_combine_missing_inf_totals_and_rates(tmp_path, mi_file):
    other = tmp_path / "thu.csv"
    _write(other, _frame(["BENIGN", "BENIGN"], bytes_s=[np.inf, 1.0]))
    c = combine_missing_inf([scan_missing_inf(mi_file), scan_missing_inf(other)])
    assert c["rows"] == 8 and c["total_nan_cells"] == 2
    assert c["total_pos_inf_cells"] == 3 and c["total_neg_inf_cells"] == 1
    assert c["by_file"]["thu.csv"] == {"rows": 2, "nan_cells": 0, "inf_cells": 1}
    assert c["by_class"]["DoS"]["pct_rows_with_inf"] == 100.0
    assert c["by_class"]["BENIGN"]["rows"] == 5 and c["by_class"]["BENIGN"]["rows_with_inf"] == 1


# ------------------------------------------------------------------ D. duplicates
def test_duplicate_stats_from_hashes_hand_checked():
    h = np.array([1, 1, 2, 2, 3, 3, 4], dtype=np.uint64)
    lab = np.array(["A", "A", "A", "B", "A", "A", "A"], dtype=object)
    src = np.array(["f1", "f1", "f1", "f1", "f1", "f2", "f2"], dtype=object)
    s = duplicate_stats_from_hashes(h, lab, src)
    assert s["exact_duplicate_rows_global"] == 2            # idx1, idx5
    assert s["exact_duplicate_rows_within_file"] == 1       # idx1 only
    assert s["exact_duplicates_only_across_files"] == 1
    assert s["label_conflict_groups"] == 1 and s["label_conflict_rows"] == 2
    assert s["vectors_spanning_multiple_files"] == 1 and s["rows_in_spanning_vectors"] == 2
    assert s["spanning_vectors_with_label_disagreement"] == 0
    assert s["per_class"]["A"]["rows"] == 6 and s["per_class"]["A"]["exact_duplicate_rows"] == 2
    assert s["per_class"]["A"]["pct_removed_by_drop_exact"] == pytest.approx(33.333, abs=1e-3)
    assert s["per_class"]["B"]["rows_in_label_conflicts"] == 1


def test_scan_duplicates_label_spelling_does_not_create_false_conflicts(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    same = dict(dur=[10], bytes_s=[5.0], pkts=[6.0])
    _write(a, _frame([f"Web Attack {DASH} XSS"], **same), encoding="cp1252")
    _write(b, _frame(["Web Attack � XSS"], **same), encoding="utf-8")
    s = scan_duplicates([a, b])
    assert s["label_conflict_rows"] == 0                    # same logical class, different bytes
    assert s["vectors_spanning_multiple_files"] == 1
    assert s["exact_duplicates_only_across_files"] == 1


def test_scan_duplicates_real_conflict_detected(tmp_path):
    f = tmp_path / "a.csv"
    _write(f, _frame(["BENIGN", "DoS"], dur=[1, 1], bytes_s=[2.0, 2.0], pkts=[3.0, 3.0]))
    assert scan_duplicates([f])["label_conflict_rows"] == 2


# ------------------------------------------------------------------ driver + outputs
def test_investigate_dataset_end_to_end_and_outputs(tmp_path, mi_file):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / mi_file.name).write_bytes(mi_file.read_bytes())
    inv = investigate_dataset(raw)
    assert set(inv) == {"files", "label_encoding", "missing_and_infinite", "duplicates"}
    paths = write_investigation_outputs(inv, tmp_path / "out", hardware={"x": 1})
    assert all(p.exists() for p in paths.values())
    md = paths["report"].read_text(encoding="utf-8")
    for heading in ("## C. Label encoding", "## A. Missing values", "## B. Infinite values", "## D. Duplicates"):
        assert heading in md
    assert json.loads(paths["json"].read_text())["missing_and_infinite"]["rows"] == 6


def test_empty_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        investigate_dataset(tmp_path)


# ------------------------------------------------------------------ resources
def test_resource_helpers():
    assert estimate_matrix_gb(1_000_000, 78) == round(1_000_000 * 78 * 8 / 1024**3, 3)
    ram = total_ram_gb()
    assert ram is None or ram > 0
    hw = hardware_summary()
    assert {"platform", "python", "cpu_count", "total_ram_gb", "available_ram_gb"} <= set(hw)


def test_scan_missing_inf_groups_utf8_replacement_label_with_cp1252_label(tmp_path):
    """Regression: files are read as latin-1, so labels must be decoded before cleaning, or the
    same class appears under two names in the by-class tables."""
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, _frame([f"Web Attack {DASH} XSS"]), encoding="cp1252")
    _write(b, _frame(["Web Attack � XSS"]), encoding="utf-8")
    c = combine_missing_inf([scan_missing_inf(a), scan_missing_inf(b)])
    assert list(c["by_class"]) == ["Web Attack XSS"] and c["by_class"]["Web Attack XSS"]["rows"] == 2
