"""Preprocessing recommendation engine.

Each recommendation is derived from measured findings and states: what was detected (evidence), why it matters,
the suggested action, expected benefit, trade-offs, and whether DataLens can apply it to the Prepare form.
``apply`` is a partial Prepare configuration (only fields DataLens really supports); ``choices`` lists the
valid alternatives so the user can customise before applying. Recommendations never change settings by
themselves: the UI applies only what the user accepts.
"""
from __future__ import annotations

from typing import Any

SUPPORTED = {
    "sample_fraction": ["0.1", "0.25", "1"], "duplicate_policy": ["keep", "drop_within_file", "drop_exact"],
    "numeric_imputer": ["median", "mean", "most_frequent"], "encoding": ["onehot", "ordinal"],
    "scaler": ["robust", "standard", "minmax", "none"], "feature_selection": ["none", "variance", "kbest_f"],
}


def rec(rid: str, category: str, priority: str, finding: str, why: str, action: str, benefit: str, tradeoff: str,
        evidence: dict | None = None, apply: dict | None = None, manual: str | None = None) -> dict[str, Any]:
    choices = {k: SUPPORTED[k] for k in (apply or {})}
    return {"id": rid, "category": category, "priority": priority, "finding": finding, "why": why, "suggested_action": action,
            "expected_benefit": benefit, "tradeoffs": tradeoff, "evidence": evidence or {},
            "can_apply": bool(apply), "apply": apply or None, "choices": choices, "manual_step": manual}


