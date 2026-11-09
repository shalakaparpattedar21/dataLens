"""Resource-aware fitting and transforming of a preprocessor.

Why this exists: sklearn pipelines hold several dense copies of the training matrix at once
(column selection, float conversion, inf handling, imputation, scaling). On 2.8M rows x 78
features one copy is ~1.6 GB, so fitting on all training rows can exceed modest RAM.

Design (leakage-safe and explicit):
- fit_preprocessor() may fit on a seeded random subsample of the TRAINING rows only. Median/IQR/
  mean/std estimated from hundreds of thousands of rows are statistically very close to the
  full-train values. The number of rows used is returned and must be recorded with the run.
  Test rows are never touched.
- transform_in_chunks() applies the already-fitted preprocessor chunk by chunk, so the full
  transformed matrix never has to exist in memory at once.
"""

from __future__ import annotations

from typing import Any, Iterator

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator


def fit_preprocessor(
    preprocessor: BaseEstimator,
    X_train: pd.DataFrame,
    max_fit_rows: int | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Fit on (a subsample of) TRAINING data only. Returns a record to store with the run."""
    n = len(X_train)
    if n == 0:
        raise ValueError("Cannot fit a preprocessor on an empty training set")
    if max_fit_rows is not None and max_fit_rows <= 0:
        raise ValueError("max_fit_rows must be positive or None")
    if max_fit_rows is not None and n > max_fit_rows:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(n, size=max_fit_rows, replace=False))
        preprocessor.fit(X_train.iloc[idx])
        used, subsample = int(max_fit_rows), True
    else:
        preprocessor.fit(X_train)
        used, subsample = int(n), False
    return {
        "train_rows": int(n), "fit_rows_used": used, "fit_on_subsample": subsample,
        "fit_subsample_fraction": round(used / n, 6), "seed": seed,
        "note": "Fitted on TRAINING rows only; test rows were never used.",
    }


def transform_in_chunks(preprocessor: BaseEstimator, X: pd.DataFrame, chunk_size: int = 200_000) -> Iterator[np.ndarray]:
    """Yield transformed row-blocks in order. Does not modify the fitted preprocessor."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    for start in range(0, len(X), chunk_size):
        yield np.asarray(preprocessor.transform(X.iloc[start:start + chunk_size]))


def transformed_summary(preprocessor: BaseEstimator, X: pd.DataFrame, chunk_size: int = 200_000) -> dict[str, Any]:
    """Sanity statistics of the transformed data computed in chunks (no full matrix kept)."""
    rows = nan = inf = 0
    max_abs = 0.0
    n_out = None
    for block in transform_in_chunks(preprocessor, X, chunk_size):
        n_out = block.shape[1]
        rows += block.shape[0]
        nan += int(np.isnan(block).sum())
        inf += int(np.isinf(block).sum())
        finite = block[np.isfinite(block)]
        if finite.size:
            max_abs = max(max_abs, float(np.abs(finite).max()))
    return {"rows": rows, "n_output_features": n_out, "nan_cells": nan, "inf_cells": inf, "max_abs_value": max_abs}


def chunked_handling_report(
    preprocessor: BaseEstimator, X_train: pd.DataFrame, X_test: pd.DataFrame | None = None, chunk_size: int = 200_000,
) -> dict[str, Any]:
    """Same content as pipeline.handling_reports, computed chunk by chunk (bounded memory).

    Per-chunk reports from the existing function are summed; fill values and strategies come from
    the fitted preprocessor and are identical for every chunk.
    """
    from datalens.preprocessing.pipeline import handling_reports

    def merge(frame: pd.DataFrame) -> dict[str, Any]:
        total: dict[str, Any] | None = None
        for start in range(0, len(frame), chunk_size):
            part = handling_reports(preprocessor, frame.iloc[start:start + chunk_size])["train"]
            if total is None:
                total = part
                continue
            for k in ("rows", "positive_inf_cells", "negative_inf_cells", "nan_cells"):
                total[k] += part[k]
            for k in ("inf_by_column", "nan_by_column"):
                for col, n in part[k].items():
                    total[k][col] = total[k].get(col, 0) + n
        return total or {"rows": 0, "positive_inf_cells": 0, "negative_inf_cells": 0, "nan_cells": 0,
                         "inf_by_column": {}, "nan_by_column": {}}

    out = handling_reports(preprocessor, X_train.iloc[:1])      # strategies + fill values (rows replaced below)
    out["train"] = merge(X_train)
    if X_test is not None:
        out["test"] = merge(X_test)
    affected = set(out["train"]["inf_by_column"]) | set(out["train"]["nan_by_column"])
    fills = out.pop("train_fill_values_for_affected_columns", {})
    num_pipe = preprocessor.named_transformers_["num"]
    cols = list(preprocessor.transformers_[[t[0] for t in preprocessor.transformers_].index("num")][2])
    stats = dict(zip(cols, [None if pd.isna(v) else float(v) for v in num_pipe.named_steps["impute"].statistics_]))
    out["train_fill_values_for_affected_columns"] = {c: stats[c] for c in sorted(affected)}
    return out
