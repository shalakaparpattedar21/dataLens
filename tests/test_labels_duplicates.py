"""Tests for label canonicalization and duplicate policies (synthetic fixtures only)."""

import numpy as np
import pandas as pd
import pytest

from datalens.preprocessing.duplicates import (
    POLICIES, apply_duplicate_policy, cross_file_duplicates, duplicate_masks)
from datalens.preprocessing.labels import build_label_mapping, canonicalize_labels, clean_label
from datalens.profiling.profiler import profile_duplicates


# ------------------------------------------------------------------ labels
@pytest.mark.parametrize("raw,expected", [
    ("Web Attack \x96 Brute Force", "Web Attack Brute Force"),       # latin-1 view of cp1252 dash
    ("Web Attack – XSS", "Web Attack XSS"),                      # en dash
    ("Web Attack � Sql Injection", "Web Attack Sql Injection"),  # replacement char
    ("FTP-Patator", "FTP-Patator"),                                   # ASCII hyphen untouched
    ("  BENIGN ", "BENIGN"),
])
def test_clean_label(raw, expected):
    assert clean_label(raw) == expected


def test_variants_of_same_label_merge_and_counts_add_up():
    counts = pd.Series({"Web Attack \x96 XSS": 5, "Web Attack � XSS": 3, "Web Attack – XSS": 2, "BENIGN": 90})
    mapping, rep = build_label_mapping(counts)
    assert set(mapping.values()) == {"Web Attack XSS", "BENIGN"}
    assert rep["clean_counts"]["Web Attack XSS"] == 10
    assert len(rep["merged_groups"]["Web Attack XSS"]) == 3


def test_similar_but_different_labels_are_not_merged():
    counts = pd.Series({"Web Attack - XSS": 4, "Web Attack XSS": 6})   # ASCII hyphen: not an artifact
    mapping, rep = build_label_mapping(counts)
    assert mapping["Web Attack - XSS"] == "Web Attack - XSS"
    assert rep["merged_groups"] == {}
    assert rep["similar_not_merged"] == [["Web Attack - XSS", "Web Attack XSS"]]


def test_different_classes_never_merged():
    counts = pd.Series({"Web Attack – XSS": 4, "Web Attack – Brute Force": 6})
    mapping, _ = build_label_mapping(counts)
    assert len(set(mapping.values())) == 2


def test_canonicalize_preserves_raw_and_total_rows():
    df = pd.DataFrame({"x": range(4), "Label": ["Web Attack \x96 XSS", "Web Attack – XSS", "BENIGN", "BENIGN"]})
    rep = canonicalize_labels(df, "Label")
    assert sorted(df["Label"].unique()) == ["BENIGN", "Web Attack XSS"]
    assert df["label_raw"].astype(str).tolist()[0] == "Web Attack \x96 XSS"   # original kept
    assert df["Label"].value_counts().sum() == 4
    assert rep["n_raw_labels"] == 3 and rep["n_clean_labels"] == 2


def test_canonicalize_refuses_to_overwrite_raw_and_missing_labels():
    df = pd.DataFrame({"Label": ["A"], "label_raw": ["A"]})
    with pytest.raises(ValueError, match="already exists"):
        canonicalize_labels(df, "Label")
    with pytest.raises(ValueError, match="missing"):
        canonicalize_labels(pd.DataFrame({"Label": ["A", None]}), "Label")
    with pytest.raises(KeyError):
        canonicalize_labels(pd.DataFrame({"x": [1]}), "Label")


# --------------------------------------------------------------- duplicates
@pytest.fixture
def dup_df():
    return pd.DataFrame({
        "f1": [1, 1, 1, 2, 3, 3],
        "f2": [9, 9, 9, 8, 7, 7],
        "Label": ["A", "A", "B", "A", "C", "C"],
        "src": ["mon", "mon", "tue", "tue", "mon", "tue"],
    })


def test_masks_match_profiler_counts(dup_df):
    m = duplicate_masks(dup_df, ["f1", "f2"], "Label")
    p = profile_duplicates(dup_df, ["f1", "f2"], "Label")
    assert int(m["exact"].sum()) == p["duplicate_rows_full"] == 2
    assert int(m["conflict"].sum()) == p["label_conflict_rows"] == 3


def test_policy_keep_returns_same_frame_untouched(dup_df):
    out, rep = apply_duplicate_policy(dup_df, ["f1", "f2"], "Label", "keep")
    assert out is dup_df and rep["rows_removed"] == 0


@pytest.mark.parametrize("policy,removed", [("drop_exact", 2), ("drop_conflicts", 3), ("drop_exact_and_conflicts", 4)])
def test_policies_remove_expected_rows(dup_df, policy, removed):
    out, rep = apply_duplicate_policy(dup_df, ["f1", "f2"], "Label", policy)
    assert rep["rows_removed"] == removed and len(out) == len(dup_df) - removed
    assert list(out.index) == list(range(len(out)))      # fresh RangeIndex
    assert len(dup_df) == 6                              # input untouched


def test_removal_reported_per_class_and_warns_on_class_wipeout():
    df = pd.DataFrame({"f": [1, 1, 2, 2], "Label": ["A", "B", "A", "A"]})   # vector 1 conflicts
    out, rep = apply_duplicate_policy(df, ["f"], "Label", "drop_conflicts")
    assert rep["removed_by_class"] == {"A": 1, "B": 1}
    assert rep["classes_lost_entirely"] == ["B"]
    assert any("removed ENTIRELY" in w for w in rep["warnings"])


def test_unknown_policy_rejected(dup_df):
    assert "keep" in POLICIES
    with pytest.raises(ValueError, match="Unknown duplicate policy"):
        apply_duplicate_policy(dup_df, ["f1", "f2"], "Label", "drop_everything")


def test_cross_file_duplicates(dup_df):
    r = cross_file_duplicates(dup_df, ["f1", "f2"], "Label", "src")
    # (3,7) is in mon and tue with the same label; (1,9) is in mon and tue with labels A and B
    assert r["n_groups_spanning_files"] == 2
    assert r["n_spanning_groups_with_label_disagreement"] == 1
    with pytest.raises(KeyError):
        cross_file_duplicates(dup_df, ["f1"], "Label", "nope")


def test_empty_frame_is_safe():
    df = pd.DataFrame({"f": pd.Series(dtype=float), "Label": pd.Series(dtype=str)})
    out, rep = apply_duplicate_policy(df, ["f"], "Label", "drop_exact")
    assert len(out) == 0 and rep["rows_removed"] == 0
