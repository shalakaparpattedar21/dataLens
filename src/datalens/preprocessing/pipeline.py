"""Leakage-safe preprocessing built from scikit-learn components.

LEAKAGE RULE: every learned quantity (clip bounds, imputation values, scaler mean/std,
encoder categories) is computed in fit() on TRAINING data only. transform() applies those
stored values to any data and never changes them. Because everything is an sklearn
estimator, putting it inside a Pipeline makes cross-validation refit it on each training
fold automatically.

Numeric branch:  InfiniteValueHandler -> SimpleImputer -> scaler
Categorical:     SimpleImputer(most_frequent) -> OneHotEncoder(handle_unknown='ignore')

Infinities: 'nan' (default) turns +/-inf into NaN so the imputer treats them as "undefined
value" -- never silently zero. 'clip' replaces +inf/-inf by the training set's largest/smallest
FINITE value. Neither is "correct" for every feature; the data-specific evidence is produced by
scripts/investigate_dataset.py. Optionally `missing_indicator` keeps the information that a
value was undefined as an extra 0/1 column.

Scaling: needed by distance/gradient-based models (logistic regression, SVM, kNN); NOT needed
by tree models (decision tree, random forest, gradient boosting), which are invariant to
monotonic feature transforms. 'robust' (median/IQR) suits heavy-tailed traffic features.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, MinMaxScaler, OneHotEncoder, OrdinalEncoder, RobustScaler, StandardScaler

INF_STRATEGIES = ("nan", "clip")
NUMERIC_IMPUTERS = ("median", "mean", "most_frequent")
SCALERS = ("standard", "robust", "minmax", "none")
CATEGORICAL_IMPUTERS = ("most_frequent",)

DEFAULT_PREPROCESSING_CONFIG: dict[str, Any] = {
    "numeric": {"inf_strategy": "nan", "imputer": "median", "missing_indicator": False, "scaler": "standard"},
    "categorical": {"imputer": "most_frequent", "handle_unknown": "ignore", "min_frequency": None, "encoding": "onehot"},
}


class InfiniteValueHandler(BaseEstimator, TransformerMixin):
    """Replace +/-inf. Learns finite per-column bounds in fit() (used by strategy='clip')."""

    def __init__(self, strategy: str = "nan"):
        self.strategy = strategy

    def _to_array(self, X) -> np.ndarray:
        return np.asarray(X, dtype=float)

    def fit(self, X, y=None):
        if self.strategy not in INF_STRATEGIES:
            raise ValueError(f"strategy must be one of {INF_STRATEGIES}, got '{self.strategy}'")
        A = self._to_array(X)
        if A.ndim != 2:
            raise ValueError("Expected a 2D array")
        self.n_features_in_ = A.shape[1]
        self.feature_names_in_ = np.asarray(X.columns, dtype=object) if isinstance(X, pd.DataFrame) else None
        mins, maxs = np.full(A.shape[1], np.nan), np.full(A.shape[1], np.nan)
        for j in range(A.shape[1]):                      # column loop keeps peak memory low
            col = A[:, j]
            finite = col[np.isfinite(col)]
            if finite.size:
                mins[j], maxs[j] = finite.min(), finite.max()
        self.finite_min_, self.finite_max_ = mins, maxs
        return self

    def transform(self, X):
        A = np.array(self._to_array(X), copy=True)       # never mutate the caller's data
        if A.shape[1] != self.n_features_in_:
            raise ValueError(f"Expected {self.n_features_in_} features, got {A.shape[1]}")
        pos, neg = np.isposinf(A), np.isneginf(A)
        names = (list(self.feature_names_in_) if self.feature_names_in_ is not None
                 else [f"x{j}" for j in range(A.shape[1])])
        self.last_transform_report_ = {
            "strategy": self.strategy,
            "n_positive_inf": int(pos.sum()),
            "n_negative_inf": int(neg.sum()),
            "by_column": {names[j]: int(pos[:, j].sum() + neg[:, j].sum())
                          for j in np.flatnonzero(pos.any(axis=0) | neg.any(axis=0))},
        }
        if self.strategy == "nan":
            A[pos | neg] = np.nan
        else:  # clip to TRAINING finite bounds
            rows, cols = np.nonzero(pos)
            A[rows, cols] = self.finite_max_[cols]
            rows, cols = np.nonzero(neg)
            A[rows, cols] = self.finite_min_[cols]
        return A

    def get_feature_names_out(self, input_features=None):
        if input_features is not None:
            return np.asarray(input_features, dtype=object)
        if self.feature_names_in_ is not None:
            return np.asarray(self.feature_names_in_, dtype=object)
        return np.asarray([f"x{j}" for j in range(self.n_features_in_)], dtype=object)


def _missing_to_nan(X):
    """Turn every missing marker (None, pd.NA, NaN) in a categorical block into np.nan.

    Why: on pandas 2.x an object column keeps None as None, and scikit-learn's SimpleImputer
    (missing_values=np.nan) does not treat None as missing, so None would be learned as a
    category of its own. Stateless: nothing is learned, so there is no leakage.
    """
    df = pd.DataFrame(X).astype(object)
    return df.where(df.notna(), np.nan)


def validate_preprocessing_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Merge with defaults and validate. Returns the effective config (recorded in metadata)."""
    eff = {k: {**DEFAULT_PREPROCESSING_CONFIG[k], **(cfg.get(k) or {})} for k in DEFAULT_PREPROCESSING_CONFIG}
    n, c = eff["numeric"], eff["categorical"]
    if n["inf_strategy"] not in INF_STRATEGIES:
        raise ValueError(f"numeric.inf_strategy must be one of {INF_STRATEGIES}")
    if n["imputer"] not in NUMERIC_IMPUTERS:
        raise ValueError(f"numeric.imputer must be one of {NUMERIC_IMPUTERS}")
    if n["scaler"] not in SCALERS:
        raise ValueError(f"numeric.scaler must be one of {SCALERS}")
    if c["imputer"] not in CATEGORICAL_IMPUTERS:
        raise ValueError(f"categorical.imputer must be one of {CATEGORICAL_IMPUTERS}")
    if c["handle_unknown"] not in ("ignore", "error"):
        raise ValueError("categorical.handle_unknown must be 'ignore' or 'error'")
    if c["encoding"] not in ("onehot", "ordinal"):
        raise ValueError("categorical.encoding must be 'onehot' or 'ordinal'")
    return eff


