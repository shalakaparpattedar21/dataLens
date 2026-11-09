from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from datalens.app_service import CHUNK_ROWS, DatasetStore, _encoding_for, utc_now
from datalens.preprocessing.fitting import fit_preprocessor
from datalens.preprocessing.pipeline import build_preprocessor, split_columns
from datalens.features.selection import build_selector


MIN_TEST_PER_CLASS = 5          # below this many test rows, per-class metrics are flagged unreliable
MANY_CLASSES = 50               # a target with more distinct values than this may be continuous
MAX_LISTED_WARNINGS = 25


def class_coverage(class_counts: dict[str, Counter]) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-class train/test counts with flags, and human-readable warnings.

    The split is random per class and chunk, so a rare class can end up entirely in one partition.
    That is reported, never hidden: a class absent from training cannot be learned, and a class
    absent from (or tiny in) the test set cannot be evaluated.
    """
    train, test = class_counts["train"], class_counts["test"]
    labels = sorted(set(train) | set(test), key=lambda k: (-(train.get(k, 0) + test.get(k, 0)), str(k)))
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for label in labels:
        tr, te = int(train.get(label, 0)), int(test.get(label, 0))
        flags = []
        if tr == 0:
            flags.append("absent_from_train")
            warnings.append(f"Class '{label}' ({te:,} rows) is absent from the training set, so a model cannot learn it.")
        if te == 0:
            flags.append("absent_from_test")
            warnings.append(f"Class '{label}' ({tr:,} rows) is absent from the test set, so its performance cannot be measured.")
        elif te < MIN_TEST_PER_CLASS:
            flags.append("low_test_support")
            warnings.append(f"Class '{label}' has only {te:,} test row(s): its per-class metrics are unreliable.")
        rows.append({"label": str(label), "train": tr, "test": te, "total": tr + te, "flags": flags})
    return rows, warnings


def _stable_seed(seed: int, file_index: int, chunk_index: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}|{file_index}|{chunk_index}|{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little")


def _selected_and_split(
    chunk: pd.DataFrame, fraction: float, test_size: float, seed: int, file_index: int, chunk_index: int,
    target: str | None,
) -> tuple[pd.DataFrame, np.ndarray]:
    if fraction < 1:
        chunk = chunk.sample(frac=fraction, random_state=seed + file_index * 100_003 + chunk_index)
    test = np.zeros(len(chunk), dtype=bool)
    if not len(chunk):
        return chunk, test
    labels = chunk[target].fillna("(missing)").astype(str) if target else pd.Series(["__all__"] * len(chunk), index=chunk.index)
    for label, index in labels.groupby(labels, sort=False).groups.items():
        loc = chunk.index.get_indexer(index)
        rng = np.random.default_rng(_stable_seed(seed, file_index, chunk_index, str(label)))
        test[loc] = rng.random(len(loc)) < test_size
    return chunk, test


class _DuplicateTracker:
    def __init__(self, path: Path, policy: str):
        self.conn = sqlite3.connect(path)
        self.policy = policy
        if policy in ("drop_exact", "drop_within_file"):
            self.conn.execute("CREATE TABLE seen(k TEXT PRIMARY KEY)")
            self.conn.execute("CREATE TEMP TABLE batch(k TEXT PRIMARY KEY, first_idx INTEGER)")

    def filter(self, frame: pd.DataFrame, target: str | None, source_name: str) -> tuple[pd.DataFrame, int]:
        if self.policy not in ("drop_exact", "drop_within_file") or frame.empty:
            return frame, 0
        signatures = pd.util.hash_pandas_object(frame, index=False).astype("uint64").to_numpy()
        keys = [f"{int(v):016x}" + (f"|{source_name}" if self.policy == "drop_within_file" else "") for v in signatures]
        first = pd.Series(keys).duplicated(keep="first").to_numpy()
        first_indices = np.flatnonzero(~first)
        self.conn.execute("DELETE FROM batch")
        self.conn.executemany("INSERT OR IGNORE INTO batch VALUES (?,?)", ((keys[i], int(i)) for i in first_indices))
        already = {int(row[0]) for row in self.conn.execute("SELECT b.first_idx FROM batch b JOIN seen s USING(k)")}
        self.conn.execute("INSERT OR IGNORE INTO seen SELECT k FROM batch")
        duplicate = first.copy()
        if already:
            duplicate[list(already)] = True
        self.conn.commit()
        return frame.iloc[np.flatnonzero(~duplicate)], int(duplicate.sum())

    def close(self) -> None:
        self.conn.close()


def _iter_chunks(files: list[Path], seed: int, fraction: float, test_size: float, target: str | None):
    for file_index, path in enumerate(files):
        encoding = _encoding_for(path)
        for chunk_index, chunk in enumerate(pd.read_csv(path, chunksize=CHUNK_ROWS, encoding=encoding, low_memory=False)):
            chunk.columns = [str(c).strip() for c in chunk.columns]
            if target and target not in chunk.columns:
                raise ValueError(f"Target column '{target}' is missing in {path.name}")
            selected, test_mask = _selected_and_split(chunk, fraction, test_size, seed, file_index, chunk_index, target)
            # Recreate split assignments for selected rows after sampling. Sampling preserves indices;
            # split decisions must therefore be made against the same selected index set.
            test = np.zeros(len(selected), dtype=bool)
            labels = selected[target].fillna("(missing)").astype(str) if target else pd.Series(["__all__"] * len(selected), index=selected.index)
            for label, index in labels.groupby(labels, sort=False).groups.items():
                loc = selected.index.get_indexer(index)
                rng = np.random.default_rng(_stable_seed(seed, file_index, chunk_index, str(label)))
                test[loc] = rng.random(len(loc)) < test_size
            yield path.name, file_index, chunk_index, selected, test


def _validate_csv(path: Path, feature_names: list[str], chunk_size: int = CHUNK_ROWS) -> dict[str, Any]:
    rows = nan_cells = inf_cells = 0
    columns = [*feature_names]
    for chunk in pd.read_csv(path, chunksize=chunk_size, low_memory=False):
        rows += len(chunk)
        features = chunk[[c for c in columns if c in chunk.columns]]
        nan_cells += int(features.isna().sum().sum())
        numeric = features.select_dtypes(include=[np.number])
        if not numeric.empty:
            inf_cells += int(np.isinf(numeric.to_numpy(dtype=np.float64, copy=False)).sum())
    return {"rows": rows, "nan_feature_cells": nan_cells, "infinite_feature_cells": inf_cells,
            "valid": nan_cells == 0 and inf_cells == 0}


def prepare_streaming(
    record: dict[str, Any], options: dict[str, Any], store: DatasetStore,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Prepare CSVs using bounded chunks; original files are read-only and never rewritten.

    A run that fails part-way leaves no partial output folder behind.
    """
    run_id = f"{datetime_token()}-{uuid.uuid4().hex[:6]}"
    output = store.prepared / record["id"] / run_id
    output.mkdir(parents=True, exist_ok=False)
    try:
        return _prepare_into(record, options, store, progress, run_id, output)
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


