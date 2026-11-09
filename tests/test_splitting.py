"""Tests for stratified and day-aware splitting (synthetic fixtures only)."""

import json

import numpy as np
import pandas as pd
import pytest

from datalens.preprocessing.labels import binarize_labels
from datalens.preprocessing.splitting import (
    class_distribution, day_aware_split, leave_one_group_out_splits,
    stratified_random_split, validate_split)


@pytest.fixture
def labels():
    # 1000 benign, 100 dos, 20 xss, 3 rare, 1 singleton
    return np.array(["BENIGN"] * 1000 + ["DoS"] * 100 + ["XSS"] * 20 + ["Rare"] * 3 + ["Single"])


def test_random_split_is_reproducible_and_seed_sensitive(labels):
    a = stratified_random_split(labels, seed=42)
    b = stratified_random_split(labels, seed=42)
    c = stratified_random_split(labels, seed=43)
    assert np.array_equal(a.train_idx, b.train_idx) and np.array_equal(a.test_idx, b.test_idx)
    assert not np.array_equal(a.test_idx, c.test_idx)


def test_random_split_disjoint_and_covers_all_rows(labels):
    s = stratified_random_split(labels)
    validate_split(s, len(labels))
    assert s.train_idx.size + s.test_idx.size == len(labels)


def test_random_split_preserves_class_proportions(labels):
    s = stratified_random_split(labels, test_size=0.2)
    d = s.metadata["test_distribution"]["percent"]
    full = class_distribution(labels)["percent"]
    for c in ("BENIGN", "DoS", "XSS"):
        assert abs(d[c] - full[c]) < 1.0


def test_singleton_class_forced_to_train_and_recorded(labels):
    s = stratified_random_split(labels)
    assert s.metadata["classes_forced_to_train"] == ["Single"]
    assert "Single" in s.metadata["classes_absent_from_test"]
    assert s.metadata["train_distribution"]["counts"]["Single"] == 1     # not dropped


def test_rare_class_policy_error(labels):
    with pytest.raises(ValueError, match="cannot be stratified"):
        stratified_random_split(labels, rare_class_policy="error")


def test_unreliable_test_metric_classes_flagged(labels):
    s = stratified_random_split(labels, min_test_per_class=5)
    assert {"Rare", "Single"} <= set(s.metadata["classes_with_unreliable_test_metrics"])
    assert "BENIGN" not in s.metadata["classes_with_unreliable_test_metrics"]


def test_missing_labels_and_empty_rejected():
    with pytest.raises(ValueError, match="missing"):
        stratified_random_split(pd.Series(["A", "A", None, "B"]))
    with pytest.raises(ValueError, match="empty"):
        stratified_random_split(np.array([]))
    with pytest.raises(ValueError, match="rare_class_policy"):
        stratified_random_split(["A", "A"], rare_class_policy="drop")


def test_metadata_is_json_serializable(labels):
    json.dumps(stratified_random_split(labels).metadata)


# ----------------------------------------------------------------- day-aware
@pytest.fixture
def week():
    src = np.array(["Monday.csv"] * 50 + ["Tuesday.csv"] * 40 + ["Wednesday.csv"] * 40 + ["Thursday-am.csv"] * 20 + ["Thursday-pm.csv"] * 10)
    y = np.array(["BENIGN"] * 50 + ["BENIGN"] * 30 + ["FTP"] * 10 + ["BENIGN"] * 25 + ["DoS"] * 15
                 + ["BENIGN"] * 15 + ["XSS"] * 5 + ["Infil"] * 10)
    return src, y


def test_day_aware_no_test_file_in_training(week):
    src, y = week
    s = day_aware_split(src, y, ["monday", "tuesday"], ["thursday", "wednesday"])
    validate_split(s, len(y))
    assert set(src[s.train_idx]) == {"Monday.csv", "Tuesday.csv"}
    assert set(src[s.test_idx]) == {"Wednesday.csv", "Thursday-am.csv", "Thursday-pm.csv"}
    assert not (set(src[s.train_idx]) & set(src[s.test_idx]))


def test_day_aware_reports_unseen_classes(week):
    src, y = week
    s = day_aware_split(src, y, ["monday", "tuesday"], ["wednesday", "thursday"])
    m = s.metadata
    assert set(m["classes_absent_from_train"]) == {"DoS", "XSS", "Infil"}
    assert m["classes_absent_from_test"] == ["FTP"]
    assert m["classes_evaluable_in_both"] == ["BENIGN"]
    assert m["test_rows_in_classes_absent_from_train"] == 30
    assert any("ABSENT from training" in n for n in m["notes"])
    json.dumps(m)


def test_day_aware_thursday_pattern_matches_both_files(week):
    src, y = week
    s = day_aware_split(src, y, ["monday", "tuesday", "wednesday"], ["thursday"])
    assert s.metadata["test_files"] == ["Thursday-am.csv", "Thursday-pm.csv"]


def test_day_aware_rejects_overlap_unmatched_and_unassigned(week):
    src, y = week
    with pytest.raises(ValueError, match="BOTH"):
        day_aware_split(src, y, ["monday", "thursday"], ["thursday-am", "tuesday", "wednesday"])
    with pytest.raises(ValueError, match="matches no file"):
        day_aware_split(src, y, ["monday", "sunday"], ["tuesday"])
    with pytest.raises(ValueError, match="not assigned"):
        day_aware_split(src, y, ["monday"], ["tuesday"])
    s = day_aware_split(src, y, ["monday"], ["tuesday"], unassigned="exclude")
    assert "Wednesday.csv" in s.metadata["excluded_files"]
    with pytest.raises(ValueError, match="must not be empty"):
        day_aware_split(src, y, [], ["tuesday"])


def test_day_aware_length_mismatch_and_missing_labels(week):
    src, y = week
    with pytest.raises(ValueError, match="same length"):
        day_aware_split(src[:-1], y, ["monday"], ["tuesday"])
    with pytest.raises(ValueError, match="missing"):
        day_aware_split(src, pd.Series([None] * len(y)), ["monday"], ["tuesday"])


def test_leave_one_group_out_covers_every_group(week):
    src, y = week
    groups = {"Mon": ["monday"], "Tue": ["tuesday"], "Wed": ["wednesday"], "Thu": ["thursday"]}
    results = dict(leave_one_group_out_splits(src, y, groups))
    assert set(results) == set(groups)
    for name, s in results.items():
        validate_split(s, len(y))
        assert s.train_idx.size + s.test_idx.size == len(y)
    assert results["Thu"].metadata["test_files"] == ["Thursday-am.csv", "Thursday-pm.csv"]


def test_binarize_labels():
    assert binarize_labels(["BENIGN", "DoS", "XSS"]).tolist() == [0, 1, 1]
    with pytest.raises(ValueError, match="not found"):
        binarize_labels(["DoS"])


def test_validate_split_detects_overlap():
    from datalens.preprocessing.splitting import SplitResult
    bad = SplitResult("x", np.array([0, 1]), np.array([1, 2]))
    with pytest.raises(AssertionError, match="overlap"):
        validate_split(bad, 5)