def _make_scaler(name: str):
    return {"standard": StandardScaler(), "robust": RobustScaler(), "minmax": MinMaxScaler(), "none": "passthrough"}[name]


def build_preprocessor(
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str] = (),
    cfg: dict[str, Any] | None = None,
) -> ColumnTransformer:
    """Build an UNFITTED ColumnTransformer. Fit it on training data only."""
    eff = validate_preprocessing_config(cfg or {})
    n, c = eff["numeric"], eff["categorical"]
    transformers = []
    if numeric_columns:
        transformers.append(("num", Pipeline([
            ("inf", InfiniteValueHandler(strategy=n["inf_strategy"])),
            ("impute", SimpleImputer(strategy=n["imputer"], add_indicator=n["missing_indicator"],
                                     keep_empty_features=True)),
            ("scale", _make_scaler(n["scaler"])),
        ]), list(numeric_columns)))
    if categorical_columns:
        if c["encoding"] == "onehot":
            encoder = OneHotEncoder(handle_unknown=c["handle_unknown"], min_frequency=c["min_frequency"], sparse_output=False)
        elif c["handle_unknown"] == "ignore":
            encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        else:
            encoder = OrdinalEncoder(handle_unknown="error")
        transformers.append(("cat", Pipeline([
            ("nan", FunctionTransformer(_missing_to_nan, validate=False, feature_names_out="one-to-one")),
            ("impute", SimpleImputer(strategy=c["imputer"], keep_empty_features=True)),
            ("encode", encoder),
        ]), list(categorical_columns)))
    if not transformers:
        raise ValueError("No feature columns given")
    return ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=False)


def split_columns(df: pd.DataFrame, exclude: Sequence[str] = ()) -> tuple[list[str], list[str]]:
    """Return (numeric_columns, categorical_columns) for the non-excluded columns."""
    skip = set(exclude)
    num, cat = [], []
    for col in df.columns:
        if col in skip:
            continue
        s = df[col]
        (num if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) else cat).append(col)
    return num, cat


def handling_reports(preprocessor: ColumnTransformer, X_train: pd.DataFrame, X_test: pd.DataFrame | None = None) -> dict[str, Any]:
    """Missing- and infinite-value handling report for a FITTED preprocessor.

    Counts come straight from the raw frames; fill values are the TRAIN statistics the fitted
    imputer will apply to any data (including test).
    """
    out: dict[str, Any] = {}
    if "num" not in preprocessor.named_transformers_:
        return out
    num_pipe = preprocessor.named_transformers_["num"]
    cols = list(preprocessor.transformers_[[t[0] for t in preprocessor.transformers_].index("num")][2])
    imputer: SimpleImputer = num_pipe.named_steps["impute"]
    fills = dict(zip(cols, [None if pd.isna(v) else float(v) for v in imputer.statistics_]))

    def counts(df: pd.DataFrame) -> dict[str, Any]:
        A = df[cols].to_numpy(dtype=float)
        pos, neg, nan = np.isposinf(A), np.isneginf(A), np.isnan(A)
        return {
            "rows": int(len(df)),
            "positive_inf_cells": int(pos.sum()), "negative_inf_cells": int(neg.sum()), "nan_cells": int(nan.sum()),
            "inf_by_column": {cols[j]: int(pos[:, j].sum() + neg[:, j].sum()) for j in np.flatnonzero(pos.any(0) | neg.any(0))},
            "nan_by_column": {cols[j]: int(nan[:, j].sum()) for j in np.flatnonzero(nan.any(0))},
        }

    out["train"] = counts(X_train)
    if X_test is not None:
        out["test"] = counts(X_test)
    out["inf_strategy"] = num_pipe.named_steps["inf"].strategy
    out["imputer_strategy"] = imputer.strategy
    out["missing_indicator"] = bool(imputer.add_indicator)
    affected = set(out["train"]["inf_by_column"]) | set(out["train"]["nan_by_column"])
    out["train_fill_values_for_affected_columns"] = {c: fills[c] for c in sorted(affected)}
    return out
