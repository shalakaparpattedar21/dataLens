"""Feature relationship analysis: correlations, redundancy, feature-target association, Cramér's V, VIF.

Limits (all reported in the output): at most MAX_NUMERIC numeric columns enter the matrices; when more exist,
columns are ranked by association with the target (or by completeness when there is no target) and the rest are
listed as omitted. Missing values are handled pairwise for correlations and median-imputed for MI and VIF.
Correlation is not causation, and Pearson only sees linear relationships.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression

from datalens.intelligence.sampling import clean_numeric, split_feature_types, target_kind

MAX_NUMERIC = 60
MAX_CATEGORICAL = 20
MAX_VIF_COLUMNS = 30
SPEARMAN_ROWS = 20_000
MI_ROWS = 20_000
VIF_WARN, VIF_SEVERE = 5.0, 10.0


def cramers_v(a: pd.Series, b: pd.Series) -> float | None:
    """Bias-corrected Cramér's V between two categorical series (Bergsma 2013). None if undefined."""
    table = pd.crosstab(a, b)
    if table.shape[0] < 2 or table.shape[1] < 2:
        return None
    obs = table.to_numpy(dtype=float)
    n = obs.sum()
    expected = obs.sum(1, keepdims=True) @ obs.sum(0, keepdims=True) / n
    chi2 = float(((obs - expected) ** 2 / expected).sum())
    phi2 = chi2 / n
    r, k = obs.shape
    phi2c = max(0.0, phi2 - (k - 1) * (r - 1) / (n - 1))
    rc, kc = r - (r - 1) ** 2 / (n - 1), k - (k - 1) ** 2 / (n - 1)
    denom = min(kc - 1, rc - 1)
    return float(np.sqrt(phi2c / denom)) if denom > 0 else None


def _encode_target(series: pd.Series, kind: str) -> np.ndarray:
    if kind == "regression":
        return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return pd.factorize(series.fillna("(missing)").astype(str))[0]


def feature_target_mi(data: pd.DataFrame, y: np.ndarray, kind: str, seed: int) -> dict[str, float]:
    """Mutual information of each (median-imputed) numeric column with the target, on at most MI_ROWS rows."""
    if data.empty:
        return {}
    ok = ~np.isnan(y) if kind == "regression" else np.ones(len(y), bool)
    X = data.loc[ok].copy()
    yy = y[ok]
    if len(X) > MI_ROWS:
        idx = np.random.default_rng(seed).choice(len(X), MI_ROWS, replace=False)
        X, yy = X.iloc[idx], yy[idx]
    X = X.fillna(X.median()).fillna(0.0)
    if len(X) < 10:
        return {}
    func = mutual_info_regression if kind == "regression" else mutual_info_classif
    scores = func(X.to_numpy(), yy, random_state=seed)
    return dict(zip(X.columns, (float(s) for s in scores)))


def vif_table(data: pd.DataFrame) -> list[dict[str, Any]]:
    """VIF_i = diag(R^-1) for the correlation matrix R of median-imputed columns. Perfect collinearity -> inf."""
    cols = [c for c in data.columns if data[c].std(skipna=True) > 0][:MAX_VIF_COLUMNS]
    if len(cols) < 2 or len(data) < len(cols) + 5:
        return []
    X = data[cols].fillna(data[cols].median())
    R = np.corrcoef(X.to_numpy(), rowvar=False)
    R = np.nan_to_num(R)
    try:
        inv = np.linalg.inv(R)
        vifs = np.diag(inv).copy()
        if not np.all(np.isfinite(vifs)) or np.any(vifs < 0.99):
            raise np.linalg.LinAlgError
    except np.linalg.LinAlgError:
        # Singular matrix: report columns that are (near-)exactly explained by others via the pseudo-inverse.
        vifs = np.diag(np.linalg.pinv(R)).copy()
        vifs = np.where(vifs > 1e6, np.inf, np.maximum(vifs, 1.0))
    rows = [{"column": c, "vif": (None if not np.isfinite(v) else round(float(v), 2)),
             "perfect_collinearity": bool(not np.isfinite(v) or v > 1e6)} for c, v in zip(cols, vifs)]
    return sorted(rows, key=lambda r: (r["vif"] is not None, -(r["vif"] or 0)))


