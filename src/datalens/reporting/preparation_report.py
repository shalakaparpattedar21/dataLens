"""Human-readable Phase 3 summary for one run. Measured facts and interpretation are kept apart."""

from __future__ import annotations

from typing import Any

import pandas as pd

from datalens.reporting.investigation_report import df_to_md


def _dist_table(train: dict, test: dict) -> str:
    classes = sorted(set(train["counts"]) | set(test["counts"]), key=lambda c: -(train["counts"].get(c, 0) + test["counts"].get(c, 0)))
    rows = [{"class": c, "train": train["counts"].get(c, 0), "test": test["counts"].get(c, 0)} for c in classes]
    return df_to_md(pd.DataFrame(rows), index=False)


def build_preparation_markdown(run: dict[str, Any], feat: dict[str, Any], imb: dict[str, Any],
                               labels: dict[str, Any], dup: dict[str, Any]) -> str:
    ds, sp, pre = run["dataset"], run["split"]["full_metadata"], run["preprocessing"]
    L = [f"# Phase 3 preparation summary: {run['strategy']} split", "",
         f"Run `{run['run_id']}` | created {run['created_utc']} | git `{run['code']['git_commit']}` | "
         f"seed {ds['random_seed']}", "",
         "Sections titled *(measured)* are computed from the data; *(interpretation)* is explanation, not measurement.", "",
         "## Dataset (measured)", "",
         f"- Source files ({len(ds['source_files'])}): {', '.join(ds['source_files'])}",
         f"- Fingerprint `{ds['fingerprint']}` (content hash included: {ds['fingerprint_includes_content_hash']})",
         f"- **Full dataset: {ds['is_full_dataset']}**" + ("" if ds["is_full_dataset"] else f" -- RANDOM SAMPLE, fraction {ds['sample_fraction']}; rare classes lose rows disproportionately"),
         f"- Rows in files: {ds['rows_in_files']:,}; loaded: {ds['rows_loaded']:,}; after duplicate policy: {ds['rows_after_cleaning']:,}", ""]

    L += ["## Label canonicalization (measured)", "",
          f"- Raw labels: {labels['n_raw_labels']}; canonical labels: {labels['n_clean_labels']}",
          f"- Artifact characters removed: {labels['artifact_chars_removed']}", ""]
    if labels["changed_labels"]:
        L += [df_to_md(pd.DataFrame(labels["changed_labels"]), index=False), ""]
    L += [f"- Merged groups (identical after artifact removal): {labels['merged_groups'] or 'none'}",
          f"- Similar but deliberately NOT merged: {labels['similar_not_merged'] or 'none'}",
          "- Original labels are preserved in column `label_raw`.", ""]

    L += ["## Duplicate handling (measured)", "",
          f"- Policy: `{dup['policy']}`; exact duplicate rows found: {dup['exact_duplicate_rows']:,}; "
          f"rows in label-conflicting vectors: {dup['label_conflict_rows']:,}; rows removed: {dup['rows_removed']:,}",
          f"- Vectors present in more than one file: {dup['cross_file']['n_groups_spanning_files']:,} "
          f"(label disagreement in {dup['cross_file']['n_spanning_groups_with_label_disagreement']:,})",
          f"- Removed by class: {dup['removed_by_class'] or 'none'}",
          f"- Classes lost entirely: {dup['classes_lost_entirely'] or 'none'}"]
    L += [f"- WARNING: {w}" for w in dup["warnings"]]
    L += ["", "*(interpretation)* Exact duplicates split across train and test inflate test scores, so they are removed "
          "before splitting. Conflicting vectors are kept by default: they are real label noise that sets a floor on error.", ""]

    L += ["## Class imbalance (measured)", "",
          f"- Majority `{imb['majority_class']}` = {imb['majority_percent']}%; overall ratio {imb['overall_imbalance_ratio']}:1",
          f"- Minority classes (< {imb['assumptions']['minority_pct']}% of rows): {imb['minority_classes']}",
          f"- Unstratifiable: {imb['classes_unstratifiable']}; unusable for {imb['assumptions']['cv_folds']}-fold CV: {imb['classes_unusable_for_kfold']}",
          f"- Unreliable expected test metrics (< {imb['assumptions']['min_test_per_class']} test rows): {imb['classes_with_unreliable_test_metrics']}",
          f"- SMOTE infeasible in training (<= k samples): {imb['smote']['infeasible_classes']}", "",
          df_to_md(pd.DataFrame(imb["per_class"]).T[["count", "percent", "ratio_to_majority", "expected_test_count"]]), ""]

    L += [f"## Split: {sp['strategy']} (measured)", "", f"- Train rows: {sp['n_train']:,}; test rows: {sp['n_test']:,}"]
    if sp["strategy"] == "stratified_random":
        L += [f"- Classes forced to train (cannot be stratified): {sp['classes_forced_to_train'] or 'none'}",
              f"- Classes absent from test: {sp['classes_absent_from_test'] or 'none'}",
              f"- Classes with unreliable test metrics: {sp['classes_with_unreliable_test_metrics'] or 'none'}"]
    else:
        L += [f"- Train files: {sp['train_files']}", f"- Test files: {sp['test_files']}",
              f"- **Classes in test but absent from training: {sp['classes_absent_from_train'] or 'none'}** "
              f"({sp['test_rows_in_classes_absent_from_train']:,} test rows)",
              f"- Classes absent from test: {sp['classes_absent_from_test'] or 'none'}"]
    L += ["", _dist_table(sp["train_distribution"], sp["test_distribution"]), ""]
    if sp.get("leave_one_day_out_coverage"):
        L += ["### Coverage of every leave-one-day-out option (measured)", "",
              df_to_md(pd.DataFrame(sp["leave_one_day_out_coverage"]), index=False), ""]
    L += [f"- *(interpretation)* {n}" for n in sp["notes"]] + [""]

    h = run["results"]["handling"]
    L += ["## Preprocessing", "",
          f"- Infinite values: `{pre['inf_handling']}` (inf treated as undefined, never silently 0)",
          f"- Imputation: {pre['imputation']}; missing-indicator columns: {pre['missing_indicator']}; scaling: `{pre['scaling']}`; "
          f"encoding: {pre['encoding']}",
          f"- Fitted on **{pre['fit']['fit_rows_used']:,} of {pre['fit']['train_rows']:,} training rows** "
          f"(subsample: {pre['fit']['fit_on_subsample']}); test rows never used for fitting",
          f"- Train: {h['train']['positive_inf_cells']:,} +inf, {h['train']['negative_inf_cells']:,} -inf, {h['train']['nan_cells']:,} NaN cells; "
          f"Test: {h['test']['positive_inf_cells']:,} +inf, {h['test']['negative_inf_cells']:,} -inf, {h['test']['nan_cells']:,} NaN cells",
          f"- Train inf by column: {h['train']['inf_by_column'] or 'none'}; NaN by column: {h['train']['nan_by_column'] or 'none'}",
          f"- Train fill values for affected columns: {h['train_fill_values_for_affected_columns'] or 'none'}",
          f"- Transformed output NaN/inf cells (train/test): {run['results']['transformed_summary']['train']['nan_cells']}/"
          f"{run['results']['transformed_summary']['test']['nan_cells']} (must be 0)", ""]

    fm = feat["metadata"]
    L += ["## Features (computed on training rows only)", "",
          f"- Original: {fm['n_original']}; excluded: {len(fm['excluded_features'])}; modeling: {fm['n_modeling']}; "
          f"transformed columns: {len(fm.get('transformed_features', []))}"]
    for f, e in fm["excluded_features"].items():
        L.append(f"- EXCLUDED `{f}`: {e['reason']}; evidence {e['evidence']}")
    review = [r["feature"] for r in feat["low_variance"] if str(r["suggested_action"]).startswith("review")]
    L += [f"- Low-variance / near-constant features to REVIEW (kept): {review or 'none'}"]
    corr = feat.get("correlation")
    if corr:
        L += [f"- Correlated pairs |r| >= {corr['threshold']} ({corr['method']}, {corr['rows_used']:,} rows): {corr['n_pairs_above_threshold']}; "
              f"suggested drops (NOT applied): {[d['dropped'] for d in corr['suggested_drops']][:15]}"]
    probe = feat.get("single_feature_probe")
    if probe:
        flagged = [r["feature"] for r in probe if r.get("flag_review")]
        top = sorted(probe, key=lambda r: -(r["roc_auc"] if r["roc_auc"] == r["roc_auc"] else r["balanced_accuracy"]))[:5]
        L += [f"- Single-feature shortcut probe (attack vs benign, depth-limited tree): flagged for review {flagged or 'none'}; "
              f"strongest: {[(r['feature'], round(r['roc_auc'], 4)) for r in top]}"]
    elif feat.get("single_feature_probe_skipped"):
        L += [f"- Single-feature probe skipped: {feat['single_feature_probe_skipped']}"]
    imp = feat.get("importance_train_only")
    if imp:
        L += [f"- Top train-only impurity importances: {[(k, round(v, 4)) for k, v in list(imp.items())[:8]]}"]
    L += [f"- Selection: {feat['selection']}", "",
          "*(interpretation)* Flags ask for human review and with/without comparisons in Phase 4; no feature was removed except "
          "those listed under EXCLUDED. A strong single feature may be a genuine signal or a collection artifact.", ""]

    L += ["## Limitations", ""]
    if sp["strategy"] == "stratified_random":
        L += ["- Rows from one capture are correlated, so random-split scores are optimistic for unseen traffic. Do not pool with day-aware scores."]
    else:
        L += ["- Attack families are mostly confined to specific days: a held-out day removes whole classes from training, so multiclass scores for them are undefined; use binary attack-vs-benign or report them separately.",
              "- A day-aware score is NOT a universal measure of real-world generalization."]
    L += ["- Offline benchmark results do not demonstrate production intrusion-detection performance."]
    if not ds["is_full_dataset"]:
        L += ["- THIS RUN USED A SAMPLE: do not report these numbers as full-dataset results."]
    return "\n".join(L) + "\n"
