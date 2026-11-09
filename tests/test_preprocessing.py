"""Tests for the leakage-safe preprocessing pipeline (synthetic fixtures only)."""

import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline

from datalens.preprocessing.pipeline import (
    InfiniteValueHandler, build_preprocessor, handling_reports, split_columns, validate_preprocessing_config)


@pytest.fixture
def train():
    return pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, np.nan], "b": [10.0, 20.0, 30.0, np.inf, 50.0],
                         "c": ["x", "y", "x", "x", None]})


@pytest.fixture
def test():
    return pd.DataFrame({"a": [100.0, np.nan], "b": [-np.inf, np.inf], "c": ["z", None]})


# ---------------------------------------------------------------- infinities
def test_inf_handler_nan_strategy_counts_and_does_not_mutate():
    X = np.array([[1.0, np.inf], [np.nan, -np.inf], [3.0, 4.0]])
    original = X.copy()
    h = InfiniteValueHandler("nan").fit(X)
    out = h.transform(X)
    assert np.isnan(out[0, 1]) and np.isnan(out[1, 1]) and np.isnan(out[1, 0])
    assert out[2, 1] == 4.0 and out[0, 0] == 1.0
    np.testing.assert_array_equal(X, original)                     # input untouched
    rep = h.last_transform_report_
    assert rep["n_positive_inf"] == 1 and rep["n_negative_inf"] == 1


def test_inf_clip_uses_training_bounds_not_test_values():
    train = np.array([[1.0], [5.0], [np.inf]])
    test = np.array([[np.inf], [1000.0], [-np.inf]])
    h = InfiniteValueHandler("clip").fit(train)
    out = h.transform(test)
    assert out[0, 0] == 5.0           # train finite max, NOT test's 1000
    assert out[1, 0] == 1000.0        # finite values untouched
    assert out[2, 0] == 1.0           # train finite min


def test_inf_handler_validation():
    with pytest.raises(ValueError, match="strategy"):
        InfiniteValueHandler("zero").fit(np.ones((2, 2)))
    h = InfiniteValueHandler().fit(np.ones((2, 2)))
    with pytest.raises(ValueError, match="Expected 2 features"):
        h.transform(np.ones((2, 3)))


def test_all_inf_column_does_not_crash():
    h = InfiniteValueHandler("clip").fit(np.array([[np.inf], [np.inf]]))
    assert np.isnan(h.finite_min_[0])


# ------------------------------------------------------------ leakage checks
def test_imputer_and_scaler_use_training_statistics_only():
    rng = np.random.default_rng(0)
    tr = pd.DataFrame({"f": rng.normal(10, 1, 200)})
    te = pd.DataFrame({"f": rng.normal(500, 50, 200)})                # very different distribution
    tr.loc[0, "f"] = np.nan
    pre = build_preprocessor(["f"], cfg={"numeric": {"scaler": "standard", "imputer": "median"}}).fit(tr)
    num = pre.named_transformers_["num"]
    assert num.named_steps["impute"].statistics_[0] == pytest.approx(tr["f"].median())
    assert num.named_steps["scale"].mean_[0] == pytest.approx(tr["f"].fillna(tr["f"].median()).mean())
    assert abs(num.named_steps["scale"].mean_[0] - te["f"].mean()) > 400   # test mean NOT absorbed


def test_transform_does_not_change_fitted_parameters():
    rng = np.random.default_rng(1)
    tr, te = pd.DataFrame({"f": rng.normal(0, 1, 100)}), pd.DataFrame({"f": rng.normal(99, 9, 50)})
    pre = build_preprocessor(["f"]).fit(tr)
    sc = pre.named_transformers_["num"].named_steps["scale"]
    before = (sc.mean_.copy(), sc.scale_.copy())
    pre.transform(te)
    np.testing.assert_array_equal(before[0], sc.mean_)
    np.testing.assert_array_equal(before[1], sc.scale_)


def test_fitting_on_train_plus_test_would_differ_sanity_check():
    """Guards the leakage tests above against being vacuous."""
    rng = np.random.default_rng(2)
    tr, te = pd.DataFrame({"f": rng.normal(0, 1, 100)}), pd.DataFrame({"f": rng.normal(50, 5, 100)})
    a = build_preprocessor(["f"]).fit(tr).named_transformers_["num"].named_steps["scale"].mean_[0]
    b = build_preprocessor(["f"]).fit(pd.concat([tr, te])).named_transformers_["num"].named_steps["scale"].mean_[0]
    assert abs(a - b) > 10


def test_train_median_used_for_test_missing_and_inf(train, test):
    pre = build_preprocessor(["a", "b"], cfg={"numeric": {"scaler": "none"}}).fit(train[["a", "b"]])
    out = pre.transform(test[["a", "b"]])
    assert out[1, 0] == train["a"].median()                         # NaN in test -> TRAIN median of a
    b_med = train["b"].replace(np.inf, np.nan).median()
    assert out[0, 1] == b_med and out[1, 1] == b_med                 # +/-inf in test -> TRAIN median of b


def test_no_zero_fill_for_infinities(train):
    pre = build_preprocessor(["b"], cfg={"numeric": {"scaler": "none"}}).fit(train[["b"]])
    out = pre.transform(train[["b"]])
    assert out[3, 0] != 0.0 and out[3, 0] == train["b"].replace(np.inf, np.nan).median()