def compute_relationships(frame: pd.DataFrame, target: str | None, info: dict[str, Any], seed: int = 42,
                          corr_threshold: float = 0.9) -> dict[str, Any]:
    types = split_feature_types(frame, exclude=[target] if target else [])
    y_series = frame[target] if target and target in frame.columns else None
    kind = target_kind(y_series)
    y = _encode_target(y_series, kind) if kind != "none" else None
    numeric = types["numeric"]
    omitted_numeric: list[str] = []
    data_all = clean_numeric(frame, numeric)
    mi_all: dict[str, float] = {}
    if kind != "none" and numeric:
        mi_all = feature_target_mi(data_all, y, kind, seed)
    if len(numeric) > MAX_NUMERIC:
        if mi_all:
            ranked = sorted(numeric, key=lambda c: -mi_all.get(c, 0.0))
            basis = "highest mutual information with the target"
        else:
            ranked = sorted(numeric, key=lambda c: (data_all[c].isna().mean(), numeric.index(c)))
            basis = "most complete columns (no usable target)"
        keep = ranked[:MAX_NUMERIC]
        omitted_numeric = [c for c in numeric if c not in keep]
        numeric = [c for c in numeric if c in keep]
        cap_note = f"{len(omitted_numeric)} numeric columns omitted from the matrices; kept the {MAX_NUMERIC} with the {basis}."
    else:
        cap_note = None
    data = data_all[numeric]

    heat: dict[str, Any] = {"columns": [], "pearson": [], "spearman": []}
    pairs: list[dict[str, Any]] = []
    if len(numeric) >= 2:
        pearson = data.corr(method="pearson", min_periods=10)
        sdata = data if len(data) <= SPEARMAN_ROWS else data.sample(SPEARMAN_ROWS, random_state=seed)
        spearman = sdata.corr(method="spearman", min_periods=10)
        fill = pearson.fillna(0.0).to_numpy()
        order = list(leaves_list(linkage(squareform(np.clip(1 - np.abs(fill), 0, None) * (1 - np.eye(len(fill))), checks=False), method="average"))) if len(numeric) > 2 else list(range(len(numeric)))
        cols = [numeric[i] for i in order]
        p = pearson.loc[cols, cols]
        s = spearman.loc[cols, cols]
        rnd = lambda m: [[None if pd.isna(v) else round(float(v), 3) for v in row] for row in m.to_numpy()]
        heat = {"columns": cols, "pearson": rnd(p), "spearman": rnd(s), "ordering": "hierarchical clustering on 1-|Pearson|"}
        for i, a in enumerate(cols):
            for j in range(i + 1, len(cols)):
                b = cols[j]
                rp, rs = p.loc[a, b], s.loc[a, b]
                strongest = max((abs(v) for v in (rp, rs) if not pd.isna(v)), default=0.0)
                if strongest >= corr_threshold:
                    pairs.append({"a": a, "b": b, "pearson": None if pd.isna(rp) else round(float(rp), 4),
                                  "spearman": None if pd.isna(rs) else round(float(rs), 4), "abs_max": round(float(strongest), 4)})
        pairs.sort(key=lambda r: -r["abs_max"])

    # Redundancy: within each connected group of correlated columns, keep the most target-informative (or most
    # complete) column and list the others as candidates to review. This is a heuristic suggestion, not a verdict.
    redundant: list[dict[str, Any]] = []
    parent = {c: c for c in numeric}
    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for pr in pairs:
        parent[find(pr["a"])] = find(pr["b"])
    groups: dict[str, list[str]] = {}
    for c in numeric:
        groups.setdefault(find(c), []).append(c)
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = max(members, key=lambda c: (mi_all.get(c, 0.0), -float(data[c].isna().mean())))
        redundant.append({"keep": keep, "candidates": [m for m in members if m != keep], "members": members,
                          "basis": "kept the column with the highest target mutual information" if mi_all
                          else "kept the most complete column (no usable target)"})
    vif = vif_table(data)

    # Feature-target relationships
    ranking: list[dict[str, Any]] = []
    if kind != "none":
        for col in numeric:
            row: dict[str, Any] = {"column": col, "type": "numeric", "mutual_information": round(mi_all.get(col, 0.0), 5)}
            x = data[col]
            if kind == "regression":
                row["spearman_with_target"] = _safe(x.corr(pd.Series(y, index=x.index), method="spearman"))
            ranking.append(row)
        cat_cols = (types["categorical"])[:MAX_CATEGORICAL]
        for col in cat_cols:
            tcol = y_series.fillna("(missing)").astype(str) if kind == "classification" else None
            if tcol is None:
                continue
            v = cramers_v(frame[col].fillna("(missing)").astype(str), tcol)
            ranking.append({"column": col, "type": "categorical", "cramers_v": None if v is None else round(v, 4)})
        ranking.sort(key=lambda r: -(r.get("mutual_information") or 0.0 if r["type"] == "numeric" else (r.get("cramers_v") or 0.0)))
    # Categorical association (feature vs feature)
    cat_pairs: list[dict[str, Any]] = []
    cats = types["categorical"][:MAX_CATEGORICAL]
    for i, a in enumerate(cats):
        for b in cats[i + 1:]:
            v = cramers_v(frame[a].fillna("(missing)").astype(str), frame[b].fillna("(missing)").astype(str))
            if v is not None and v >= 0.5:
                cat_pairs.append({"a": a, "b": b, "cramers_v": round(v, 4)})
    cat_pairs.sort(key=lambda r: -r["cramers_v"])

    skipped = ([{"column": c, "reason": "constant"} for c in types["constant"]] +
               [{"column": c, "reason": "high cardinality (>50 distinct values); excluded from association tests"} for c in types["high_cardinality"]] +
               [{"column": c, "reason": "omitted: matrix column cap"} for c in omitted_numeric])
    return {
        "kind": "relationships", "sample": info, "target": target if kind != "none" else None, "target_kind": kind,
        "threshold": corr_threshold, "heatmap": heat, "high_correlation_pairs": pairs[:200], "high_correlation_pairs_total": len(pairs),
        "redundancy_groups": redundant, "vif": vif, "vif_thresholds": {"warning": VIF_WARN, "severe": VIF_SEVERE},
        "feature_target": ranking, "categorical_pairs": cat_pairs[:50], "skipped": skipped, "cap_note": cap_note,
        "methodology": {
            "pearson": "Linear correlation, pairwise-complete observations; infinities treated as missing.",
            "spearman": f"Rank correlation on at most {SPEARMAN_ROWS:,} rows; captures monotonic, non-linear relations.",
            "mutual_information": "k-NN estimator (sklearn), median-imputed, on at most 20,000 rows; ≥0, unit-free, no sign.",
            "cramers_v": "Bias-corrected Cramér's V for categorical pairs with ≤50 distinct values.",
            "vif": f"Diagonal of the inverse correlation matrix of ≤{MAX_VIF_COLUMNS} median-imputed columns; >5 warns, >10 is severe.",
            "limits": "Associations are not causal. Pearson ignores non-linear structure; MI estimates are noisy on small samples."},
    }


def _safe(v: float) -> float | None:
    return None if v is None or pd.isna(v) else round(float(v), 4)
