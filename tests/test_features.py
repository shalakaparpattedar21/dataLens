"""Tests for feature analysis, selection and metadata. Synthetic data with planted structure."""

import numpy as np
import pandas as pd
import pytest
from sklearn.feature_selection import f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate

from datalens.features import (
    ExclusionLog, build_feature_metadata, build_selector, correlation_analysis, low_variance_report,
    make_selection_pipeline, map_to_original, selected_feature_names, single_feature_probe,
    suggest_correlated_drops, train_only_importance,
)
from datalens.preprocessing.pipeline import build_preprocessor


@pytest.fixture
def data():
    rng = np.random.default_rng(0)
    n = 600
    y = rng.choice(["BENIGN", "DoS"], n, p=[0.6, 0.4])
    signal = (y == "DoS").astype(float) * 3 + rng.normal(0, 0.3, n)
    X = pd.DataFrame({"signal": signal, "noise1": rng.normal(size=n), "noise2": rng.normal(size=n),
                      "const": 7.0, "port": rng.integers(0, 65535, n).astype(float)})
    return X, y


# ------------------------------------------------------------------ low variance
def test_low_variance_report_actions():
    X = pd.DataFrame({
        "const": [5.0] * 100,
        "near": [0.0] * 99 + [1.0],
        "ok": np.arange(100, dtype=float),
        "inf_const": [np.inf] * 50 + [3.0] * 50,        # finite part is constant
        "allbad": [np.nan] * 100,
    })
    r = low_variance_report(X)
    assert r.loc["const", "suggested_action"].startswith("drop")
    assert r.loc["near", "suggested_action"].startswith("review")
    assert r.loc["ok", "suggested_action"] == "keep"
    assert r.loc["inf_const", "suggested_action"].startswith("drop")   # inf ignored in statistics
    assert r.loc["allbad", "suggested_action"].startswith("review") and bool(r.loc["allbad", "all_non_finite"])


# ------------------------------------------------------------------ correlation
def test_correlation_pairs_and_drops():
    rng = np.random.default_rng(1)
    a = rng.normal(size=500)
    X = pd.DataFrame({"a": a, "b": 2 * a + rng.normal(0, 1e-3, 500), "d": -a, "c": rng.normal(size=500), "k": 1.0})
    r = correlation_analysis(X, threshold=0.95)
    pair_sets = {frozenset((p["feature_a"], p["feature_b"])) for p in r["pairs"]}
    assert pair_sets == {frozenset("ab"), frozenset("ad"), frozenset("bd")}
    dropped = {d["dropped"] for d in r["suggested_drops"]}
    assert len(dropped) == 2 and dropped < {"a", "b", "d"}      # one of the trio survives
    assert "c" not in dropped and "k" not in dropped            # independent / constant never paired


def test_correlation_threshold_validation_and_sampling():
    X = pd.DataFrame(np.random.default_rng(2).normal(size=(300, 3)), columns=list("abc"))
    for bad in (0, 1.5, -0.1):
        with pytest.raises(ValueError):
            correlation_analysis(X, threshold=bad)
    r = correlation_analysis(X, threshold=0.99, max_rows=100, seed=5)
    assert r["rows_used"] == 100 and r["pairs"] == []


def test_suggest_correlated_drops_is_deterministic():
    X = pd.DataFrame({"a": np.arange(50.0), "b": np.arange(50.0) * 3, "c": np.arange(50.0) ** 2})
    corr = X.corr()
    assert suggest_correlated_drops(corr, 0.9) == suggest_correlated_drops(corr, 0.9)


def test_correlation_ignores_inf():
    X = pd.DataFrame({"a": [1.0, 2.0, np.inf, 4.0, 5.0], "b": [2.0, 4.0, 6.0, 8.0, 10.0]})
    r = correlation_analysis(X, threshold=0.9)       # must not crash or produce nan pairs
    assert r["n_features"] == 2


# ------------------------------------------------------------------ probe + importance
def test_single_feature_probe_flags_signal_not_noise(data):
    X, y = data
    r = single_feature_probe(X, y, flag_auc=0.95)
    assert r.attrs["binary"] is True
    assert r.index[0] == "signal" and bool(r.loc["signal", "flag_review"])
    assert r.loc["signal", "roc_auc"] > 0.95
    assert not bool(r.loc["noise1", "flag_review"]) and r.loc["noise1", "roc_auc"] < 0.65


def test_probe_multiclass_and_rare_class_handling():
    rng = np.random.default_rng(3)
    y = np.array(["A"] * 100 + ["B"] * 100 + ["C"] * 2)          # C has < cv samples -> excluded from probe
    X = pd.DataFrame({"f": np.r_[rng.normal(0, 1, 100), rng.normal(5, 1, 100), [9.0, 9.0]]})
    r = single_feature_probe(X, y, cv=3)
    assert r.attrs["classes"] == ["A", "B"] and r.attrs["rows_used"] == 200


def test_probe_validation_errors(data):
    X, y = data
    with pytest.raises(ValueError, match="same length"):
        single_feature_probe(X, y[:-1])
    with pytest.raises(ValueError, match="two classes"):
        single_feature_probe(X, np.array(["A"] * len(X)))


