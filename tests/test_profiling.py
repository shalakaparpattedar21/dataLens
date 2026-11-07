"""Tests for the profiler. Each fixture plants a KNOWN problem so assertions are checkable."""

import numpy as np
import pandas as pd
import pytest

from datalens.profiling import columns_frame, profile_dataframe
from datalens.profiling.profiler import profile_duplicates


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "a": [1.0, 2.0, 3.0, 4.0, 100.0, np.nan],   # one outlier, one NaN
            "b": [5.0, 5.0, 5.0, 5.0, 5.0, 5.0],        # constant
            "c": [1.0, np.inf, 2.0, 3.0, 4.0, 5.0],     # one inf
            "d": ["x", "y", "x", "y", "x", "y"],
            "Label": ["BENIGN", "BENIGN", "BENIGN", "BENIGN", "BENIGN", "DoS"],
            "src": ["mon.csv"] * 3 + ["tue.csv"] * 3,
        }
    )


def test_shape_and_excluded_columns(df):
    p = profile_dataframe(df, "Label", source_column="src")
    assert p["shape"]["rows"] == 6
    names = [c["column"] for c in p["columns"]]
    assert names == ["a", "b", "c", "d"]  # label and source column are not features


def test_missing_inf_constant_detection(df):
    cols = columns_frame(profile_dataframe(df, "Label", source_column="src")).set_index("column")
    assert cols.loc["a", "missing_n"] == 1
    assert cols.loc["a", "missing_pct"] == pytest.approx(100 / 6, abs=1e-3)
    assert cols.loc["c", "inf_n"] == 1
    assert bool(cols.loc["b", "is_constant"]) is True
    assert bool(cols.loc["a", "is_constant"]) is False


def test_stats_use_finite_values_only(df):
    cols = columns_frame(profile_dataframe(df, "Label", source_column="src")).set_index("column")
    assert cols.loc["c", "max"] == 5.0          # inf excluded
    assert cols.loc["a", "max"] == 100.0


def test_outlier_flagged_not_removed(df):
    p = profile_dataframe(df, "Label", source_column="src")
    cols = columns_frame(p).set_index("column")
    assert cols.loc["a", "outlier_iqr_n"] == 1
    assert p["shape"]["rows"] == 6  # profiling never alters data
    assert len(df) == 6


def test_target_distribution_and_by_source(df):
    t = profile_dataframe(df, "Label", source_column="src")["target"]
    assert t["counts"] == {"BENIGN": 5, "DoS": 1}
    assert t["imbalance_ratio"] == 5.0
    assert t["majority_class"] == "BENIGN" and t["minority_class"] == "DoS"
    assert t["by_source"]["tue.csv"] == {"BENIGN": 2, "DoS": 1}


def test_categorical_numeric_like_share():
    d = pd.DataFrame({"n": ["1", "2", "3", "x"], "Label": list("aabb")})
    c = columns_frame(profile_dataframe(d, "Label")).set_index("column")
    assert c.loc["n", "kind"] == "categorical"
    assert c.loc["n", "numeric_like_share"] == 0.75


def test_duplicates_and_label_conflicts():
    d = pd.DataFrame(
        {
            "f1": [1, 1, 1, 2, 3],
            "f2": [9, 9, 9, 8, 7],
            "Label": ["A", "A", "B", "A", "A"],
        }
    )
    r = profile_duplicates(d, ["f1", "f2"], "Label")
    assert r["duplicate_rows_full"] == 1        # second (1,9,A)
    assert r["duplicate_rows_features"] == 2    # rows 2 and 3 repeat features of row 1
    assert r["label_conflict_groups"] == 1      # (1,9) has labels A and B
    assert r["label_conflict_rows"] == 3


def test_no_duplicates_on_unique_rows():
    d = pd.DataFrame({"f": [1, 2, 3], "Label": ["A", "B", "A"]})
    r = profile_duplicates(d, ["f"], "Label")
    assert r["duplicate_rows_full"] == 0 and r["label_conflict_rows"] == 0


def test_empty_dataframe_and_missing_label():
    empty = pd.DataFrame({"f": pd.Series(dtype=float), "Label": pd.Series(dtype=str)})
    assert profile_dataframe(empty, "Label")["duplicates"]["duplicate_rows_full"] == 0
    with pytest.raises(KeyError):
        profile_dataframe(pd.DataFrame({"f": [1]}), "Label")


def test_all_nan_numeric_column_does_not_crash():
    d = pd.DataFrame({"f": [np.nan, np.nan], "Label": ["A", "B"]})
    c = columns_frame(profile_dataframe(d, "Label")).set_index("column")
    assert c.loc["f", "missing_n"] == 2
    assert c.loc["f", "min"] is None or pd.isna(c.loc["f", "min"])
