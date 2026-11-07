"""Dataset profiling: measured facts about a DataFrame. No judgments live here.

Judgments (what is a problem, how severe, what to do) belong to datalens.quality.

Outliers are FLAGGED with the IQR rule, never removed: in network traffic, extreme
values are often the attacks themselves. Statistics (min/max/mean/std/IQR) are
computed on finite values only; inf and NaN are counted separately.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd


def _profile_numeric(s: pd.Series, iqr_factor: float) -> dict[str, Any]:
    values = s.to_numpy(dtype=float, na_value=np.nan)
    inf_n = int(np.isinf(values).sum())
    finite = values[np.isfinite(values)]
    out: dict[str, Any] = {"inf_n": inf_n, "negative_n": int((finite < 0).sum())}
    if finite.size == 0:
        out.update(min=None, max=None, mean=None, std=None, iqr_zero=None, outlier_iqr_n=0)
        return out
    q1, q3 = np.percentile(finite, [25, 75])
    iqr = q3 - q1
    if iqr > 0:
        outliers = int(((finite < q1 - iqr_factor * iqr) | (finite > q3 + iqr_factor * iqr)).sum())
    else:
        # With IQR == 0 the rule would flag every non-modal value; report that honestly.
        outliers = int((finite != q1).sum())
    out.update(
        min=float(finite.min()),
        max=float(finite.max()),
        mean=float(finite.mean()),
        std=float(finite.std()),
        iqr_zero=bool(iqr == 0),
        outlier_iqr_n=outliers,
    )
    return out


def _profile_column(s: pd.Series, n_rows: int, iqr_factor: float) -> dict[str, Any]:
    is_numeric = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
    non_null = s.dropna()
    vc = non_null.value_counts()
    top_share = float(vc.iloc[0] / len(non_null)) if len(non_null) else None
    missing_n = int(s.isna().sum())
    info: dict[str, Any] = {
        "column": s.name,
        "dtype": str(s.dtype),
        "kind": "numeric" if is_numeric else "categorical",
        "missing_n": missing_n,
        "missing_pct": round(100 * missing_n / n_rows, 4) if n_rows else 0.0,
        "n_unique": int(len(vc)),
        "unique_ratio": round(len(vc) / n_rows, 6) if n_rows else 0.0,
        "top_value_share": top_share,
        "is_constant": bool(len(vc) <= 1),
    }
    if is_numeric:
        info.update(_profile_numeric(s, iqr_factor))
    else:
        parsed = pd.to_numeric(non_null, errors="coerce")
        info["numeric_like_share"] = float(parsed.notna().mean()) if len(non_null) else None
        info["top_values"] = {str(k): int(v) for k, v in vc.head(5).items()}
    return info


def profile_duplicates(
    df: pd.DataFrame, feature_columns: list[str], label_column: str
) -> dict[str, Any]:
    """Count duplicate rows using row hashes (fast on millions of rows).

    - duplicate_rows_full: rows identical to an earlier row in features AND label.
    - duplicate_rows_features: rows identical in features only.
    - label_conflict_*: feature vectors that appear with more than one label. These are
      label noise or genuinely indistinguishable traffic: no model can separate them.
    Row hashing has a negligible, non-zero collision probability.
    """
    n = len(df)
    if n == 0 or not feature_columns:
        return {"n_rows": n, "duplicate_rows_full": 0, "duplicate_rows_features": 0,
                "label_conflict_groups": 0, "label_conflict_rows": 0}
    h_feat = pd.util.hash_pandas_object(df[feature_columns], index=False)
    h_full = pd.util.hash_pandas_object(df[[*feature_columns, label_column]], index=False)
    tmp = pd.DataFrame({"h": h_feat.to_numpy(), "label": df[label_column].to_numpy()})
    per_hash = tmp.groupby("h")["label"].nunique()
    conflicting = per_hash[per_hash > 1].index
    return {
        "n_rows": n,
        "duplicate_rows_full": int(h_full.duplicated().sum()),
        "duplicate_rows_features": int(h_feat.duplicated().sum()),
        "label_conflict_groups": int(len(conflicting)),
        "label_conflict_rows": int(tmp["h"].isin(conflicting).sum()),
    }


def profile_target(
    df: pd.DataFrame, label_column: str, source_column: str | None = None
) -> dict[str, Any]:
    counts = df[label_column].value_counts()
    out: dict[str, Any] = {
        "n_classes": int(len(counts)),
        "counts": {str(k): int(v) for k, v in counts.items()},
        "percent": {str(k): round(100 * v / len(df), 4) for k, v in counts.items()},
        "majority_class": str(counts.index[0]) if len(counts) else None,
        "minority_class": str(counts.index[-1]) if len(counts) else None,
        "imbalance_ratio": float(counts.iloc[0] / counts.iloc[-1]) if len(counts) else None,
    }
    if source_column and source_column in df.columns:
        ct = pd.crosstab(df[source_column], df[label_column])
        out["by_source"] = {str(src): {str(k): int(v) for k, v in row.items() if v > 0}
                            for src, row in ct.iterrows()}
    return out


def profile_dataframe(
    df: pd.DataFrame,
    label_column: str,
    exclude_columns: Iterable[str] = (),
    source_column: str | None = None,
    iqr_factor: float = 1.5,
) -> dict[str, Any]:
    """Profile all feature columns, duplicates and the target.

    exclude_columns: metadata columns (e.g. the loader's source-file column) that are
    neither features nor target; they are skipped in column profiling and duplicate hashing.
    """
    if label_column not in df.columns:
        raise KeyError(f"Label column '{label_column}' not in DataFrame")
    skip = set(exclude_columns) | {label_column}
    if source_column:
        skip.add(source_column)
    feature_columns = [c for c in df.columns if c not in skip]
    n_rows = len(df)
    return {
        "shape": {"rows": n_rows, "columns_total": df.shape[1], "feature_columns": len(feature_columns)},
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 2),
        "columns": [_profile_column(df[c], n_rows, iqr_factor) for c in feature_columns],
        "duplicates": profile_duplicates(df, feature_columns, label_column),
        "target": profile_target(df, label_column, source_column),
    }


def columns_frame(profile: dict[str, Any]) -> pd.DataFrame:
    """Per-column profile as a DataFrame (one row per feature column)."""
    return pd.DataFrame(profile["columns"])