def test_train_only_importance_ranks_signal_first(data):
    X, y = data
    imp = train_only_importance(X, y, n_estimators=30, max_depth=5)
    assert imp.index[0] == "signal"
    pd.testing.assert_series_equal(imp, train_only_importance(X, y, n_estimators=30, max_depth=5))
    with pytest.raises(ValueError):
        train_only_importance(X, y[:-1])


# ------------------------------------------------------------------ selectors
def test_build_selector_validation():
    assert build_selector("none") == "passthrough"
    with pytest.raises(ValueError):
        build_selector("magic")
    with pytest.raises(ValueError):
        build_selector("kbest_f", k=0)


@pytest.mark.parametrize("method", ["kbest_f", "kbest_mi", "model_rf"])
def test_selectors_keep_the_signal_feature(data, method):
    X, y = data
    pre = build_preprocessor(list(X.columns), cfg={"numeric": {"scaler": "none"}})
    pipe = make_selection_pipeline(pre, build_selector(method, k=2, n_estimators=30), LogisticRegression(max_iter=200))
    pipe.fit(X, y)
    assert "signal" in selected_feature_names(pipe)
    assert len(selected_feature_names(pipe)) == 2


def test_variance_selector_drops_only_constants(data):
    X, y = data
    pre = build_preprocessor(list(X.columns), cfg={"numeric": {"scaler": "standard"}})
    pipe = make_selection_pipeline(pre, build_selector("variance", variance_threshold=0.0), LogisticRegression(max_iter=200))
    pipe.fit(X, y)
    kept = selected_feature_names(pipe)
    assert "const" not in kept and set(kept) == {"signal", "noise1", "noise2", "port"}


def test_selection_is_fitted_on_training_data_only(data):
    X, y = data
    X_tr, y_tr, X_te, y_te = X.iloc[:400], y[:400], X.iloc[400:], y[400:]
    pre = build_preprocessor(list(X.columns), cfg={"numeric": {"scaler": "none"}})
    pipe = make_selection_pipeline(pre, build_selector("kbest_f", k=2), LogisticRegression(max_iter=200))
    pipe.fit(X_tr, y_tr)
    scores = pipe.named_steps["select"].scores_
    train_matrix = pipe.named_steps["prep"].transform(X_tr)
    np.testing.assert_allclose(scores, f_classif(train_matrix, y_tr)[0])            # exactly train-only scores
    with_test = f_classif(pipe.named_steps["prep"].transform(X), y)[0]
    assert not np.allclose(scores, with_test)                                      # test rows had no influence


def test_cross_validation_refits_selector_per_fold(data):
    X, y = data
    pre = build_preprocessor(list(X.columns), cfg={"numeric": {"scaler": "none"}})
    pipe = make_selection_pipeline(pre, build_selector("kbest_f", k=2), LogisticRegression(max_iter=200))
    res = cross_validate(pipe, X, y, cv=StratifiedKFold(3, shuffle=True, random_state=0), return_estimator=True)
    per_fold_scores = [e.named_steps["select"].scores_ for e in res["estimator"]]
    assert not np.allclose(per_fold_scores[0], per_fold_scores[1])                  # each fold fitted its own


# ------------------------------------------------------------------ exclusion log + metadata
def test_exclusion_log_requires_reason_and_evidence_and_is_loud():
    log = ExclusionLog()
    with pytest.raises(ValueError):
        log.add("x", "", {"e": 1})
    with pytest.raises(ValueError):
        log.add("x", "constant", None)
    log.add("const", "zero variance", {"n_unique": 1})
    with pytest.raises(ValueError, match="already excluded"):
        log.add("const", "again", {"e": 1})
    assert log.apply(["a", "const", "b"]) == ["a", "b"]
    with pytest.raises(KeyError):
        log.apply(["a", "b"])                       # excluded feature not present: never silent


def test_map_to_original():
    originals = ["Flow Duration", "proto", "proto_type"]
    assert map_to_original("Flow Duration", originals) == "Flow Duration"
    assert map_to_original("missingindicator_Flow Duration", originals) == "Flow Duration"
    assert map_to_original("proto_type_tcp", originals) == "proto_type"        # longest match wins
    assert map_to_original("mystery", originals) is None


def test_build_feature_metadata_full_record():
    df = pd.DataFrame({"a": [1.0, np.nan, 3.0, 4.0], "b": [1.0, 2.0, 2.0, 2.0], "const": 1.0, "proto": list("xyxy")})
    log = ExclusionLog()
    log.add("const", "zero variance on training data", {"n_unique": 1})
    modeling = log.apply(list(df.columns))
    pre = build_preprocessor(["a", "b"], ["proto"], cfg={"numeric": {"missing_indicator": True}})
    pre.fit(df[modeling])
    meta = build_feature_metadata(list(df.columns), log, pre, selected=["a", "proto_x"], transformations={"scaler": "standard"})
    assert meta["excluded_features"]["const"]["reason"] == "zero variance on training data"
    assert meta["modeling_features"] == ["a", "b", "proto"]
    assert meta["transformed_to_original"]["missingindicator_a"] == "a"
    assert meta["transformed_to_original"]["proto_x"] == "proto"
    assert meta["selected_features"] == ["a", "proto_x"]
    assert "b" in meta["removed_by_selection"] and "a" not in meta["removed_by_selection"]
    with pytest.raises(KeyError):
        bad = ExclusionLog(); bad.add("ghost", "r", {"e": 1})
        build_feature_metadata(["a"], bad)