def build_recommendations(profile: dict[str, Any] | None, distributions: dict[str, Any] | None, relationships: dict[str, Any] | None,
                          leakage_reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not profile:
        return {"kind": "recommendations", "items": [], "note": "Profile the dataset first."}
    items: list[dict[str, Any]] = []
    rows = int(profile.get("rows") or 0)
    dtypes = profile.get("dtypes") or []
    target = profile.get("label_column")

    # size
    if rows > 2_000_000:
        items.append(rec("sample", "scale", "low", f"Large dataset ({rows:,} rows)", "Preparation holds the training fit sample in memory and writes both splits.",
                         "Prepare a 10% sample first to check settings, then rerun on the full data.", "Fast iteration with the same pipeline.",
                         "A sample can drop rare classes and is not a full-data result.", {"rows": rows}, {"sample_fraction": "0.1"}))
    # missing
    miss = [c for c in dtypes if c.get("missing_cells")]
    if miss:
        heavy = [c["column"] for c in miss if rows and c["missing_cells"] / rows > 0.4]
        numeric_missing = [c["column"] for c in miss if c.get("dtype") and ("int" in c["dtype"] or "float" in c["dtype"])]
        cat_missing = [c["column"] for c in miss if c["column"] not in numeric_missing]
        if numeric_missing:
            items.append(rec("impute-numeric", "missing", "medium", f"{len(numeric_missing)} numeric column(s) have missing values",
                             "Models cannot consume NaN. Median imputation is robust to skewed distributions and outliers.",
                             "Use median imputation; DataLens also adds missing-indicator columns so missingness stays visible.",
                             "No missing feature values; informative missingness preserved.", "Imputed values shrink variance; mean is better for symmetric data, median for skewed.",
                             {"columns": numeric_missing[:15], "missing_cells": sum(c['missing_cells'] for c in miss)}, {"numeric_imputer": "median"}))
        if cat_missing:
            items.append(rec("impute-categorical", "missing", "low", f"{len(cat_missing)} categorical column(s) have missing values",
                             "DataLens imputes categorical gaps with the most frequent category (fitted on training rows).",
                             "No change needed; be aware the most frequent value is used, which can hide missingness.", "Complete categorical features.",
                             "An explicit 'missing' category would preserve the signal but is not configurable in DataLens yet.", {"columns": cat_missing[:15]}))
        if heavy:
            items.append(rec("heavy-missing", "missing", "high", f"{len(heavy)} column(s) are more than 40% missing", "Imputing so much data fabricates most of the column.",
                             "Review these columns and consider removing them from the CSV before preparing.", "Avoids features that are mostly imputed.",
                             "Dropping loses whatever signal the observed values carry.", {"columns": heavy[:15]}, manual="DataLens cannot yet exclude columns; remove them from the CSV before upload."))
    inf = int(profile.get("positive_infinity_cells") or 0) + int(profile.get("negative_infinity_cells") or 0)
    if inf:
        items.append(rec("infinite", "validity", "medium", f"{inf:,} infinite values", "Infinite values break scalers and models. DataLens converts them to missing, then imputes.",
                         "Keep the default handling and review the source of the infinities (often a division by zero in feature extraction).", "Finite, valid features.",
                         "Imputed values replace what may be a meaningful 'very large' signal.", {"infinite_cells": inf}))
    # duplicates and conflicts
    dup = profile.get("duplicates") or {}
    g, w = int(dup.get("exact_duplicate_rows_global") or 0), int(dup.get("exact_duplicate_rows_within_file") or 0)
    if g:
        overlap_hit = any(f["id"].startswith("exact_overlap") and f["status"] == "confirmed" for r in leakage_reports for f in r.get("findings", []))
        items.append(rec("duplicates", "duplicates", "high" if overlap_hit or g / max(1, rows) > 0.05 else "medium", f"{g:,} exact duplicate rows ({100 * g / max(1, rows):.2f}%)",
                         "Identical rows landing on both sides of the split inflate test scores." + (" A prepared run already shows confirmed train/test overlap." if overlap_hit else ""),
                         "Remove global exact repeats before splitting.", "Train and test no longer share exact copies.",
                         "Removes real repeated events if frequency matters for your problem (e.g. repeated identical flows).",
                         {"global": g, "within_file": w, "across_files_only": int(dup.get("exact_duplicates_only_across_files") or 0)}, {"duplicate_policy": "drop_exact"}))
    if int(dup.get("label_conflict_rows") or 0):
        items.append(rec("label-conflicts", "consistency", "high", f"{dup['label_conflict_rows']:,} rows conflict on the label",
                         "Identical features with different labels put a ceiling on any model and add noise to evaluation.",
                         "Inspect the conflicting groups; decide on a labelling rule or merge classes.", "Cleaner labels.", "Needs domain judgement; DataLens will not choose a label for you.",
                         {"rows": dup["label_conflict_rows"], "groups": dup.get("label_conflict_groups")}, manual="Resolve conflicting labels at the source."))
    # constants
    const = profile.get("constant_columns") or []
    if const:
        items.append(rec("constants", "features", "low", f"{len(const)} constant column(s)", "A column with one value has zero information.",
                         "Remove zero-variance features.", "Fewer useless features.", "None for truly constant columns; a column constant only in a sample may vary elsewhere.",
                         {"columns": const[:15]}, {"feature_selection": "variance"}))
    # outliers / scaling
    out = profile.get("outliers") or []
    heavy_out = [o for o in out if o.get("estimated_percent", 0) > 5]
    if heavy_out:
        items.append(rec("scaling", "distribution", "medium", f"{len(heavy_out)} column(s) have >5% IQR outliers", "Mean/std scaling is dragged by extreme values; quantile-based scaling is not.",
                         "Use robust scaling, and inspect these distributions before any transformation.", "Stable feature scales despite heavy tails.",
                         "Does not reduce the influence of outliers on tree-free linear models; outliers are kept, not removed.",
                         {"columns": [o["column"] for o in heavy_out[:10]], "max_percent": max(o["estimated_percent"] for o in heavy_out)}, {"scaler": "robust"}))
    # categorical cardinality
    if distributions:
        high = [c["column"] for c in distributions.get("categorical", []) if c.get("high_cardinality")]
        if high:
            items.append(rec("cardinality", "encoding", "medium", f"{len(high)} high-cardinality categorical column(s)", "One-hot encoding of many categories creates very wide, sparse outputs.",
                             "Prefer ordinal encoding (or exclude identifier-like columns); target/hashing encoders are not available in DataLens.", "Compact output.",
                             "Ordinal codes impose an arbitrary order that linear models may misread.", {"columns": high[:10]}, {"encoding": "ordinal"}))
    # imbalance / rare classes
    classes = profile.get("class_distribution") or []
    if len(classes) >= 2:
        tot = sum(c["count"] for c in classes)
        maj = classes[0]["count"] / max(1, tot)
        if maj >= 0.9:
            items.append(rec("imbalance", "target", "high", f"Strong class imbalance: '{classes[0]['label']}' is {100 * maj:.1f}% of rows", "Accuracy rewards predicting the majority class and hides weak minority performance.",
                             "Evaluate with PR-AUC and per-class recall; consider class weights or resampling in the training step.", "Honest minority-class evaluation.",
                             "DataLens does not resample or weight classes; do it when training so the test set keeps its natural distribution.",
                             {"majority_share": round(maj, 4), "classes": len(classes)}, manual="Apply class weights or resampling in the training code."))
        rare = [c for c in classes if c["count"] < 100 and c["label"] != "(missing)"]
        if rare:
            items.append(rec("rare-classes", "target", "medium", f"{len(rare)} class(es) have fewer than 100 rows", "With a sample or a random split, such classes can vanish from train or test.",
                             "Prepare the full dataset and check per-class coverage on the Prepare page.", "All rare classes are represented.", "Slower, larger exports.",
                             {"classes": [{"label": c["label"], "count": c["count"]} for c in rare[:10]]}, {"sample_fraction": "1"}))
    # correlation
    if relationships:
        groups = relationships.get("redundancy_groups") or []
        if groups:
            cand = sum(len(g["candidates"]) for g in groups)
            items.append(rec("redundancy", "features", "medium", f"{cand} potentially redundant feature(s) in {len(groups)} correlated group(s)", "Near-duplicate information inflates dimensionality and destabilises linear models.",
                             "Review the correlated pairs in Feature Intelligence and keep one column per group.", "Simpler, more stable models.",
                             "Correlated columns can still carry unique information; DataLens cannot yet drop selected columns automatically.",
                             {"groups": [{"keep": g["keep"], "candidates": g["candidates"][:5]} for g in groups[:5]]}, manual="Remove redundant columns from the CSV, or select features during modelling."))
        severe = [v for v in relationships.get("vif", []) if v["perfect_collinearity"] or (v["vif"] or 0) >= relationships.get("vif_thresholds", {}).get("severe", 10)]
        if severe:
            items.append(rec("multicollinearity", "features", "medium", f"{len(severe)} column(s) with severe multicollinearity (VIF ≥ 10)", "A column almost fully explained by others makes linear coefficients unreliable.",
                             "Inspect these columns; regularised or tree models tolerate it better.", "More stable coefficients.", "Trees and boosting are largely unaffected, so removal is optional there.",
                             {"columns": [v["column"] for v in severe[:10]]}))
        if relationships.get("target_kind") == "classification" and target:
            items.append(rec("selection", "features", "low", "Rank features by relevance to the target", "Mutual information and ANOVA F show which features carry target signal.",
                             "Optionally keep the top 30 features by ANOVA F (fitted on training rows only).", "Smaller, faster feature set.",
                             "ANOVA F sees only linear, per-feature separation; useful features that work in combination can be lost.", {}, {"feature_selection": "kbest_f"}))
    # leakage
    for report in leakage_reports:
        for f in report.get("findings", []):
            if f["status"] in ("confirmed", "potential") and f["severity"] in ("critical", "high", "medium") and f["type"] in ("identifier_like_column", "suspicious_feature_target", "target_name_proxy"):
                items.append(rec(f"leak-{f['id']}", "leakage", "high" if f["severity"] in ("critical", "high") else "medium", f["title"], f["risk"], f["recommended_action"],
                                 "Avoids an optimistic evaluation.", "Dropping a legitimately strong feature loses real signal.", {"features": f["features"], "evidence": f["evidence_text"]},
                                 manual="DataLens cannot yet exclude columns; remove it from the CSV before preparing."))
    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda r: (order.get(r["priority"], 3), r["id"]))
    return {"kind": "recommendations", "items": items, "count": len(items), "applicable": sum(1 for i in items if i["can_apply"]),
            "note": "Recommendations are derived from measured findings. Nothing is applied until you accept it and use it on the Prepare page."}
