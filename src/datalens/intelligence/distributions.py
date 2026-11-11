"""Per-column distributions from the seeded sample: histograms, box-plot statistics, categorical top values."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from datalens.intelligence.sampling import clean_numeric, split_feature_types

MAX_NUMERIC_COLUMNS = 40
MAX_CATEGORICAL_COLUMNS = 20


def compute_distributions(frame: pd.DataFrame, target: str | None, info: dict[str, Any], bins: int = 20) -> dict[str, Any]:
    types = split_feature_types(frame, exclude=[target] if target else [])
    numeric_cols = types["numeric"]
    # Most informative first: widest spread relative to the IQR scale is not meaningful, so rank by non-null count
    # then column order. The cap is reported rather than hidden.
    omitted = max(0, len(numeric_cols) - MAX_NUMERIC_COLUMNS)
    numeric_cols = numeric_cols[:MAX_NUMERIC_COLUMNS]
    data = clean_numeric(frame, numeric_cols)
    numeric = []
    for col in numeric_cols:
        values = data[col].dropna().to_numpy()
        if not len(values):
            continue
        q1, med, q3 = np.percentile(values, [25, 50, 75])
        spread = q3 - q1
        lo_fence, hi_fence = q1 - 1.5 * spread, q3 + 1.5 * spread
        inside = values[(values >= lo_fence) & (values <= hi_fence)]
        low_whisker = float(inside.min()) if len(inside) else float(values.min())
        high_whisker = float(inside.max()) if len(inside) else float(values.max())
        counts, edges = np.histogram(values, bins=bins)
        numeric.append({
            "column": col, "n": int(len(values)), "missing_percent": round(100 * (1 - len(values) / len(frame)), 3),
            "mean": float(values.mean()), "std": float(values.std()), "min": float(values.min()), "max": float(values.max()),
            "q1": float(q1), "median": float(med), "q3": float(q3), "whisker_low": low_whisker, "whisker_high": high_whisker,
            "outliers_low": int((values < lo_fence).sum()) if spread > 0 else 0,
            "outliers_high": int((values > hi_fence).sum()) if spread > 0 else 0,
            "skew": float(pd.Series(values).skew()) if len(values) > 2 else 0.0,
            "histogram": {"counts": counts.tolist(), "edges": [float(e) for e in edges]},
        })
    categorical = []
    for col in (types["categorical"] + types["high_cardinality"])[:MAX_CATEGORICAL_COLUMNS]:
        counts = frame[col].fillna("(missing)").astype(str).value_counts()
        categorical.append({"column": col, "distinct": int(counts.size), "n": int(len(frame)),
                            "high_cardinality": col in types["high_cardinality"],
                            "top": [{"value": str(k), "count": int(v)} for k, v in counts.head(10).items()]})
    return {"kind": "distributions", "sample": info, "numeric": numeric, "categorical": categorical,
            "constant_columns": types["constant"], "numeric_columns_omitted": omitted,
            "note": f"Histograms and box plots are computed on {info['rows_sampled']:,} of {info['rows_total']:,} rows "
                    "(seeded sample). Whiskers follow the 1.5×IQR rule."}