# ---------------------------------------------------------------- categorical
def test_unknown_category_and_missing_handled_from_training_only(train, test):
    pre = build_preprocessor(["a"], ["c"]).fit(train[["a", "c"]])
    names = list(pre.get_feature_names_out())
    out = pre.transform(test[["a", "c"]])
    assert set(n for n in names if n.startswith("c_")) == {"c_x", "c_y"}   # no 'z' learned
    row_unknown = out[0, [names.index("c_x"), names.index("c_y")]]
    assert row_unknown.tolist() == [0.0, 0.0]                              # unseen 'z' -> all zeros
    row_missing = out[1, [names.index("c_x"), names.index("c_y")]]
    assert row_missing.tolist() == [1.0, 0.0]                              # None -> train mode 'x'


def test_handle_unknown_error_config(train, test):
    pre = build_preprocessor(["a"], ["c"], {"categorical": {"handle_unknown": "error"}}).fit(train[["a", "c"]])
    with pytest.raises(ValueError):
        pre.transform(test[["a", "c"]])


# --------------------------------------------------------- shapes / indicators
def test_feature_names_match_output_columns(train):
    pre = build_preprocessor(["a", "b"], ["c"]).fit(train)
    out = pre.transform(train)
    assert out.shape[1] == len(pre.get_feature_names_out())
    assert list(pre.get_feature_names_out())[:2] == ["a", "b"]


def test_missing_indicator_only_for_features_with_missing_in_train(train):
    df = train[["a", "b"]].copy()
    df["d"] = [1.0, 2.0, 3.0, 4.0, 5.0]                                   # complete in train
    pre = build_preprocessor(["a", "b", "d"], cfg={"numeric": {"missing_indicator": True}}).fit(df)
    names = list(pre.get_feature_names_out())
    assert any("missingindicator_a" in n for n in names) and any("missingindicator_b" in n for n in names)
    assert not any("missingindicator_d" in n for n in names)
    assert pre.transform(df).shape[1] == len(names)


def test_all_nan_training_column_keeps_feature(train):
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "z": [np.nan] * 3})
    pre = build_preprocessor(["a", "z"], cfg={"numeric": {"scaler": "none"}}).fit(df)
    assert pre.transform(df).shape[1] == 2


@pytest.mark.parametrize("scaler", ["standard", "robust", "minmax", "none"])
def test_all_scalers_run(train, scaler):
    pre = build_preprocessor(["a", "b"], cfg={"numeric": {"scaler": scaler}}).fit(train[["a", "b"]])
    assert np.isfinite(pre.transform(train[["a", "b"]])).all()


def test_config_validation():
    with pytest.raises(ValueError, match="scaler"):
        validate_preprocessing_config({"numeric": {"scaler": "magic"}})
    with pytest.raises(ValueError, match="inf_strategy"):
        validate_preprocessing_config({"numeric": {"inf_strategy": "zero"}})
    with pytest.raises(ValueError, match="imputer"):
        validate_preprocessing_config({"numeric": {"imputer": "knn"}})
    eff = validate_preprocessing_config({})
    assert eff["numeric"]["scaler"] == "standard" and eff["numeric"]["inf_strategy"] == "nan"
    with pytest.raises(ValueError, match="No feature columns"):
        build_preprocessor([], [])


def test_split_columns(train):
    train = train.assign(flag=[True, False, True, True, False], label=list("abcde"))
    num, cat = split_columns(train, exclude=["label"])
    assert num == ["a", "b"] and cat == ["c", "flag"]


# ----------------------------------------------------------- pipeline / CV use
def test_works_in_sklearn_pipeline_and_cv_without_leakage_errors():
    rng = np.random.default_rng(3)
    X = pd.DataFrame(rng.normal(size=(120, 3)), columns=list("abc"))
    X.iloc[::17, 0] = np.inf
    X.iloc[::13, 1] = np.nan
    y = (X["c"] > 0).astype(int)
    pipe = Pipeline([("prep", build_preprocessor(list("abc"))), ("clf", LogisticRegression(max_iter=500))])
    scores = cross_val_score(pipe, X, y, cv=3)
    assert len(scores) == 3 and np.isfinite(scores).all()
    clone(pipe)                                                        # clonable for tuning


def test_handling_reports_counts_and_train_fill_values(train, test):
    pre = build_preprocessor(["a", "b"]).fit(train[["a", "b"]])
    rep = handling_reports(pre, train[["a", "b"]], test[["a", "b"]])
    assert rep["train"]["positive_inf_cells"] == 1 and rep["train"]["nan_cells"] == 1
    assert rep["test"]["positive_inf_cells"] == 1 and rep["test"]["negative_inf_cells"] == 1
    assert rep["train"]["inf_by_column"] == {"b": 1}
    assert rep["train_fill_values_for_affected_columns"]["a"] == train["a"].median()
    assert rep["inf_strategy"] == "nan" and rep["imputer_strategy"] == "median"


def test_none_in_object_column_is_imputed_not_learned_as_category():
    """Regression: on pandas 2.x an object column keeps None; SimpleImputer(np.nan) ignores None,
    so it used to become the one-hot category 'c_None'. Forced object dtype makes this
    version-independent."""
    tr = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "c": pd.Series(["x", "y", "x", None], dtype=object)})
    te = pd.DataFrame({"a": [1.0, 2.0], "c": pd.Series([None, "z"], dtype=object)})
    pre = build_preprocessor(["a"], ["c"]).fit(tr)
    names = list(pre.get_feature_names_out())
    assert sorted(n for n in names if n.startswith("c_")) == ["c_x", "c_y"]
    out = pre.transform(te)
    assert out[0, [names.index("c_x"), names.index("c_y")]].tolist() == [1.0, 0.0]   # None -> train mode 'x'
    assert out[1, [names.index("c_x"), names.index("c_y")]].tolist() == [0.0, 0.0]   # unseen 'z' -> zeros
