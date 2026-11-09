"""Tests for imbalance analysis and train-only resampling. Synthetic, hand-checkable numbers."""

import numpy as np
import pandas as pd
import pytest

from datalens.evaluation.imbalance import (
    class_weights, imbalance_report, resample_training_data, resampled_folds, smote_feasibility,
)


@pytest.fixture
def y100():
    return np.array(["A"] * 80 + ["B"] * 15 + ["C"] * 4 + ["D"] * 1)


# ------------------------------------------------------------------ analysis
def test_imbalance_report_hand_checked(y100):
    r = imbalance_report(y100, test_size=0.2, cv_folds=5, minority_pct=5.0)
    assert r["n_rows"] == 100 and r["n_classes"] == 4
    assert r["majority_class"] == "A" and r["majority_percent"] == 80.0
    assert r["overall_imbalance_ratio"] == 80.0
    assert r["per_class"]["B"]["percent"] == 15.0 and r["per_class"]["B"]["ratio_to_majority"] == pytest.approx(5.33, abs=0.01)
    assert r["minority_classes"] == ["C", "D"]
    assert r["classes_unstratifiable"] == ["D"]
    assert r["classes_unusable_for_kfold"] == ["C", "D"]
    assert r["classes_with_unreliable_test_metrics"] == ["B", "C", "D"]      # expected test count < 5
    assert r["classes_with_low_test_support"] == ["A", "B", "C", "D"]        # all < 30
    assert r["smote"]["infeasible_classes"] == ["C", "D"]                    # train counts 3 and 1 < 6
    assert any("handful" in note for note in r["notes"])


def test_imbalance_report_single_class_and_empty():
    r = imbalance_report(np.array(["A"] * 10))
    assert r["overall_imbalance_ratio"] == 1.0 and r["minority_classes"] == []
    with pytest.raises(ValueError):
        imbalance_report(np.array([]))


def test_smote_feasibility_boundary():
    s = smote_feasibility({"x": 5, "y": 6}, k_neighbors=5)
    assert s["infeasible_classes"] == ["x"] and s["feasible_classes"] == ["y"]


def test_class_weights_formula_and_modes():
    y = np.array(["A"] * 80 + ["B"] * 20)
    w = class_weights(y)
    assert w["A"] == pytest.approx(100 / (2 * 80)) and w["B"] == pytest.approx(100 / (2 * 20))
    ws = class_weights(y, "balanced_sqrt")
    assert ws["B"] == pytest.approx(np.sqrt(w["B"]))
    with pytest.raises(ValueError):
        class_weights(y, "magic")


# ------------------------------------------------------------------ resampling
@pytest.fixture
def frame(y100):
    return pd.DataFrame({"rowid": np.arange(100), "f": np.random.default_rng(0).normal(size=100)}), y100


def test_random_over_raises_floor_without_losing_or_touching_big_classes(frame):
    X, y = frame
    res = resample_training_data(X, y, "random_over", floor=30, seed=1)
    after = res.report["counts_after"]
    assert after == {"A": 80, "B": 30, "C": 30, "D": 30}
    assert len(res.X) == len(res.y) == 170 == res.report["rows_after"]
    assert set(res.positions) <= set(range(100))                              # only input rows are reused
    np.testing.assert_array_equal(res.y.to_numpy() if hasattr(res.y, "to_numpy") else res.y, y[res.positions])
    np.testing.assert_array_equal(res.X["rowid"].to_numpy(), X["rowid"].to_numpy()[res.positions])
    assert len(X) == 100                                                      # input not mutated


def test_random_under_caps_majority_without_replacement(frame):
    X, y = frame
    res = resample_training_data(X, y, "random_under", cap=20, seed=2)
    assert res.report["counts_after"] == {"A": 20, "B": 15, "C": 4, "D": 1}
    a_pos = res.positions[y[res.positions] == "A"]
    assert len(set(a_pos)) == len(a_pos)                                      # no duplicates when undersampling


def test_over_under_and_validation(frame):
    X, y = frame
    res = resample_training_data(X, y, "random_over_under", floor=10, cap=40, seed=3)
    assert res.report["counts_after"] == {"A": 40, "B": 15, "C": 10, "D": 10}
    with pytest.raises(ValueError, match="floor must not exceed cap"):
        resample_training_data(X, y, "random_over_under", floor=50, cap=40)
    with pytest.raises(ValueError, match="floor"):
        resample_training_data(X, y, "random_over")
    with pytest.raises(ValueError, match="cap"):
        resample_training_data(X, y, "random_under")
    with pytest.raises(ValueError, match="strategy"):
        resample_training_data(X, y, "smote")                                  # SMOTE intentionally not implemented
    with pytest.raises(ValueError, match="same length"):
        resample_training_data(X.iloc[:-1], y)


def test_none_strategy_is_identity(frame):
    X, y = frame
    res = resample_training_data(X, y, "none")
    assert res.report["counts_after"] == res.report["counts_before"]
    np.testing.assert_array_equal(res.positions, np.arange(100))


def test_resampling_is_reproducible_and_seed_sensitive(frame):
    X, y = frame
    a = resample_training_data(X, y, "random_over", floor=30, seed=7).positions
    b = resample_training_data(X, y, "random_over", floor=30, seed=7).positions
    c = resample_training_data(X, y, "random_over", floor=30, seed=8).positions
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


def test_heavy_oversampling_of_tiny_class_warns(frame):
    X, y = frame
    res = resample_training_data(X, y, "random_over", floor=300)
    assert any("'D'" in w and "x300" in w for w in res.report["warnings"])
    assert any("'C'" in w for w in res.report["warnings"])                     # 4 real rows (< 5)
    assert not any("'A'" in w for w in res.report["warnings"])


def test_numpy_inputs_supported(y100):
    X = np.random.default_rng(0).normal(size=(100, 3))
    res = resample_training_data(X, y100, "random_over", floor=20)
    assert isinstance(res.X, np.ndarray) and res.X.shape == (res.report["rows_after"], 3)


# ------------------------------------------------------------------ isolation under CV
def test_resampled_folds_never_touch_validation_data():
    rng = np.random.default_rng(0)
    y = np.array(["A"] * 90 + ["B"] * 12 + ["C"] * 8)
    X = pd.DataFrame({"rowid": np.arange(len(y)), "f": rng.normal(size=len(y))})
    seen_val: list[int] = []
    for Xtr, ytr, Xva, yva, rep in resampled_folds(X, y, n_splits=4, strategy="random_over", floor=40, seed=5):
        val_ids, train_ids = set(Xva["rowid"]), set(Xtr["rowid"])
        assert val_ids.isdisjoint(train_ids)                                   # nothing from validation reaches training
        assert len(Xva) == len(yva) == rep["n_validation"]
        assert pd.Series(yva).value_counts().to_dict() == pd.Series(y[Xva["rowid"].to_numpy()]).value_counts().to_dict()
        assert pd.Series(ytr).value_counts().min() >= 40                       # training was resampled...
        assert len(val_ids) == len(Xva)                                        # ...validation rows are unique, not duplicated
        seen_val += list(val_ids)
    assert sorted(seen_val) == list(range(len(y)))                             # each row validated exactly once


def test_resampled_folds_rejects_unstratifiable_classes():
    y = np.array(["A"] * 50 + ["B"] * 3)
    X = pd.DataFrame({"f": np.arange(53.0)})
    with pytest.raises(ValueError, match="cannot be stratified"):
        list(resampled_folds(X, y, n_splits=5, strategy="none"))
