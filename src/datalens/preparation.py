"""Phase 3 orchestration: load -> canonicalize labels -> duplicates -> split -> features -> preprocess.

Order matters for leakage safety:
 1. Dataset-level cleaning that does not learn from labels' relation to features (label spelling,
    exact-duplicate removal) happens BEFORE splitting so duplicates cannot straddle train/test.
 2. The split uses indices only.
 3. Everything LEARNED (zero-variance screen, correlation, probes, importance, imputation values,
    scaler statistics, selection) uses TRAINING rows only.
 4. The test rows are only transformed, in chunks, and never influence a decision.
Each strategy (random, day_aware) is a separate run with its own metadata; scores from the two
strategies measure different things and must not be pooled.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from datalens.evaluation.imbalance import imbalance_report
from datalens.experiments.metadata import build_run_metadata, to_jsonable, write_run_metadata
from datalens.features import (
    ExclusionLog, build_feature_metadata, build_selector, correlation_analysis, low_variance_report,
    single_feature_probe, train_only_importance,
)
from datalens.ingestion.loader import load_dataset
from datalens.preprocessing.duplicates import apply_duplicate_policy, cross_file_duplicates
from datalens.preprocessing.fitting import chunked_handling_report, fit_preprocessor, transformed_summary
from datalens.preprocessing.labels import canonicalize_labels
from datalens.preprocessing.pipeline import build_preprocessor, split_columns, validate_preprocessing_config
from datalens.preprocessing.splitting import (
    day_aware_split, leave_one_group_out_splits, stratified_random_split, validate_split,
)
from datalens.profiling import profile_dataframe
from datalens.quality import assess_quality
from datalens.reporting import write_quality_outputs
from datalens.reporting.preparation_report import build_preparation_markdown
from datalens.resources import estimate_matrix_gb, hardware_summary

logger = logging.getLogger(__name__)
STRATEGIES = ("random", "day_aware")
BENIGN = "BENIGN"
RAW_LABEL_COLUMN = "label_raw"


def _dump(obj: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(obj), indent=2), encoding="utf-8")
    return path


def validate_day_groups(sources: list[str], groups: dict[str, list[str]]) -> None:
    """Fail fast: every group must match a file and every file must belong to a group."""
    files = sorted(set(sources))
    covered: set[str] = set()
    for name, pats in groups.items():
        hit = {f for f in files if any(p.lower() in f.lower() for p in pats)}
        if not hit:
            raise ValueError(f"day group '{name}' {pats} matches no file. Files: {files}")
        covered |= hit
    if set(files) - covered:
        raise ValueError(f"Files not covered by any day group: {sorted(set(files) - covered)}")


def check_no_missing_labels(labels: pd.Series) -> None:
    bad = labels.astype(str).str.strip().str.lower().isin(["nan", "", "none", "<na>"])
    if bad.any():
        raise ValueError(f"{int(bad.sum())} rows have a missing label; resolve them explicitly (rows are never dropped silently)")


def _make_split(strategy: str, df: pd.DataFrame, cfg: dict, label: str, source: str, seed: int):
    sp = cfg["split"]
    if strategy == "random":
        r = sp["random"]
        split = stratified_random_split(df[label], sp["test_size"], seed, r["rare_class_policy"],
                                        r["min_class_count"], r["min_test_per_class"])
        return split, None
    da = sp["day_aware"]
    held = list(da["primary_holdout"])
    unknown = [h for h in held if h not in da["groups"]]
    if unknown:
        raise ValueError(f"primary_holdout {unknown} not among groups {list(da['groups'])}")
    test_pats = [p for h in held for p in da["groups"][h]]
    train_pats = [p for name, ps in da["groups"].items() if name not in held for p in ps]
    split = day_aware_split(df[source], df[label], train_days=train_pats, test_days=test_pats)
    coverage = []
    for held_out, s in leave_one_group_out_splits(df[source], df[label], da["groups"]):
        m = s.metadata
        coverage.append({"held_out": held_out, "n_train": m["n_train"], "n_test": m["n_test"],
                         "classes_absent_from_train": m["classes_absent_from_train"],
                         "test_rows_in_classes_absent_from_train": m["test_rows_in_classes_absent_from_train"],
                         "classes_absent_from_test": m["classes_absent_from_test"]})
    split.metadata["leave_one_day_out_coverage"] = coverage
    return split, coverage


def _analyze_features(X_train: pd.DataFrame, y_train: pd.Series, numeric: list[str], cfg: dict, seed: int) -> dict[str, Any]:
    """Training-only feature evidence. Nothing here removes a feature (the caller logs exclusions)."""
    fc = cfg["features"]
    out: dict[str, Any] = {}
    lv = low_variance_report(X_train[numeric], fc["variance_threshold"], cfg["profiling"]["near_constant_threshold"])
    out["low_variance"] = lv
    keep = [c for c in numeric if not lv.loc[c, "suggested_action"].startswith("drop")]
    out["correlation"] = correlation_analysis(X_train[keep], fc["correlation_threshold"], fc["correlation_method"],
                                              fc["analysis_max_rows"], seed) if len(keep) > 1 else None
    labels = y_train.astype(str).to_numpy()
    pr = fc["probe"]
    if pr["enabled"]:
        y_bin = np.where(labels == BENIGN, "benign", "attack")
        counts = pd.Series(y_bin).value_counts()
        if len(counts) == 2 and counts.min() >= pr["cv"]:
            out["single_feature_probe"] = single_feature_probe(X_train[keep], y_bin, pr["max_rows"], pr["cv"], pr["max_depth"], seed, pr["flag_auc"])
        else:
            out["single_feature_probe"] = None
            out["single_feature_probe_skipped"] = "training data lacks both benign and attack rows (>= cv each)"
    im = fc["importance"]
    if im["enabled"] and len(set(labels)) > 1:
        out["importance"] = train_only_importance(X_train[keep], labels, im["n_estimators"], im["max_depth"], im["max_rows"], seed)
    return out


def prepare_dataset(
    cfg: dict[str, Any], raw_dir: str | Path, out_dir: str | Path, experiments_dir: str | Path,
    strategies: tuple[str, ...] = STRATEGIES, sample_fraction: float | None = None, run_quality: bool = True,
    command: str = "python scripts/prepare_dataset.py",
) -> dict[str, Any]:
    """Run Phase 3 end to end and write every artifact. Returns a summary with paths and metadata."""
    bad = [s for s in strategies if s not in STRATEGIES]
    if bad:
        raise ValueError(f"Unknown strategies {bad}; choose from {STRATEGIES}")
    out_root, timings = Path(out_dir) / "phase3", {}
    seed = int(cfg["project"]["random_seed"])
    ing = cfg["ingestion"]
    label, source = ing["label_column"], ing["source_column"]
    hw = hardware_summary()
    eff_pre = validate_preprocessing_config(cfg["preprocessing"])

    # ---- 1. load -------------------------------------------------------------------------------
    t = time.perf_counter()
    df, dmeta = load_dataset(raw_dir, ing["file_glob"], label, source, ing["chunk_size"], sample_fraction, seed,
                             tuple([ing["encoding"], *ing["fallback_encodings"]]), ing["compute_hash"])
    timings["load"] = round(time.perf_counter() - t, 2)
    n_feat = df.shape[1] - 2
    plan = {"rows": len(df), "feature_matrix_gb_one_copy": estimate_matrix_gb(len(df), n_feat),
            "available_ram_gb": hw["available_ram_gb"],
            "assumption": "pipelines hold several concurrent copies of the training matrix; measure before scaling up"}
    dmeta["resource_plan"] = plan
    logger.info("Loaded %s rows (full dataset: %s). One feature-matrix copy ~ %s GB; available RAM %s GB",
                f"{len(df):,}", dmeta["is_full_dataset"], plan["feature_matrix_gb_one_copy"], hw["available_ram_gb"])
    validate_day_groups(list(df[source].unique()), cfg["split"]["day_aware"]["groups"]) if "day_aware" in strategies else None
    check_no_missing_labels(df[label])

    # ---- 2. labels (traceable) ---------------------------------------------------------------------
    t = time.perf_counter()
    label_report = canonicalize_labels(df, label, RAW_LABEL_COLUMN)
    timings["labels"] = round(time.perf_counter() - t, 2)
    numeric_all, categorical_all = split_columns(df, exclude=[label, RAW_LABEL_COLUMN, source])
    feature_cols = numeric_all + categorical_all
    shared = {"label_canonicalization": _dump(label_report, out_root / "label_canonicalization.json")}

    # ---- 3. quality findings (before dedup, after label repair) -------------------------------------------
    quality_findings = None
    if run_quality:
        t = time.perf_counter()
        prof = profile_dataframe(df, label, exclude_columns=[RAW_LABEL_COLUMN], source_column=source,
                                 iqr_factor=cfg["profiling"]["outlier_iqr_factor"])
        quality_findings = assess_quality(prof, cfg["quality"], cfg["profiling"], dmeta)
        shared["quality"] = write_quality_outputs(prof, quality_findings, dmeta, out_root / "quality")["report"]
        timings["quality"] = round(time.perf_counter() - t, 2)

    # ---- 4. duplicates -------------------------------------------------------------------------------------------
    t = time.perf_counter()
    cross = cross_file_duplicates(df, feature_cols, label, source)
    dpol = cfg["preprocessing"]["duplicates"]
    df, dup_report = apply_duplicate_policy(df, feature_cols, label, dpol["policy"], dpol["max_class_loss_pct"])
    dup_report["cross_file"] = cross
    timings["duplicates"] = round(time.perf_counter() - t, 2)
    shared["duplicates"] = _dump(dup_report, out_root / "duplicates.json")

    # ---- 5. imbalance (of the dataset that will be split) -----------------------------------------------------------------
    ic = cfg["imbalance"]
    imb = imbalance_report(df[label], cfg["split"]["test_size"], cfg["split"]["cv_folds"], ic["minority_pct"],
                           ic["min_test_per_class"], ic["low_support_test"], ic["smote_k"])
    shared["class_imbalance"] = _dump(imb, out_root / "class_imbalance.json")
    shared["dataset"] = _dump(dmeta, out_root / "dataset_metadata.json")

    # ---- 6. each strategy ---------------------------------------------------------------------------------------------------
    results: dict[str, Any] = {}
    for strategy in strategies:
        st, sdir = dict(timings), out_root / strategy
        t = time.perf_counter()
        split, _ = _make_split(strategy, df, cfg, label, source, seed)
        validate_split(split, len(df))
        st["split"] = round(time.perf_counter() - t, 2)
        meta_path = _dump(split.metadata, sdir / "split_metadata.json")

        X_train = df[feature_cols].iloc[split.train_idx]
        X_test = df[feature_cols].iloc[split.test_idx]
        y_train = df[label].iloc[split.train_idx]

        # training-only feature evidence and logged exclusions
        t = time.perf_counter()
        num = [c for c in numeric_all if c in X_train.columns]
        ev = _analyze_features(X_train, y_train, num, cfg, seed)
        excl = ExclusionLog()
        if cfg["features"]["exclude_zero_variance"]:
            lv = ev["low_variance"]
            for f in lv.index[lv["suggested_action"].str.startswith("drop")]:
                excl.add(f, "zero variance on training rows (constant: nothing to learn)",
                         {"n_unique_finite": int(lv.loc[f, "n_unique"]), "variance": float(lv.loc[f, "variance"]),
                          "computed_on": "training rows only"})
        modeling = excl.apply(feature_cols)
        X_train, X_test = X_train[modeling], X_test[modeling]
        num_m, cat_m = [c for c in numeric_all if c in modeling], [c for c in categorical_all if c in modeling]
        st["feature_analysis"] = round(time.perf_counter() - t, 2)

        # preprocessing fitted on TRAINING rows only (bounded), transformed in chunks
        t = time.perf_counter()
        pre = build_preprocessor(num_m, cat_m, cfg["preprocessing"])
        fit_record = fit_preprocessor(pre, X_train, cfg["preprocessing"]["fit_max_rows"], seed)
        chunk = cfg["preprocessing"]["transform_chunk_size"]
        handling = chunked_handling_report(pre, X_train, X_test, chunk)
        tsum = {"train": transformed_summary(pre, X_train, chunk), "test": transformed_summary(pre, X_test, chunk)}
        for part, s in tsum.items():
            if s["nan_cells"] or s["inf_cells"]:
                raise RuntimeError(f"Transformed {part} data still has NaN/inf cells: {s}")
        st["preprocessing"] = round(time.perf_counter() - t, 2)

        # optional selection, fitted on a bounded TRAINING sample
        selected, sel_info = None, {"method": cfg["features"]["selection"]["method"]}
        if sel_info["method"] != "none":
            n_sel = min(len(X_train), cfg["features"]["importance"]["max_rows"])
            idx = np.sort(np.random.default_rng(seed).choice(len(X_train), size=n_sel, replace=False))
            Xs = pre.transform(X_train.iloc[idx])
            selector = build_selector(sel_info["method"], cfg["features"]["selection"]["k"], seed=seed)
            selector.fit(Xs, y_train.astype(str).to_numpy()[idx])
            names = np.asarray(pre.get_feature_names_out(), dtype=object)
            selected = list(names[selector.get_support()])
            sel_info.update(k=cfg["features"]["selection"]["k"], fit_rows=int(n_sel), n_selected=len(selected), fit_on="training rows only")

        fmeta = build_feature_metadata(feature_cols, excl, pre, selected, {"preprocessing": eff_pre, "selection": sel_info})
        feature_report = {
            "metadata": fmeta, "selection": sel_info,
            "low_variance": ev["low_variance"].reset_index().to_dict("records"),
            "correlation": ev["correlation"],
            "single_feature_probe": None if ev.get("single_feature_probe") is None else ev["single_feature_probe"].reset_index().to_dict("records"),
            "single_feature_probe_skipped": ev.get("single_feature_probe_skipped"),
            "importance_train_only": None if "importance" not in ev else ev["importance"].to_dict(),
            "computed_on": f"training rows only (n={len(X_train):,})",
        }
        paths = {
            "split": meta_path,
            "handling": _dump(handling, sdir / "handling_report.json"),
            "features": _dump(feature_report, sdir / "feature_report.json"),
            "preprocessing_config": _dump({"effective": eff_pre, "fit": fit_record, "duplicates": dpol}, sdir / "preprocessing_config.json"),
        }
        run_meta = build_run_metadata(strategy, cfg, dmeta, label_report, dup_report, split.metadata, fit_record, fmeta,
                                      handling, imb, tsum, hw, st, eff_pre, command)
        paths["run_metadata"] = write_run_metadata(run_meta, experiments_dir)
        paths["summary"] = sdir / "preparation_summary.md"
        paths["summary"].write_text(build_preparation_markdown(run_meta, feature_report, imb, label_report, dup_report), encoding="utf-8")
        results[strategy] = {"paths": paths, "run_id": run_meta["run_id"], "split": split.metadata, "n_train": len(X_train), "n_test": len(X_test)}
        del X_train, X_test, pre
    return {"dataset_meta": dmeta, "label_report": label_report, "duplicate_report": dup_report, "imbalance": imb,
            "quality_findings": quality_findings, "shared_paths": shared, "strategies": results, "timings": timings}