def _prepare_into(
    record: dict[str, Any], options: dict[str, Any], store: DatasetStore,
    progress: Callable[[float, str], None] | None, run_id: str, output: Path,
) -> dict[str, Any]:
    files = [Path(p) for p in record["files"]]
    if not files or any(not p.is_file() for p in files):
        raise FileNotFoundError("One or more dataset files are unavailable")
    target = options.get("target_column") or None
    fraction = float(options.get("sample_fraction", 1.0))
    test_size = float(options.get("test_size", 0.2))
    seed = int(options.get("seed", 42))
    fit_limit = int(options.get("fit_max_rows", 500_000))
    policy = options.get("duplicate_policy", "keep")
    if not 0 < fraction <= 1:
        raise ValueError("Sample fraction must be in (0, 1]")
    if not 0.05 <= test_size <= 0.5:
        raise ValueError("Test size must be between 5% and 50%")
    if fit_limit <= 0:
        raise ValueError("Fit row limit must be positive")
    if policy not in ("keep", "drop_exact", "drop_within_file"):
        raise ValueError("Unknown duplicate policy")

    total_expected = int((record.get("profile") or {}).get("rows", 0) * fraction)
    fit_rate = min(1.0, fit_limit / max(1, total_expected * (1 - test_size)))
    fit_parts: list[pd.DataFrame] = []
    fit_rows = 0
    schema: list[str] | None = None
    dup_removed_fit = 0
    n_seen_fit = 0
    with tempfile.TemporaryDirectory(prefix="datalens-prepare-fit-") as tmp:
        tracker = _DuplicateTracker(Path(tmp) / "seen.sqlite", policy)
        try:
            for source, fi, ci, chunk, test_mask in _iter_chunks(files, seed, fraction, test_size, target):
                if schema is None:
                    schema = list(chunk.columns)
                elif list(chunk.columns) != schema:
                    raise ValueError(f"{source}: columns differ from the first CSV")
                n_seen_fit += len(chunk)
                rows = chunk.copy()
                if target:
                    rows[target] = rows[target].fillna("(missing)")
                retained, dropped = tracker.filter(rows, target, source)
                dup_removed_fit += dropped
                # align positions after dedup using retained original indices
                train_mask = np.asarray([not bool(test_mask[chunk.index.get_loc(i)]) for i in retained.index], dtype=bool)
                train = retained.loc[train_mask]
                if not train.empty:
                    take = train if fit_rate >= 1 else train.sample(frac=fit_rate, random_state=seed + fi * 100_003 + ci)
                    if not take.empty:
                        fit_parts.append(take)
                        fit_rows += len(take)
                if progress and ci % 8 == 0:
                    progress(0.05 + min(0.25, (fi + 1) / len(files) * 0.25), f"Selecting training fit sample ({n_seen_fit:,} rows scanned)")
        finally:
            tracker.close()
    if not fit_parts or schema is None:
        raise ValueError("The selected sample produced no training rows")
    fit_frame = pd.concat(fit_parts, ignore_index=True)
    if len(fit_frame) > fit_limit:
        fit_frame = fit_frame.sample(n=fit_limit, random_state=seed).reset_index(drop=True)
    feature_cols = [c for c in schema if c != target]
    numeric, categorical = split_columns(fit_frame, exclude=[target] if target else [])
    prep_cfg = {
        "numeric": {"inf_strategy": "nan", "imputer": options.get("numeric_imputer", "median"),
                    "missing_indicator": bool(options.get("missing_indicator", True)),
                    "scaler": options.get("scaler", "robust")},
        "categorical": {"imputer": "most_frequent", "handle_unknown": "ignore",
                        "min_frequency": options.get("min_frequency", 0.01),
                        "encoding": options.get("encoding", "onehot")},
    }
    pre = build_preprocessor(numeric, categorical, prep_cfg)
    fit_X = fit_frame[feature_cols]
    fit_y = fit_frame[target].astype(str) if target else None
    fit_record = fit_preprocessor(pre, fit_X, fit_limit, seed)
    selection = options.get("feature_selection", "none")
    selection_info: dict[str, Any] = {"method": selection, "fit_rows": len(fit_frame)}
    selector = None
    if selection != "none":
        if selection in ("kbest_f", "model_rf", "kbest_mi") and fit_y is None:
            raise ValueError("Supervised feature selection requires a target column")
        transformed_fit = np.asarray(pre.transform(fit_X))
        k = min(int(options.get("selection_k", 30)), transformed_fit.shape[1])
        selector = build_selector(selection, k=k, seed=seed)
        if selection == "variance":
            selector.fit(transformed_fit)
        else:
            selector.fit(transformed_fit, fit_y.to_numpy())
        selection_info.update(k=k, selected_count=int(selector.get_support().sum()))
    out_names = [str(s) for s in pre.get_feature_names_out()]
    if selector is not None:
        out_names = list(np.asarray(out_names, dtype=object)[selector.get_support()])
    if len(set(out_names)) != len(out_names) or (target and target in set(out_names)):
        raise ValueError("Transformed feature names are not unique or collide with the target column name; rename a column in the source CSV")

    train_path, test_path = output / "train.csv", output / "test.csv"
    written = {"train": 0, "test": 0}
    sample_rows = dropped_rows = 0
    sample_missing_cells = sample_inf_cells = 0
    class_counts = {"train": Counter(), "test": Counter()}
    # 64-bit row hashes (8 bytes per row, about 23 MB for 2.8M rows) measure train/test overlap.
    row_hashes: dict[str, list[np.ndarray]] = {"train": [], "test": []}
    with tempfile.TemporaryDirectory(prefix="datalens-prepare-output-") as tmp:
        tracker = _DuplicateTracker(Path(tmp) / "seen.sqlite", policy)
        try:
            for source, fi, ci, chunk, test_mask in _iter_chunks(files, seed, fraction, test_size, target):
                sample_rows += len(chunk)
                sample_missing_cells += int(chunk.isna().sum().sum())
                sample_numeric = chunk.select_dtypes(include=[np.number])
                if not sample_numeric.empty:
                    sample_inf_cells += int(np.isinf(sample_numeric.to_numpy(dtype=np.float64, copy=False)).sum())
                if target:
                    chunk[target] = chunk[target].fillna("(missing)")
                kept, dropped = tracker.filter(chunk, target, source)
                dropped_rows += dropped
                train_mask = np.asarray([not bool(test_mask[chunk.index.get_loc(i)]) for i in kept.index], dtype=bool)
                for split_name, mask, dest in (("train", train_mask, train_path), ("test", ~train_mask, test_path)):
                    part = kept.loc[mask]
                    if part.empty:
                        continue
                    row_hashes[split_name].append(pd.util.hash_pandas_object(part, index=False).to_numpy())
                    X = part[feature_cols]
                    transformed = np.asarray(pre.transform(X))
                    if selector is not None:
                        transformed = selector.transform(transformed)
                    result = pd.DataFrame(transformed, columns=out_names)
                    if target:
                        result[target] = part[target].astype(str).to_numpy()
                        class_counts[split_name].update(part[target].astype(str).value_counts().to_dict())
                    result.to_csv(dest, mode="a", header=written[split_name] == 0, index=False)
                    written[split_name] += len(result)
                if progress and ci % 8 == 0:
                    progress(0.35 + min(0.5, (fi + (ci + 1) / 100) / len(files) * 0.5), f"Transforming and writing {sample_rows:,} sampled rows")
        finally:
            tracker.close()
    validation = {"train": _validate_csv(train_path, out_names), "test": _validate_csv(test_path, out_names)}
    if not validation["train"]["valid"] or not validation["test"]["valid"]:
        raise RuntimeError("Prepared feature data failed NaN/infinity validation")
    duplicate_report = {"policy": policy, "sample_rows_before": sample_rows, "rows_removed": dropped_rows,
                        "rows_after": written["train"] + written["test"]}
    train_hashes =np.concatenate(row_hashes["train"]) if row_hashes["train"] else np.empty(0, dtype=np.uint64)
    test_hashes = np.concatenate(row_hashes["test"]) if row_hashes["test"] else np.empty(0, dtype=np.uint64)
    overlap_rows = int(np.isin(test_hashes, train_hashes).sum()) if train_hashes.size and test_hashes.size else 0
    overlap = {"test_rows": int(test_hashes.size), "test_rows_also_in_train": overlap_rows,
               "percent_of_test": round(100 * overlap_rows / max(1, test_hashes.size), 4),
               "basis": "identical feature values and target in the source rows, before transformation"}
    coverage, coverage_warnings = class_coverage(class_counts) if target else ([], [])
    run_warnings: list[str] = []
    if fraction < 1:
        run_warnings.append("A sampled run is for workflow validation and is not a full-dataset result.")
    if overlap_rows:
        run_warnings.append(f"{overlap_rows:,} test rows ({overlap['percent_of_test']}%) are exact copies of training rows, so test scores "
                            "will look better than they are. Choose a duplicate policy other than 'keep' to remove them.")
    run_warnings.extend(coverage_warnings)
    if target:
        n_missing_target = class_counts["train"].get("(missing)", 0) + class_counts["test"].get("(missing)", 0)
        if n_missing_target:
            run_warnings.append(f"{n_missing_target:,} rows have no target value and were kept as the class '(missing)'. Fix or remove them before modeling.")
        if len(coverage) > MANY_CLASSES:
            run_warnings.append(f"The target has {len(coverage):,} distinct values and is treated as classes. If it is a continuous quantity, classification metrics and stratification do not apply.")
    min_freq = prep_cfg["categorical"]["min_frequency"] if prep_cfg["categorical"]["encoding"] == "onehot" and categorical else None
    config_record = {
        "dataset_id": record["id"], "dataset_name": record["name"], "sample_fraction": fraction,
        "is_full_dataset": fraction == 1, "seed": seed, "test_size": test_size,
        "target_column": target, "duplicate_policy": policy, "numeric_imputer": prep_cfg["numeric"]["imputer"],
        "missing_indicator": prep_cfg["numeric"]["missing_indicator"], "encoding": prep_cfg["categorical"]["encoding"],
        "scaler": prep_cfg["numeric"]["scaler"], "feature_selection": selection,
        "selection_k": options.get("selection_k", 30), "fit_record": fit_record,
        "split_method": "seeded per-class random assignment within chunks (approximately stratified)",
        "class_counts": {split: dict(counts) for split, counts in class_counts.items()},
        "class_coverage": coverage, "train_test_overlap": overlap,
        "categorical_min_frequency": min_freq,
        "categorical_note": (f"One-hot encoding groups categories rarer than {min_freq:.0%} of training rows into an 'infrequent' column."
                             if min_freq else None),
        "chunk_rows": CHUNK_ROWS, "created_at": utc_now(),
    }
    profile = record.get("profile") or {}
    before_after = {
        "source_full_dataset": {"rows": int(profile.get("rows", sample_rows)), "columns": int(profile.get("columns", len(schema))),
                                "missing_cells": int(profile.get("missing_cells", 0)),
                                "infinite_cells": int(profile.get("positive_infinity_cells", 0) + profile.get("negative_infinity_cells", 0))},
        "before_sample_preparation": {"rows": sample_rows, "columns": len(schema), "feature_columns": len(feature_cols),
                                      "missing_cells": sample_missing_cells, "infinite_cells": sample_inf_cells},
        "processed_sample": {"rows": sample_rows, "rows_after_duplicate_policy": written["train"] + written["test"],
                             "train_rows": written["train"], "test_rows": written["test"],
                             "missing_feature_cells_after": validation["train"]["nan_feature_cells"] + validation["test"]["nan_feature_cells"],
                             "infinite_feature_cells_after": validation["train"]["infinite_feature_cells"] + validation["test"]["infinite_feature_cells"],
                             "transformed_features": len(out_names), "duplicate_rows_removed": dropped_rows,
                             "sample_fraction": fraction},
        "validation": validation,
    }
    quality_report = {
        "summary": "Prepared outputs preserve all selected rows except duplicates removed under the explicitly chosen policy. Features were fitted on training data only.",
        "source_issues": profile.get("issues", []), "before_after": before_after,
        "validation": validation, "duplicate_policy": duplicate_report,
        "train_test_overlap": overlap, "class_coverage": coverage,
        "warnings": run_warnings,
    }
    issue_lines = [f"- **{item['title']}**{(' · ' + item['column']) if item.get('column') else ''}: {item['explanation']}"
                   + (f" *Recommendation:* {item['recommendation']}" if item.get("recommendation") else "")
                   for item in quality_report["source_issues"]]
    coverage_lines = [f"| {row['label']} | {row['train']:,} | {row['test']:,} | {', '.join(row['flags']) or 'ok'} |" for row in coverage]
    report_md = [
        "# DataLens preparation quality report", "",
        f"- Dataset: **{record['name']}**",
        f"- Run: {run_id}",
        f"- Input: **{'full dataset' if fraction == 1 else f'{fraction:.0%} sample'}**",
        f"- Duplicate policy: **{policy}** ({dropped_rows:,} rows removed from the selected input)",
        f"- Split: **{written['train']:,} train / {written['test']:,} test**",
        f"- Validation: **{'passed' if validation['train']['valid'] and validation['test']['valid'] else 'failed'}** (no missing or infinite transformed feature values)",
        "", "## Source data quality findings", "",
        *(issue_lines or ["- No source quality issues were reported by the profile."]),
        "", "## Before and after", "",
        f"- Selected input rows: {sample_rows:,}",
        f"- Rows after the selected duplicate policy: {written['train'] + written['test']:,}",
        f"- Transformed feature columns: {len(out_names)}",
        f"- Missing feature cells after preparation: {validation['train']['nan_feature_cells'] + validation['test']['nan_feature_cells']:,}",
        f"- Infinite feature cells after preparation: {validation['train']['infinite_feature_cells'] + validation['test']['infinite_feature_cells']:,}",
        f"- Test rows that are exact copies of training rows: {overlap_rows:,} ({overlap['percent_of_test']}% of test)",
        "", "## Warnings", "",
        *([f"- {w}" for w in run_warnings[:MAX_LISTED_WARNINGS]] or ["- None."]),
        *([f"- ...and {len(run_warnings) - MAX_LISTED_WARNINGS} more (see quality_report.json)."] if len(run_warnings) > MAX_LISTED_WARNINGS else []),
        *(["", "## Class coverage", "", "| Class | Train rows | Test rows | Status |", "|---|---:|---:|---|", *coverage_lines] if coverage else []),
        *(["", f"Note: {config_record['categorical_note']}"] if config_record["categorical_note"] else []),
        "", "Outliers are flagged during profiling and are never removed automatically.",
    ]
    (output / "config.json").write_text(json.dumps(config_record, indent=2), encoding="utf-8")
    (output / "quality_report.json").write_text(json.dumps(quality_report, indent=2), encoding="utf-8")
    (output / "quality_report.md").write_text("\n".join(report_md) + "\n", encoding="utf-8")
    (output / "comparison.json").write_text(json.dumps(before_after, indent=2), encoding="utf-8")
    manifest = {"id": run_id, "dataset_id": record["id"], "dataset_name": record["name"],
                "created_at": utc_now(), "output_dir": str(output), "files": ["train.csv", "test.csv", "config.json", "quality_report.json", "quality_report.md", "comparison.json"],
                "rows": written, "sample_fraction": fraction, "comparison": before_after,
                "validation": validation, "duplicate_report": duplicate_report,
                "target_column": target, "warnings": run_warnings, "class_coverage": coverage,
                "train_test_overlap": overlap, "config": {k: config_record[k] for k in (
                    "test_size", "seed", "duplicate_policy", "numeric_imputer", "missing_indicator", "encoding",
                    "scaler", "feature_selection", "selection_k")}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if progress:
        progress(1.0, "Preparation and validation complete")
    return manifest


def datetime_token() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())
