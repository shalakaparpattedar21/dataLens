"""Tests for bounded-memory fitting and chunked transform (synthetic data)."""

import numpy as np
import pandas as pd
import pytest

from datalens.preprocessing.fitting import fit_preprocessor, transform_in_chunks, transformed_summary
from datalens.preprocessing.pipeline import build_preprocessor


@pytest.fixture
def frames():
    rng = np.random.default_rng(0)
    train = pd.DataFrame({"a": rng.normal(10, 2, 1000), "b": rng.lognormal(1, 1, 1000)})
    train.loc[5, "a"] = np.inf
    train.loc[7, "b"] = np.nan
    test = pd.DataFrame({"a": [1e9, -1e9, np.nan], "b": [np.inf, 1.0, 2.0]})   # extreme on purpose
    return train, test


def test_full_fit_records_all_rows(frames):
    train, _ = frames
    pre = build_preprocessor(["a", "b"], cfg={"numeric": {"scaler": "standard"}})
    rec = fit_preprocessor(pre, train)
    assert rec["fit_rows_used"] == rec["train_rows"] == 1000 and rec["fit_on_subsample"] is False


def test_subsample_fit_uses_only_train_rows_and_is_reproducible(frames):
    train, test = frames
    p1 = build_preprocessor(["a", "b"], cfg={"numeric": {"scaler": "none", "imputer": "median"}})
    p2 = build_preprocessor(["a", "b"], cfg={"numeric": {"scaler": "none", "imputer": "median"}})
    r1 = fit_preprocessor(p1, train, max_fit_rows=200, seed=3)
    fit_preprocessor(p2, train, max_fit_rows=200, seed=3)
    assert r1["fit_on_subsample"] is True and r1["fit_rows_used"] == 200 and r1["fit_subsample_fraction"] == 0.2
    f1 = p1.named_transformers_["num"].named_steps["impute"].statistics_
    f2 = p2.named_transformers_["num"].named_steps["impute"].statistics_
    np.testing.assert_array_equal(f1, f2)
    # statistics equal the median of exactly the sampled TRAIN rows (inf -> NaN ignored by the imputer)
    idx = np.sort(np.random.default_rng(3).choice(1000, size=200, replace=False))
    expected = train.iloc[idx].replace([np.inf, -np.inf], np.nan).median().to_numpy()
    np.testing.assert_allclose(f1, expected)


def test_test_data_never_changes_fitted_state(frames):
    train, test = frames
    pre = build_preprocessor(["a", "b"], cfg={"numeric": {"scaler": "robust"}})
    fit_preprocessor(pre, train)
    scale_before = pre.named_transformers_["num"].named_steps["scale"].scale_.copy()
    list(transform_in_chunks(pre, test, chunk_size=2))
    np.testing.assert_array_equal(pre.named_transformers_["num"].named_steps["scale"].scale_, scale_before)


def test_chunked_transform_equals_full_transform(frames):
    train, test = frames
    pre = build_preprocessor(["a", "b"])
    fit_preprocessor(pre, train)
    full = pre.transform(train)
    chunked = np.vstack(list(transform_in_chunks(pre, train, chunk_size=137)))
    np.testing.assert_allclose(chunked, full)


def test_transformed_summary_has_no_nan_or_inf(frames):
    train, test = frames
    pre = build_preprocessor(["a", "b"])
    fit_preprocessor(pre, train)
    s = transformed_summary(pre, test, chunk_size=2)
    assert s["rows"] == 3 and s["nan_cells"] == 0 and s["inf_cells"] == 0


@pytest.mark.parametrize("bad", [0, -5])
def test_invalid_arguments(frames, bad):
    train, _ = frames
    pre = build_preprocessor(["a", "b"])
    with pytest.raises(ValueError):
        fit_preprocessor(pre, train, max_fit_rows=bad)
    with pytest.raises(ValueError):
        list(transform_in_chunks(pre, train, chunk_size=bad))


def test_empty_train_raises():
    pre = build_preprocessor(["a"])
    with pytest.raises(ValueError, match="empty"):
        fit_preprocessor(pre, pd.DataFrame({"a": pd.Series(dtype=float)}))


def test_chunked_handling_report_equals_unchunked(frames):
    from datalens.preprocessing.fitting import chunked_handling_report
    from datalens.preprocessing.pipeline import handling_reports
    train, test = frames
    pre = build_preprocessor(["a", "b"])
    fit_preprocessor(pre, train)
    whole = handling_reports(pre, train, test)
    chunked = chunked_handling_report(pre, train, test, chunk_size=137)
    for part in ("train", "test"):
        assert chunked[part] == whole[part]
    assert chunked["train_fill_values_for_affected_columns"] == whole["train_fill_values_for_affected_columns"]
    assert chunked["inf_strategy"] == whole["inf_strategy"] and chunked["imputer_strategy"] == whole["imputer_strategy"]
