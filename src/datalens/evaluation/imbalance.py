"""Class imbalance analysis and TRAIN-ONLY resampling.

ISOLATION BY DESIGN: every resampling function takes only training data (X_train, y_train).
There is no parameter through which validation or test rows could be passed, so they can
never be resampled. Under cross-validation use `resampled_folds`, which resamples the training
part of each fold and returns the validation part untouched.

Honest limits
- Random oversampling duplicates existing rows: it adds weight, not information. For a class
  with a handful of examples (e.g. 11 Heartbleed rows) the model sees the same rows again and
  again; held-out scores for such a class are not reliable whatever the training recipe.
- SMOTE interpolates between a sample and its k nearest same-class neighbours, so it needs
  more than k samples in the class (inside the TRAINING fold). It is NOT implemented here
  (it needs the `imbalanced-learn` dependency); `smote_feasibility` reports which classes could
  not be synthesized at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_class_weight

RESAMPLING_STRATEGIES = ("none", "random_over", "random_under", "random_over_under")
CLASS_WEIGHT_MODES = ("balanced", "balanced_sqrt")


# ----------------------------------------------------------------------------- analysis
def smote_feasibility(class_counts: dict[str, int], k_neighbors: int = 5) -> dict[str, Any]:
    """SMOTE needs at least k_neighbors + 1 samples of a class in the training data."""
    need = k_neighbors + 1
    return {
        "k_neighbors": k_neighbors, "min_samples_required": need,
        "feasible_classes": sorted(c for c, n in class_counts.items() if n >= need),
        "infeasible_classes": sorted(c for c, n in class_counts.items() if n < need),
    }


def imbalance_report(
    y: pd.Series | np.ndarray, test_size: float = 0.2, cv_folds: int = 5, minority_pct: float = 1.0,
    min_test_per_class: int = 5, low_support_test: int = 30, smote_k: int = 5,
) -> dict[str, Any]:
    """Frequencies, percentages, ratios and per-procedure feasibility for every class.

    Expected counts assume a stratified split at `test_size`; they are estimates of what each
    partition would hold, not the realised split (see the split metadata for that).
    """
    s = pd.Series(np.asarray(y)).astype(str)
    if s.empty:
        raise ValueError("Empty label vector")
    counts = s.value_counts()
    n, majority = len(s), int(counts.iloc[0])
    per_class: dict[str, dict[str, Any]] = {}
    for cls, c in counts.items():
        exp_test, exp_train = c * test_size, c * (1 - test_size)
        per_class[cls] = {
            "count": int(c), "percent": round(100 * c / n, 4), "ratio_to_majority": round(majority / c, 2),
            "is_minority": bool(100 * c / n < minority_pct),
            "stratified_split_possible": bool(c >= 2),
            "stratified_kfold_possible": bool(c >= cv_folds),
            "expected_test_count": round(exp_test, 2),
            "test_metrics_unreliable": bool(exp_test < min_test_per_class),
            "test_metrics_low_support": bool(exp_test < low_support_test),
            "smote_possible_in_train": bool(exp_train > smote_k),
        }
    pc = per_class
    return {
        "n_rows": n, "n_classes": int(len(counts)),
        "majority_class": str(counts.index[0]), "majority_percent": round(100 * majority / n, 4),
        "overall_imbalance_ratio": round(majority / int(counts.iloc[-1]), 2),
        "minority_classes": [c for c in pc if pc[c]["is_minority"]],
        "classes_unstratifiable": [c for c in pc if not pc[c]["stratified_split_possible"]],
        "classes_unusable_for_kfold": [c for c in pc if not pc[c]["stratified_kfold_possible"]],
        "classes_with_unreliable_test_metrics": [c for c in pc if pc[c]["test_metrics_unreliable"]],
        "classes_with_low_test_support": [c for c in pc if pc[c]["test_metrics_low_support"]],
        "smote": smote_feasibility({c: int(round(pc[c]["count"] * (1 - test_size))) for c in pc}, smote_k),
        "assumptions": {"test_size": test_size, "cv_folds": cv_folds, "minority_pct": minority_pct,
                        "min_test_per_class": min_test_per_class, "low_support_test": low_support_test},
        "per_class": pc,
        "notes": ["Do not expect reliable per-class performance for classes with only a handful of examples; "
                  "report them separately with their support instead of averaging them away.",
                  "Accuracy is dominated by the majority class; use macro-F1, per-class recall and PR-AUC."],
    }


# ----------------------------------------------------------------------------- class weights
def class_weights(y_train: pd.Series | np.ndarray, mode: str = "balanced") -> dict[str, float]:
    """Per-class weights from TRAINING labels. 'balanced_sqrt' softens extreme weights."""
    if mode not in CLASS_WEIGHT_MODES:
        raise ValueError(f"mode must be one of {CLASS_WEIGHT_MODES}")
    y = np.asarray(pd.Series(np.asarray(y_train)).astype(str))
    classes = np.unique(y)
    w = compute_class_weight("balanced", classes=classes, y=y)
    if mode == "balanced_sqrt":
        w = np.sqrt(w)
    return {str(c): float(x) for c, x in zip(classes, w)}


# ----------------------------------------------------------------------------- resampling
@dataclass
class ResampleResult:
    X: Any
    y: Any
    positions: np.ndarray        # positions (in the INPUT training data) of every output row
    report: dict[str, Any]


def resample_training_data(
    X_train, y_train, strategy: str = "random_over", floor: int | None = None, cap: int | None = None,
    seed: int = 42, max_oversample_factor: float = 50.0,
) -> ResampleResult:
    """Randomly resample TRAINING data.

    random_over:        classes with fewer than `floor` rows are oversampled (with replacement) to `floor`.
    random_under:       classes with more than `cap` rows are undersampled (without replacement) to `cap`.
    random_over_under:  both.
    'none' returns the data unchanged. Classes already within bounds are never touched; no class
    is ever removed entirely.
    """
    if strategy not in RESAMPLING_STRATEGIES:
        raise ValueError(f"strategy must be one of {RESAMPLING_STRATEGIES}")
    n = len(y_train)
    if n == 0:
        raise ValueError("Empty training data")
    if len(X_train) != n:
        raise ValueError("X_train and y_train must have the same length")
    use_over, use_under = strategy in ("random_over", "random_over_under"), strategy in ("random_under", "random_over_under")
    if use_over and (floor is None or floor <= 0):
        raise ValueError("'floor' (target minimum rows per class) is required and must be positive for oversampling")
    if use_under and (cap is None or cap <= 0):
        raise ValueError("'cap' (maximum rows per class) is required and must be positive for undersampling")
    if use_over and use_under and floor > cap:
        raise ValueError("floor must not exceed cap")

    labels = np.asarray(pd.Series(np.asarray(y_train)).astype(str))
    rng = np.random.default_rng(seed)
    chosen: list[np.ndarray] = []
    before, after, warnings = {}, {}, []
    for cls in np.unique(labels):
        pos = np.flatnonzero(labels == cls)
        before[str(cls)] = int(pos.size)
        if use_over and pos.size < floor:
            extra = rng.choice(pos, size=floor - pos.size, replace=True)
            pos = np.concatenate([pos, extra])
            factor = floor / before[str(cls)]
            if factor > max_oversample_factor or before[str(cls)] < 5:
                warnings.append(f"Class '{cls}' oversampled x{factor:.0f} from {before[str(cls)]} real rows: "
                                "duplicates add weight, not information; its held-out metrics stay unreliable")
        elif use_under and pos.size > cap:
            pos = rng.choice(pos, size=cap, replace=False)
        after[str(cls)] = int(pos.size)
        chosen.append(pos)
    positions = np.arange(n) if strategy == "none" else np.concatenate(chosen)
    Xr = X_train.iloc[positions].reset_index(drop=True) if isinstance(X_train, pd.DataFrame) else np.asarray(X_train)[positions]
    yr = (pd.Series(np.asarray(y_train)).iloc[positions].reset_index(drop=True) if isinstance(y_train, pd.Series)
          else np.asarray(y_train)[positions])
    report = {"strategy": strategy, "floor": floor, "cap": cap, "seed": seed, "rows_before": n, "rows_after": int(len(positions)),
              "counts_before": before, "counts_after": after, "warnings": warnings,
              "note": "Resampled TRAINING data only; validation/test data are never passed to this function."}
    return ResampleResult(Xr, yr, positions, report)


def resampled_folds(
    X, y, n_splits: int = 5, strategy: str = "random_over", floor: int | None = None, cap: int | None = None,
    seed: int = 42,
) -> Iterator[tuple[Any, Any, Any, Any, dict[str, Any]]]:
    """Stratified CV where resampling touches ONLY each fold's training part.

    Yields (X_train_resampled, y_train_resampled, X_val, y_val, report); X_val/y_val are exact
    slices of the input, never resampled. Classes with fewer than n_splits rows cannot be
    stratified: they raise (handle them explicitly before calling, do not drop them silently).
    """
    labels = np.asarray(pd.Series(np.asarray(y)).astype(str))
    counts = pd.Series(labels).value_counts()
    too_small = sorted(counts[counts < n_splits].index)
    if too_small:
        raise ValueError(f"Classes with fewer than n_splits={n_splits} rows cannot be stratified: {too_small}")
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for fold, (tr, va) in enumerate(skf.split(np.zeros(len(labels)), labels)):
        Xtr = X.iloc[tr] if isinstance(X, pd.DataFrame) else np.asarray(X)[tr]
        ytr = np.asarray(y)[tr] if not isinstance(y, pd.Series) else y.iloc[tr]
        Xva = X.iloc[va] if isinstance(X, pd.DataFrame) else np.asarray(X)[va]
        yva = np.asarray(y)[va] if not isinstance(y, pd.Series) else y.iloc[va]
        res = resample_training_data(Xtr, ytr, strategy, floor, cap, seed + fold)
        rep = dict(res.report, fold=fold, n_validation=int(len(va)))
        yield res.X, res.y, Xva, yva, rep
