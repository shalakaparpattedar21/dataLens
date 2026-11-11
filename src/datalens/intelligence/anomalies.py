"""Extensible anomaly detection on a seeded sample.

Detectors register in DETECTORS and share one contract: (matrix, params) -> (scores, flagged mask, extra), where a
higher score means more anomalous. Three classes of result are kept apart in the output:

* statistical_outlier      - outside the 1.5×IQR fences of a single feature (iqr method)
* multivariate_anomaly     - unusual in combination across features (isolation_forest, lof, dbscan)
* potential_data_error     - a *heuristic indicator* (infinite value, or a negative value in a column that is
                             otherwise non-negative). It is evidence to check, not proof.

An anomaly is not automatically a bad record: rows are never removed or modified by this service.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.preprocessing import RobustScaler

from datalens.app_service import _name_tokens
from datalens.intelligence.sampling import ROW_ID, split_feature_types

MAX_ANOMALY_FEATURES = 25
DEFAULT_MAX_ROWS = 20_000
LOF_MAX_ROWS = 20_000
DBSCAN_MAX_ROWS = 10_000
SCATTER_POINTS = 2_000
TABLE_ROWS = 500
METHODS = ("isolation_forest", "lof", "iqr", "dbscan")
METHOD_CLASS = {"isolation_forest": "multivariate_anomaly", "lof": "multivariate_anomaly", "dbscan": "multivariate_anomaly",
                "iqr": "statistical_outlier"}


def _threshold_flags(scores: np.ndarray, contamination: float) -> tuple[np.ndarray, float]:
    k = max(1, int(round(contamination * len(scores))))
    cut = float(np.partition(scores, len(scores) - k)[len(scores) - k])
    return scores >= cut, cut


def _isolation_forest(X: np.ndarray, p: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    model = IsolationForest(n_estimators=p.get("n_estimators", 200), contamination="auto", random_state=p["seed"], n_jobs=1)
    model.fit(X)
    scores = -model.score_samples(X)
    flags, cut = _threshold_flags(scores, p["contamination"])
    return scores, flags, {"score_threshold": cut, "score_meaning": "−score_samples: higher = isolated in fewer random splits"}


def _lof(X: np.ndarray, p: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    k = int(min(p.get("n_neighbors", 20), max(2, len(X) - 1)))
    model = LocalOutlierFactor(n_neighbors=k, contamination="auto")
    model.fit_predict(X)
    scores = -model.negative_outlier_factor_
    flags, cut = _threshold_flags(scores, p["contamination"])
    return scores, flags, {"score_threshold": cut, "n_neighbors": k, "score_meaning": "local outlier factor: ≈1 normal, >1 sparser than neighbours"}


def _iqr(X: np.ndarray, p: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    q1, q3 = np.nanpercentile(X, [25, 75], axis=0)
    spread = q3 - q1
    usable = spread > 0
    exceed = np.zeros_like(X)
    if usable.any():
        below = (q1[usable] - X[:, usable]) / spread[usable]
        above = (X[:, usable] - q3[usable]) / spread[usable]
        exceed[:, usable] = np.maximum(np.maximum(below, above), 0.0)
    scores = exceed.max(axis=1)
    flags = scores > 1.5
    return scores, flags, {"score_threshold": 1.5, "score_meaning": "largest distance outside the IQR box, in IQR units (flag if >1.5)",
                           "constant_iqr_features": int((~usable).sum()), "contamination_ignored": True}


def _dbscan(X: np.ndarray, p: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    d = X.shape[1]
    min_samples = int(p.get("min_samples", max(5, 2 * d)))
    min_samples = min(min_samples, max(2, len(X) - 1))
    dist, _ = NearestNeighbors(n_neighbors=min_samples).fit(X).kneighbors(X)
    kth = dist[:, -1]
    eps = float(p.get("eps") or np.percentile(kth, 90))
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(X)
    flags = labels == -1
    return kth, flags, {"eps": eps, "min_samples": min_samples, "eps_basis": "90th percentile of k-NN distance" if not p.get("eps") else "user",
                        "score_threshold": eps, "score_meaning": f"distance to the {min_samples}th nearest neighbour; flagged = DBSCAN noise",
                        "clusters": int(len(set(labels)) - (1 if -1 in labels else 0)), "contamination_ignored": True,
                        "exploratory": True}


DETECTORS: dict[str, Callable] = {"isolation_forest": _isolation_forest, "lof": _lof, "iqr": _iqr, "dbscan": _dbscan}


def default_features(frame: pd.DataFrame, target: str | None) -> list[str]:
    cols = split_feature_types(frame, exclude=[target] if target else [])["numeric"]
    # identifier-like columns (names with "id"/"uuid", or unique integer counters) describe row order, not behaviour
    cols = [c for c in cols if not (_name_tokens(c) & {"id", "uuid"}) and not (pd.api.types.is_integer_dtype(frame[c]) and frame[c].nunique() >= 0.95 * len(frame))] or cols
    if len(cols) <= MAX_ANOMALY_FEATURES:
        return cols
    data = frame[cols].astype("float64").replace([np.inf, -np.inf], np.nan)
    # Most complete columns with the widest robust spread: deterministic, no target needed.
    q = data.quantile([.25, .75])
    spread = (q.loc[.75] - q.loc[.25]).fillna(0)
    ranked = sorted(cols, key=lambda c: (-float(data[c].notna().mean() > 0.9), -float(spread[c] > 0), cols.index(c)))
    return ranked[:MAX_ANOMALY_FEATURES]


def run_anomaly_detection(frame: pd.DataFrame, target: str | None, info: dict[str, Any], method: str = "isolation_forest",
                          contamination: float = 0.01, features: list[str] | None = None, max_rows: int = DEFAULT_MAX_ROWS,
                          seed: int = 42) -> dict[str, Any]:
    if method not in DETECTORS:
        raise ValueError(f"Unknown anomaly method '{method}'. Choose one of: {', '.join(METHODS)}")
    if not 0.0005 <= contamination <= 0.2:
        raise ValueError("contamination must be between 0.0005 and 0.2")
    available = split_feature_types(frame, exclude=[target] if target else [])["numeric"]
    chosen = features or default_features(frame, target)
    bad = [c for c in chosen if c not in available]
    if bad:
        raise ValueError(f"Not usable numeric feature(s): {', '.join(bad[:5])}")
    if len(chosen) > MAX_ANOMALY_FEATURES:
        raise ValueError(f"Select at most {MAX_ANOMALY_FEATURES} features")
    if not chosen:
        raise ValueError("No numeric, non-constant features are available for anomaly detection")

    limit = {"lof": LOF_MAX_ROWS, "dbscan": DBSCAN_MAX_ROWS}.get(method, DEFAULT_MAX_ROWS)
    limit = min(limit, max(1000, int(max_rows)))
    work = frame
    if len(work) > limit:
        idx = np.sort(np.random.default_rng([seed, 99]).choice(len(work), limit, replace=False))
        work = work.iloc[idx]
    work = work.reset_index(drop=True)
    if len(work) < 20:
        raise ValueError("Too few rows (<20) for anomaly detection")

    raw = work[chosen].astype("float64")
    inf_mask = np.isinf(raw.to_numpy())
    raw = raw.replace([np.inf, -np.inf], np.nan)
    missing_before = int(raw.isna().to_numpy().sum())
    medians = raw.median().fillna(0.0)
    filled = raw.fillna(medians)
    X = RobustScaler().fit_transform(filled.to_numpy())
    X = np.clip(X, -50, 50)  # keeps extreme magnitudes from overflowing distance computations

    scores, flags, extra = DETECTORS[method](X, {"contamination": contamination, "seed": seed})
    n, flagged = len(work), int(flags.sum())

    # descriptive explanation: robust z of each feature (distance from the median in IQR units)
    q1, q3 = np.nanpercentile(filled.to_numpy(), [25, 75], axis=0)
    iqr_scale = np.where((q3 - q1) > 0, q3 - q1, np.nan)
    rz = (filled.to_numpy() - medians.to_numpy()) / iqr_scale
    # data-error indicators
    nonneg = [(raw[c].dropna() >= 0).mean() >= 0.999 and (raw[c].dropna() > 0).any() for c in chosen]
    neg_cols = np.array([bool(v) for v in nonneg])
    error_reasons: list[list[str]] = [[] for _ in range(n)]
    negs = (raw.to_numpy() < 0) & neg_cols
    for i in np.where(inf_mask.any(axis=1) | negs.any(axis=1))[0]:
        cols_inf = [chosen[j] for j in np.where(inf_mask[i])[0]]
        cols_neg = [chosen[j] for j in np.where(negs[i])[0]]
        if cols_inf:
            error_reasons[i].append("infinite value in " + ", ".join(cols_inf[:3]))
        if cols_neg:
            error_reasons[i].append("negative value in otherwise non-negative column " + ", ".join(cols_neg[:3]))
    candidate_idx = [i for i in range(n) if error_reasons[i]]

    order = np.argsort(-scores)
    flagged_idx = [i for i in order if flags[i]]
    table = []
    for i in flagged_idx[:TABLE_ROWS]:
        z = np.nan_to_num(rz[i], nan=0.0)
        top = np.argsort(-np.abs(z))[:3]
        table.append({
            "row_id": int(work.at[i, ROW_ID]), "score": round(float(scores[i]), 5),
            "label": None if not target or target not in work.columns else (None if pd.isna(work.at[i, target]) else str(work.at[i, target])),
            "category": METHOD_CLASS[method], "data_error_indicators": error_reasons[i],
            "top_features": [{"feature": chosen[j], "value": None if pd.isna(raw.iat[i, j]) else float(raw.iat[i, j]),
                              "median": float(medians.iloc[j]), "robust_z": round(float(z[j]), 2)} for j in top if abs(z[j]) > 0],
        })
    # score distribution (all rows vs flagged rows share the same bins)
    hi = float(np.percentile(scores, 99.5)) if len(scores) > 200 else float(scores.max())
    lo = float(scores.min())
    hi = hi if hi > lo else lo + 1.0
    edges = np.linspace(lo, hi, 31)
    all_counts, _ = np.histogram(np.clip(scores, lo, hi), bins=edges)
    flag_counts, _ = np.histogram(np.clip(scores[flags], lo, hi), bins=edges)
    # 2-D projection (PCA) for the scatter plot: all flagged rows (capped) plus a seeded normal subsample
    scatter: dict[str, Any] = {"points": [], "explained_variance": None, "projection": "PCA on the scaled selected features"}
    if X.shape[1] >= 2:
        pca = PCA(n_components=2, random_state=seed)
        coords = pca.fit_transform(X)
        scatter["explained_variance"] = [round(float(v), 4) for v in pca.explained_variance_ratio_]
    else:
        coords = np.column_stack([X[:, 0], scores])
        scatter["projection"] = "feature value (x) vs anomaly score (y)"
    rng = np.random.default_rng([seed, 5])
    flagged_pick = np.array(flagged_idx[:SCATTER_POINTS // 2], dtype=int)
    normal_idx = np.where(~flags)[0]
    normal_pick = rng.choice(normal_idx, min(len(normal_idx), SCATTER_POINTS - len(flagged_pick)), replace=False) if len(normal_idx) else np.array([], int)
    for i in np.concatenate([normal_pick, flagged_pick]).astype(int):
        scatter["points"].append({"row_id": int(work.at[i, ROW_ID]), "x": round(float(coords[i, 0]), 4), "y": round(float(coords[i, 1]), 4),
                                  "score": round(float(scores[i]), 4), "flagged": bool(flags[i])})
    by_class = []
    if target and target in work.columns:
        lab = work[target].fillna("(missing)").astype(str)
        for cls, count in lab.value_counts().head(30).items():
            sel = (lab == cls).to_numpy()
            by_class.append({"label": cls, "rows": int(count), "flagged": int((flags & sel).sum()),
                             "flagged_percent": round(100 * float((flags & sel).sum()) / count, 2)})
    return {
        "kind": "anomalies", "method": method, "category": METHOD_CLASS[method],
        "summary": {"rows_analyzed": n, "rows_available": info["rows_total"], "rows_sampled_from_source": info["rows_sampled"],
                    "flagged": flagged, "flagged_percent": round(100 * flagged / n, 3),
                    "data_error_indicator_rows": len(candidate_idx), "data_error_indicator_rows_also_flagged": int(sum(1 for i in candidate_idx if flags[i])),
                    "missing_cells_imputed": missing_before, "infinite_cells_as_missing": int(inf_mask.sum())},
        "config": {"method": method, "contamination": contamination, "features": chosen, "max_rows": limit, "seed": seed,
                   "preprocessing": "infinite→missing, median impute, RobustScaler, clip ±50", **{k: v for k, v in extra.items() if k not in ("score_meaning",)}},
        "score_meaning": extra.get("score_meaning"), "sample": info,
        "score_histogram": {"edges": [round(float(e), 5) for e in edges], "all": all_counts.tolist(), "flagged": flag_counts.tolist()},
        "scatter": scatter, "records": table, "records_total_flagged": flagged, "records_shown": len(table),
        "by_class": by_class,
        "data_error_candidates": [{"row_id": int(work.at[i, ROW_ID]), "reasons": error_reasons[i], "flagged": bool(flags[i]), "score": round(float(scores[i]), 5),
                                   "label": None if not target or target not in work.columns or pd.isna(work.at[i, target]) else str(work.at[i, target])}
                                  for i in candidate_idx[:200]],
        "data_error_note": "Heuristic indicators only: an infinite value, or a negative value in a column that is otherwise non-negative (≥99.9% of values ≥ 0). They are listed whether or not the row was flagged as an anomaly.",
        "interpretation": ("Flagged rows are unusual relative to the analysed sample, not necessarily wrong. In security data, "
                           "attacks are often anomalies. Inspect before deciding whether to keep them; DataLens never removes them. "
                           "'Why flagged' lists the features furthest from the median (robust z-score): descriptive, not model-intrinsic."),
    }
