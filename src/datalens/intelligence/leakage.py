"""Leakage intelligence.

Two entry points:

* ``source_leakage``  - checks that need only the source data (identifier-like columns, single-feature target
                        predictors, duplicate exposure, group- and time-column evidence).
* ``run_leakage``     - checks on a prepared run (exact train/test overlap, near-duplicates, preprocessing fit scope).

Each finding carries a status that is never inflated:
  confirmed     - verified by computation on the data or by the run's execution record
  potential     - a measured warning sign that is not proof of leakage
  not_assessed  - the evidence needed is absent (stated explicitly, with what would be needed)
  clear         - the check ran and found nothing
No numeric "risk score" is produced here; severity is a documented rule applied to measured evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, r2_score
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.neighbors import NearestNeighbors
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from datalens.app_service import _name_tokens
from datalens.intelligence.relationships import cramers_v
from datalens.intelligence.sampling import ROW_ID, clean_numeric, split_feature_types, target_kind

SEVERITIES = ("critical", "high", "medium", "low", "info")
TREE_MAX_FEATURES = 60
TREE_MAX_ROWS = 20_000
GROUP_TOKENS = {"group", "session", "user", "subject", "patient", "customer", "device", "host", "src", "source", "client", "account"}
TIME_TOKENS = {"time", "date", "timestamp", "datetime", "day"}
NEAR_ROWS_TEST, NEAR_ROWS_TRAIN, NEAR_MAX_COLS = 2_000, 20_000, 100


def finding(ftype: str, severity: str, status: str, title: str, *, features: list[str] | None = None, evidence: dict | None = None,
            evidence_text: str = "", risk: str = "", action: str = "", limitations: str = "") -> dict[str, Any]:
    assert severity in SEVERITIES and status in ("confirmed", "potential", "not_assessed", "clear")
    return {"id": f"{ftype}:{(features or ['-'])[0]}", "type": ftype, "severity": severity, "status": status, "title": title,
            "features": features or [], "evidence": evidence or {}, "evidence_text": evidence_text, "risk": risk,
            "recommended_action": action, "limitations": limitations}


def summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    active = [f for f in findings if f["status"] in ("confirmed", "potential")]
    by_status = {s: sum(1 for f in findings if f["status"] == s) for s in ("confirmed", "potential", "not_assessed", "clear")}
    by_sev = {s: sum(1 for f in active if f["severity"] == s) for s in SEVERITIES}
    top = next((s for s in SEVERITIES if by_sev[s]), None)
    return {"by_status": by_status, "active_by_severity": by_sev, "highest_active_severity": top,
            "level": {"critical": "critical", "high": "high", "medium": "moderate", "low": "low", "info": "low"}.get(top, "none detected"),
            "rule": "Level = highest severity among confirmed or potential findings. Not-assessed checks are listed, never scored."}


# ----------------------------------------------------------------------------------------------- source level
def _single_feature_strength(x: pd.Series, y: np.ndarray, kind: str, seed: int) -> float | None:
    """Cross-validated strength of one feature alone: balanced accuracy (classification) or R² (regression)."""
    ok = x.notna().to_numpy()
    xv, yv = x.to_numpy(dtype=float)[ok], y[ok]
    if len(xv) < 60:
        return None
    if len(xv) > TREE_MAX_ROWS:
        idx = np.random.default_rng(seed).choice(len(xv), TREE_MAX_ROWS, replace=False)
        xv, yv = xv[idx], yv[idx]
    X = xv.reshape(-1, 1)
    if kind == "classification":
        counts = np.bincount(yv.astype(int))
        keep = counts[yv.astype(int)] >= 6
        X, yv = X[keep], yv[keep]
        if len(np.unique(yv)) < 2:
            return None
        folds = StratifiedKFold(3, shuffle=True, random_state=seed)
        preds = np.empty_like(yv)
        for tr, te in folds.split(X, yv):
            preds[te] = DecisionTreeClassifier(max_depth=3, random_state=seed).fit(X[tr], yv[tr]).predict(X[te])
        return float(balanced_accuracy_score(yv, preds))
    folds = KFold(3, shuffle=True, random_state=seed)
    preds = np.empty_like(yv, dtype=float)
    for tr, te in folds.split(X):
        preds[te] = DecisionTreeRegressor(max_depth=3, random_state=seed).fit(X[tr], yv[tr]).predict(X[te])
    return float(r2_score(yv, preds))


def _looks_like_time(series: pd.Series) -> dict[str, Any] | None:
    if pd.api.types.is_numeric_dtype(series):
        return None
    vals = series.dropna().astype(str).head(300)
    if len(vals) < 10:
        return None
    parsed = pd.to_datetime(vals, errors="coerce", format="mixed")
    if parsed.notna().mean() < 0.95:
        return None
    full = pd.to_datetime(series.dropna().astype(str), errors="coerce", format="mixed").dropna()
    return {"min": str(full.min()), "max": str(full.max()), "parsed_percent": round(100 * float(parsed.notna().mean()), 1)}


def source_leakage(frame: pd.DataFrame, target: str | None, info: dict[str, Any], profile: dict[str, Any], seed: int = 42,
                   test_size: float = 0.2) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    n = len(frame)
    y_series = frame[target] if target and target in frame.columns else None
    kind = target_kind(y_series)
    types = split_feature_types(frame, exclude=[target] if target else [])

    # 1) identifier-like columns
    id_cols = []
    for col in frame.columns:
        if col in (ROW_ID, target):
            continue
        s = frame[col]
        name_hit = bool(_name_tokens(col) & {"id", "ip", "uuid", "mac"})
        float_col = pd.api.types.is_float_dtype(s)
        ratio = s.nunique(dropna=True) / max(1, s.notna().sum())
        data_hit = n >= 100 and not float_col and ratio >= 0.95
        mono = False
        if pd.api.types.is_integer_dtype(s) and s.notna().all() and n >= 100:
            mono = bool(s.nunique() > 1 and (s.is_monotonic_increasing or s.is_monotonic_decreasing)) and ratio >= 0.5  # a constant or repeating column is not a counter
        if name_hit or data_hit or mono:
            id_cols.append((col, ratio, name_hit, data_hit, mono))
    for col, ratio, name_hit, data_hit, mono in id_cols[:20]:
        order_v = None
        if kind == "classification" and n >= 200:
            order = frame[ROW_ID] if (mono or not pd.api.types.is_numeric_dtype(frame[col])) else frame[col]
            bins = pd.qcut(order.rank(method="first"), 10, labels=False, duplicates="drop")
            order_v = cramers_v(bins.astype(str), y_series.fillna("(missing)").astype(str))
        strong = order_v is not None and order_v >= 0.3
        reasons = [r for r, f in (("name suggests an identifier", name_hit), (f"{ratio:.0%} of values are unique", data_hit),
                                  ("values are strictly ordered", mono)) if f]
        findings.append(finding(
            "identifier_like_column", "high" if strong else "medium" if data_hit or mono else "low", "potential",
            f"'{col}' looks like an identifier", features=[col],
            evidence={"unique_ratio": round(float(ratio), 4), "reasons": reasons, "order_target_cramers_v": None if order_v is None else round(order_v, 4)},
            evidence_text="; ".join(reasons) + (f". Row order along this column tracks the target (Cramér's V={order_v:.2f})." if strong else
                                                 (f". Target association along this column is weak (Cramér's V={order_v:.2f})." if order_v is not None else ".")),
            risk="Identifiers let a model memorise individual rows instead of learning patterns, and can encode collection order that correlates with the label.",
            action="Exclude the column from model features unless it carries real meaning. DataLens exports it unchanged; remove it from the CSV before preparing if it should not be used.",
            limitations="Heuristic on names and value uniqueness; a high-cardinality column can be legitimate."))

    # 2) single-feature target predictors (suspicious feature-target relationships)
    suspicious = 0
    if kind != "none":
        y = pd.factorize(y_series.fillna("(missing)").astype(str))[0] if kind == "classification" else pd.to_numeric(y_series, errors="coerce").to_numpy(dtype=float)
        data = clean_numeric(frame, types["numeric"])
        cols = types["numeric"]
        if len(cols) > TREE_MAX_FEATURES:
            cols = cols[:TREE_MAX_FEATURES]
        baseline = (1.0 / max(2, len(np.unique(y)))) if kind == "classification" else 0.0
        metric = "balanced accuracy" if kind == "classification" else "R²"
        results = []
        for col in cols:
            if col in {c for c, *_ in id_cols}:
                continue
            strength = _single_feature_strength(data[col], np.asarray(y), kind, seed)
            if strength is not None:
                results.append((col, strength))
        for col, strength in sorted(results, key=lambda r: -r[1]):
            sev = "critical" if strength >= 0.99 else "high" if strength >= 0.95 else "medium" if strength >= 0.90 else None
            if not sev:
                continue
            suspicious += 1
            findings.append(finding(
                "suspicious_feature_target", sev, "potential", f"'{col}' alone predicts the target almost perfectly", features=[col],
                evidence={"metric": metric, "cv_score": round(strength, 4), "baseline": round(baseline, 4), "model": "depth-3 decision tree, 3-fold CV, one feature"},
                evidence_text=f"A depth-3 tree on '{col}' alone reaches {metric} {strength:.3f} (chance ≈ {baseline:.2f}) in 3-fold cross-validation.",
                risk="A feature that is a near-deterministic function of the label is often a proxy for it (recorded after the outcome, or derived from it). It can also be a genuinely strong signal.",
                action="Check how and when this column is produced. If it would not exist at prediction time, drop it from model features.",
                limitations="Strong single-feature signal is a warning, not proof of leakage. Sample-based (≤20,000 rows)."))
        # name-based proxies of the target
        tname = str(target).lower()
        for col in frame.columns:
            if col in (target, ROW_ID):
                continue
            if tname in str(col).lower() and len(tname) >= 3:
                findings.append(finding(
                    "target_name_proxy", "high", "potential", f"'{col}' has the target's name in its name", features=[col],
                    evidence={"target": target}, evidence_text=f"Column name '{col}' contains the target name '{target}'.",
                    risk="Columns derived from the label (encodings, flags, predictions) leak it directly.",
                    action="Confirm the column does not encode the target; exclude it if it does.",
                    limitations="Name-based heuristic only."))
        if types["categorical"]:
            yy = y_series.fillna("(missing)").astype(str) if kind == "classification" else None
            for col in types["categorical"][:20] if yy is not None else []:
                v = cramers_v(frame[col].fillna("(missing)").astype(str), yy)
                if v is not None and v >= 0.95:
                    suspicious += 1
                    findings.append(finding(
                        "suspicious_feature_target", "high", "potential", f"Categorical '{col}' is almost a function of the target", features=[col],
                        evidence={"cramers_v": round(v, 4)}, evidence_text=f"Cramér's V between '{col}' and the target is {v:.3f}.",
                        risk="Near-perfect association suggests the column encodes the label or is derived from it.",
                        action="Check how the column is produced; exclude it if it is unavailable at prediction time.",
                        limitations="Association is not proof of leakage."))
    else:
        findings.append(finding("suspicious_feature_target", "info", "not_assessed", "Feature-target leakage not assessed", evidence={},
                                evidence_text="No usable target column (needs ≥2 distinct values).", action="Choose a target on the Prepare page and re-run the analysis."))
    if kind != "none" and not suspicious:
        findings.append(finding("suspicious_feature_target", "info", "clear", "No single feature predicts the target almost perfectly",
                                evidence_text="No numeric or categorical feature reached the review thresholds (balanced accuracy/R² ≥ 0.90; Cramér's V ≥ 0.95)."))

    # 3) duplicate exposure (full-data counts from the profile)
    dup = (profile or {}).get("duplicates") or {}
    rows = int((profile or {}).get("rows") or 0)
    g = int(dup.get("exact_duplicate_rows_global") or 0)
    if g and rows:
        rate = g / rows
        findings.append(finding(
            "duplicate_exposure", "high" if rate >= 0.05 else "medium", "potential", "Duplicate rows can fall on both sides of a split",
            evidence={"exact_duplicate_rows": g, "rows": rows, "percent": round(100 * rate, 3), "basis": "full-data scan"},
            evidence_text=f"{g:,} of {rows:,} rows ({100 * rate:.2f}%) repeat another row exactly. A random split places copies in train and test.",
            risk="Copies in both splits inflate test scores because the model has already seen those rows.",
            action="Prepare with a duplicate policy (drop_exact) and re-check the Leakage Intelligence overlap after preparation.",
            limitations="Whether overlap actually occurs is confirmed only after a preparation run."))
    elif rows:
        findings.append(finding("duplicate_exposure", "info", "clear", "No exact duplicate rows", evidence={"rows": rows}, evidence_text="Full-data scan found no exact duplicates."))

    # 4) group leakage
    group_cols = []
    for col in frame.columns:
        if col in (ROW_ID, target) or pd.api.types.is_float_dtype(frame[col]):
            continue
        distinct = frame[col].nunique(dropna=True)
        if _name_tokens(col) & GROUP_TOKENS and 2 <= distinct <= 0.5 * n:
            group_cols.append(col)
    for col in group_cols[:5]:
        sizes = frame[col].value_counts()
        t = test_size
        multi = sizes[sizes >= 2]
        straddle = float(sum(k * (1 - t ** k - (1 - t) ** k) for k in multi)) / n
        findings.append(finding(
            "group_leakage", "medium" if straddle >= 0.2 else "low", "potential", f"'{col}' defines groups that a random split would separate",
            features=[col], evidence={"groups_in_sample": int(sizes.size), "rows_in_multi_row_groups_percent": round(100 * float(multi.sum()) / n, 2),
                                      "expected_rows_in_groups_split_across_train_and_test_percent": round(100 * straddle, 2), "assumed_test_size": t},
            evidence_text=f"{sizes.size:,} groups in the sample; about {100 * straddle:.1f}% of rows are expected to belong to a group that appears in both train and test under a random {t:.0%} split.",
            risk="Rows of the same entity are correlated; a model can recognise the entity instead of generalising to new ones.",
            action="If new entities appear at prediction time, evaluate with a group-aware split. DataLens' split is random, so use this as a risk signal.",
            limitations="Sample-based group sizes underestimate full-data group sizes. Whether the column is a real grouping entity is for you to decide."))
    if not group_cols:
        findings.append(finding("group_leakage", "info", "not_assessed", "Group leakage not assessed",
                                evidence_text="No group-like column found (looked for names containing: " + ", ".join(sorted(GROUP_TOKENS)) + ").",
                                action="If rows share an entity (user, device, session), add that column or assess grouping manually.",
                                limitations="Group structure cannot be inferred without such metadata."))

    # 5) temporal leakage
    time_cols = []
    for col in frame.columns:
        if col in (ROW_ID, target):
            continue
        by_name = bool(_name_tokens(col) & TIME_TOKENS)
        parsed = _looks_like_time(frame[col])
        if parsed or (by_name and pd.api.types.is_numeric_dtype(frame[col])):
            time_cols.append((col, parsed))
    for col, parsed in time_cols[:3]:
        findings.append(finding(
            "temporal_leakage", "medium", "potential", f"'{col}' is a time column but DataLens splits rows randomly", features=[col],
            evidence={"range": parsed, "split_method": "random, seeded per class"},
            evidence_text=(f"Values span {parsed['min']} → {parsed['max']}. " if parsed else "Column name indicates time. ") +
                          "A random split mixes past and future rows between train and test.",
            risk="Training on later data and testing on earlier data overstates performance for time-dependent problems.",
            action="If the model will predict future rows, split by time outside DataLens or treat these scores as optimistic.",
            limitations="Whether the problem is time-dependent is a modelling decision DataLens cannot infer."))
    if not time_cols:
        findings.append(finding("temporal_leakage", "info", "not_assessed", "Temporal leakage not assessed",
                                evidence_text="No time/date column detected, so time ordering could not be examined.",
                                limitations="Temporal leakage requires a timestamp or ordering column."))
    findings.append(finding("preprocessing_leakage", "info", "not_assessed", "Preprocessing leakage not assessed at dataset level",
                            evidence_text="This is judged from a preparation run's execution record. Prepare the dataset to assess it."))
    return {"kind": "leakage", "scope": "source", "sample": info, "findings": findings, "summary": summarize(findings), "target": target,
            "target_kind": kind}


# --------------------------------------------------------------------------------------------------- run level
def _near_duplicates(train_csv: Path, test_csv: Path, target: str | None, threshold: float, seed: int) -> dict[str, Any]:
    tr = pd.read_csv(train_csv, nrows=200_000)
    te = pd.read_csv(test_csv, nrows=50_000)
    cols = [c for c in tr.columns if c != target and c in te.columns and pd.api.types.is_numeric_dtype(tr[c])]
    cols = [c for c in cols if tr[c].std() > 0][:NEAR_MAX_COLS]
    if not cols or len(tr) < 10 or len(te) < 1:
        return {"assessed": False, "reason": "no usable numeric columns or rows in the exports"}
    rng = np.random.default_rng(seed)
    tr_s = tr.iloc[rng.choice(len(tr), min(len(tr), NEAR_ROWS_TRAIN), replace=False)]
    te_s = te.iloc[rng.choice(len(te), min(len(te), NEAR_ROWS_TEST), replace=False)]
    mu, sd = tr_s[cols].mean(), tr_s[cols].std().replace(0, 1)
    A = ((tr_s[cols] - mu) / sd).to_numpy()
    B = ((te_s[cols] - mu) / sd).to_numpy()
    dist, _ = NearestNeighbors(n_neighbors=1, algorithm="brute").fit(A).kneighbors(B)
    rms = dist[:, 0] / np.sqrt(len(cols))
    exact = int((rms < 1e-9).sum())
    near = int(((rms >= 1e-9) & (rms <= threshold)).sum())
    return {"assessed": True, "threshold_rms": threshold, "columns_used": len(cols), "test_rows_checked": int(len(B)),
            "train_rows_searched": int(len(A)), "exact_in_sample": exact, "near_not_exact": near,
            "near_percent": round(100 * near / len(B), 3),
            "distance": "Euclidean on train-standardised numeric columns divided by √(columns): RMS per-feature difference in train std units",
            "histogram": _hist(rms)}


def _hist(rms: np.ndarray) -> dict[str, Any]:
    cap = float(np.percentile(rms, 95)) if len(rms) > 20 else float(rms.max())
    cap = cap if cap > 0 else 1.0
    edges = np.linspace(0, cap, 21)
    counts, _ = np.histogram(np.clip(rms, 0, cap), bins=edges)
    return {"edges": [round(float(e), 5) for e in edges], "counts": counts.tolist(), "clipped_at": "95th percentile"}


def run_leakage(run_dir: Path, manifest: dict[str, Any], threshold: float = 0.05, seed: int = 42) -> dict[str, Any]:
    if not 0 < threshold <= 1:
        raise ValueError("near-duplicate threshold must be in (0, 1]")
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8")) if (run_dir / "config.json").is_file() else {}
    target = manifest.get("target_column")
    findings: list[dict[str, Any]] = []
    ov = manifest.get("train_test_overlap") or {}
    test_rows = int(ov.get("test_rows") or 0)
    if ov and test_rows:
        shared, pct = int(ov.get("test_rows_also_in_train") or 0), float(ov.get("percent_of_test") or 0)
        if shared:
            sev = "critical" if pct >= 10 else "high" if pct >= 1 else "medium"
            findings.append(finding(
                "exact_overlap", sev, "confirmed", "Exact records shared between training and test",
                evidence={**ov, "percent_of_test": pct}, evidence_text=f"{shared:,} of {test_rows:,} test rows ({pct}%) are exact copies of training rows (matched by 64-bit row hash over all columns).",
                risk="The model is evaluated on rows it was trained on, so test metrics are optimistic.",
                action="Re-prepare with duplicate policy 'Remove global exact repeats' (drop_exact), then re-check.",
                limitations="Hash-based match over the exported source columns; 64-bit hashes make false matches negligible but not impossible."))
        else:
            findings.append(finding("exact_overlap", "info", "clear", "No exact train/test overlap", evidence=ov,
                                    evidence_text=f"0 of {test_rows:,} test rows appear in the training set."))
    else:
        findings.append(finding("exact_overlap", "info", "not_assessed", "Exact overlap not assessed", evidence_text="The run has no overlap record (no test rows or an older run)."))

    train_csv, test_csv = run_dir / "train.csv", run_dir / "test.csv"
    near: dict[str, Any] = {"assessed": False, "reason": "train.csv or test.csv missing"}
    if train_csv.is_file() and test_csv.is_file():
        near = _near_duplicates(train_csv, test_csv, target, threshold, seed)
    if near.get("assessed"):
        pct = near["near_percent"]
        if near["near_not_exact"]:
            findings.append(finding(
                "near_duplicates", "high" if pct >= 10 else "medium" if pct >= 1 else "low", "potential",
                f"Test rows nearly identical to training rows (≤ {threshold} RMS)", evidence=near,
                evidence_text=f"{near['near_not_exact']:,} of {near['test_rows_checked']:,} checked test rows ({pct}%) have a non-identical training row within RMS distance {threshold}.",
                risk="Near-copies behave like leakage: the model can answer from a close memorised neighbour.",
                action="Review these rows. Consider a stricter duplicate policy or grouping similar rows before splitting.",
                limitations=f"Threshold is explicit ({threshold}); searched {near['train_rows_searched']:,} training rows, so counts are a lower bound. Distance is computed on exported numeric columns."))
        else:
            findings.append(finding("near_duplicates", "info", "clear", "No near-duplicates found", evidence=near,
                                    evidence_text=f"No checked test row has a non-identical training neighbour within RMS {threshold}."))
    else:
        findings.append(finding("near_duplicates", "info", "not_assessed", "Near-duplicates not assessed", evidence_text=near.get("reason", "")))

    scope = config.get("fit_scope")
    if scope:
        findings.append(finding(
            "preprocessing_leakage", "info", "clear", "Preprocessing was fitted on training rows only",
            evidence={"fit_scope": scope, "fit_rows": config.get("fit_rows"), "feature_selection": config.get("feature_selection"), "scaler": config.get("scaler")},
            evidence_text=f"The run's execution record states: {scope} (fit on {config.get('fit_rows'):,} rows). Imputer, scaler, encoder and selector were fitted there and only applied to test.",
            limitations="Based on the run's recorded fit scope. It does not cover transformations applied before upload."))
    else:
        findings.append(finding("preprocessing_leakage", "info", "not_assessed", "Preprocessing leakage not assessed",
                                evidence_text="This run's config.json does not record the fit scope (older run). Re-prepare to record it."))
    return {"kind": "leakage", "scope": "run", "run_id": manifest.get("id"), "dataset_id": manifest.get("dataset_id"), "findings": findings,
            "summary": summarize(findings), "near_duplicate_threshold": threshold, "target": target}
