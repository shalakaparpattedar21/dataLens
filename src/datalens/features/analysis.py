"""Feature analysis computed on TRAINING data only.

Nothing here removes a feature. Each function returns evidence; a human (or a logged policy in
`datalens.features.selection.ExclusionLog`) decides. Pass ONLY training rows: using test rows
here would let test information influence which features are kept.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.tree import DecisionTreeClassifier


def _finite_sample(X: pd.DataFrame, max_rows: int | None, seed: int) -> pd.DataFrame:
    """Row subsample (if needed) with +/-inf converted to NaN. Returns a new small frame."""
    if max_rows is not None and len(X) > max_rows:
        X = X.iloc[np.sort(np.random.default_rng(seed).choice(len(X), size=max_rows, replace=False))]
    return X.replace([np.inf, -np.inf], np.nan)


# ----------------------------------------------------------------------- A. low variance
def low_variance_report(
    X_train: pd.DataFrame, variance_threshold: float = 1e-8, near_constant_threshold: float = 0.99
) -> pd.DataFrame:
    """Per-feature variance and dominance of the most common value (finite values only).

    Variance depends on units (a feature measured in seconds can have tiny variance yet be
    informative), so only ZERO variance is suggested for dropping; everything else is 'review'.
    """
    rows = []
    for c in X_train.columns:
        v = X_train[c].to_numpy(dtype=float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            rows.append({"feature": c, "variance": np.nan, "n_unique": 0, "top_value_share": np.nan,
                         "all_non_finite": True, "suggested_action": "review (no finite values)"})
            continue
        vals, counts = np.unique(v, return_counts=True)
        var, share = float(v.var()), float(counts.max() / v.size)
        if len(vals) == 1:
            action = "drop (constant on training data: no information to learn)"
        elif var < variance_threshold or share >= near_constant_threshold:
            action = "review (low variance / near-constant: a rare value may still mark an attack)"
        else:
            action = "keep"
        rows.append({"feature": c, "variance": var, "n_unique": int(len(vals)), "top_value_share": share,
                     "all_non_finite": False, "suggested_action": action})
    return pd.DataFrame(rows).set_index("feature")


# ----------------------------------------------------------------------- B. correlation
def suggest_correlated_drops(corr: pd.DataFrame, threshold: float) -> list[dict[str, Any]]:
    """Greedy, deterministic redundancy removal (caret-style 'findCorrelation').

    Repeatedly take the most correlated remaining pair and drop the member with the larger mean
    absolute correlation to all remaining features. Order-dependent by nature; the result is a
    SUGGESTION with evidence, not a decision.
    """
    absc = corr.abs().fillna(0.0)
    names = list(absc.columns)
    remaining = list(range(len(names)))
    M = absc.to_numpy().copy()
    np.fill_diagonal(M, 0.0)
    out: list[dict[str, Any]] = []
    while len(remaining) > 1:
        sub = M[np.ix_(remaining, remaining)]
        if sub.max() < threshold:
            break
        i, j = np.unravel_index(int(np.argmax(sub)), sub.shape)
        mi, mj = sub[i].mean(), sub[j].mean()
        drop_local, keep_local = (i, j) if mi > mj else (j, i)
        d, k = remaining[drop_local], remaining[keep_local]
        out.append({"dropped": names[d], "kept_partner": names[k], "abs_corr": float(M[d, k]),
                    "mean_abs_corr_dropped": float(max(mi, mj)), "mean_abs_corr_partner": float(min(mi, mj))})
        remaining.remove(d)
    return out


def correlation_analysis(
    X_train: pd.DataFrame, threshold: float = 0.95, method: str = "pearson",
    max_rows: int | None = 200_000, seed: int = 42,
) -> dict[str, Any]:
    """Highly correlated feature pairs and a suggested drop list (training data only).

    Why removing correlated features can help: linear models become unstable/hard to interpret
    under collinearity, cost grows with features, and importance scores get split between twins.
    When it is not necessary: tree ensembles are largely unaffected in accuracy, and two correlated
    features can still carry complementary signal. Correlation among features says nothing about
    relevance to the target, so we never drop on low correlation WITH the target.
    """
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    sample = _finite_sample(X_train, max_rows, seed)
    corr = sample.corr(method=method)
    cols = list(corr.columns)
    A = corr.abs().to_numpy()
    iu = np.triu_indices(len(cols), k=1)
    mask = np.nan_to_num(A[iu]) >= threshold
    pairs = sorted(({"feature_a": cols[i], "feature_b": cols[j], "corr": float(corr.iat[i, j])}
                    for i, j in zip(iu[0][mask], iu[1][mask])), key=lambda p: -abs(p["corr"]))
    return {"method": method, "threshold": threshold, "rows_used": int(len(sample)), "n_features": len(cols),
            "n_pairs_above_threshold": len(pairs), "pairs": pairs,
            "suggested_drops": suggest_correlated_drops(corr, threshold)}


# ----------------------------------------------------------------------- shortcut probe
def single_feature_probe(
    X_train: pd.DataFrame, y_train: pd.Series | np.ndarray, max_rows: int | None = 100_000,
    cv: int = 3, max_depth: int = 3, seed: int = 42, flag_auc: float = 0.99,
) -> pd.DataFrame:
    """How well does ONE feature, alone, predict the target? (cross-validated, training rows only)

    A depth-limited decision tree is fitted per feature. High single-feature skill marks a
    feature as a CANDIDATE shortcut or leakage source (e.g. a port number or a collection
    artifact) -- it can equally be a genuinely strong signal. The flag asks for human review and
    for with/without comparisons; it never removes anything.
    Binary targets also get ROC-AUC; multiclass gets balanced accuracy only.
    """
    y_all = pd.Series(np.asarray(y_train)).astype(str).reset_index(drop=True)
    X = X_train.reset_index(drop=True)
    if len(X) != len(y_all):
        raise ValueError("X_train and y_train must have the same length")
    if max_rows is not None and len(X) > max_rows:
        idx = np.sort(np.random.default_rng(seed).choice(len(X), size=max_rows, replace=False))
        X, y_all = X.iloc[idx], y_all.iloc[idx]
    X = X.replace([np.inf, -np.inf], np.nan)
    keep_classes = y_all.value_counts()[lambda s: s >= cv].index
    mask = y_all.isin(keep_classes).to_numpy()
    X, y = X[mask], y_all[mask].to_numpy()
    classes = np.unique(y)
    if len(classes) < 2:
        raise ValueError("Need at least two classes with >= cv samples in the probe sample")
    binary = len(classes) == 2
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=seed)
    rows = []
    for c in X.columns:
        tree = DecisionTreeClassifier(max_depth=max_depth, random_state=seed)
        xc = X[[c]]
        if binary:
            proba = cross_val_predict(tree, xc, y, cv=skf, method="predict_proba")
            pred = np.asarray(classes)[proba.argmax(axis=1)]
            auc = float(roc_auc_score(y == classes[1], proba[:, 1]))
        else:
            pred = cross_val_predict(tree, xc, y, cv=skf)
            auc = np.nan
        rows.append({"feature": c, "balanced_accuracy": float(balanced_accuracy_score(y, pred)), "roc_auc": auc})
    out = pd.DataFrame(rows).set_index("feature").sort_values("balanced_accuracy", ascending=False)
    out["chance_balanced_accuracy"] = 1.0 / len(classes)
    out["flag_review"] = (out["roc_auc"] >= flag_auc) if binary else (out["balanced_accuracy"] >= flag_auc)
    out.attrs.update(rows_used=int(len(X)), classes=list(map(str, classes)), binary=binary, cv=cv)
    return out


# ----------------------------------------------------------------------- C. importance prep
def train_only_importance(
    X_train: pd.DataFrame, y_train: pd.Series | np.ndarray, n_estimators: int = 100, max_depth: int | None = 12,
    max_rows: int | None = 200_000, seed: int = 42, n_jobs: int = 1,
) -> pd.Series:
    """Random-forest impurity importance fitted on training rows ONLY.

    Preparation for the later importance analysis. Impurity importance is biased toward
    continuous/high-cardinality features; Phase 5 should confirm with permutation importance
    on validation data. Never feed test rows here to decide which features to keep.
    """
    y = pd.Series(np.asarray(y_train)).astype(str).reset_index(drop=True)
    X = X_train.reset_index(drop=True)
    if len(X) != len(y):
        raise ValueError("X_train and y_train must have the same length")
    if max_rows is not None and len(X) > max_rows:
        idx = np.sort(np.random.default_rng(seed).choice(len(X), size=max_rows, replace=False))
        X, y = X.iloc[idx], y.iloc[idx]
    X = X.replace([np.inf, -np.inf], np.nan)
    rf = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, random_state=seed, n_jobs=n_jobs)
    rf.fit(X, y.to_numpy())
    return pd.Series(rf.feature_importances_, index=X.columns, name="rf_impurity_importance").sort_values(ascending=False)
