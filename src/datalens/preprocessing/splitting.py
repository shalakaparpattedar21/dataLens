"""Train/test splitting: stratified random and day-aware (collection-period) evaluation.

These two strategies answer DIFFERENT questions and their scores must never be pooled:
- Stratified random split: "how well does the model do on traffic drawn from the same
  distribution (same days) it was trained on?" Optimistic: rows from one capture are
  highly correlated, so near-duplicates sit on both sides of the split.
- Day-aware split: "how well does it do on a capture period it never saw?" In CIC-IDS2017
  each attack family is mostly confined to specific days, so holding out a day usually
  removes whole attack classes from training. Multiclass scores on classes absent from
  training are undefined by construction; the metadata lists them explicitly.
  Day-aware results are NOT a universal measure of real-world generalization.

Splits return POSITIONAL INDICES (np.ndarray), not DataFrame copies, to save memory.
Use df.iloc[split.train_idx]. Splitting happens BEFORE any preprocessing is fitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

RARE_POLICIES = ("train_only", "error")


@dataclass
class SplitResult:
    strategy: str
    train_idx: np.ndarray
    test_idx: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


def class_distribution(y: pd.Series | np.ndarray) -> dict[str, Any]:
    """Counts and percentages per class (descending by count)."""
    counts = pd.Series(np.asarray(y).astype(str)).value_counts()
    n = int(counts.sum())
    return {
        "n": n,
        "counts": {str(k): int(v) for k, v in counts.items()},
        "percent": {str(k): round(100 * v / n, 4) if n else 0.0 for k, v in counts.items()},
    }


def _check_labels(y: pd.Series | np.ndarray) -> np.ndarray:
    arr = pd.Series(y)
    if arr.isna().any():
        raise ValueError(f"Labels contain {int(arr.isna().sum())} missing values; resolve before splitting")
    if len(arr) == 0:
        raise ValueError("Cannot split an empty dataset")
    return arr.astype(str).to_numpy()


def stratified_random_split(
    y: pd.Series | np.ndarray,
    test_size: float = 0.2,
    seed: int = 42,
    rare_class_policy: str = "train_only",
    min_class_count: int = 2,
    min_test_per_class: int = 5,
) -> SplitResult:
    """Stratified random split on labels.

    Stratification needs at least 2 rows per class. Classes below `min_class_count`:
    - 'train_only' (default): all their rows go to training; they are listed in the
      metadata as absent from the test set. Nothing is dropped.
    - 'error': raise ValueError.
    Classes whose expected test count is below `min_test_per_class` are flagged: per-class
    metrics for them are statistically unreliable.
    """
    if rare_class_policy not in RARE_POLICIES:
        raise ValueError(f"rare_class_policy must be one of {RARE_POLICIES}")
    labels = _check_labels(y)
    codes, uniques = pd.factorize(labels, sort=True)
    counts = np.bincount(codes)
    rare_codes = np.flatnonzero(counts < min_class_count)
    rare_mask = np.isin(codes, rare_codes)
    forced = [str(uniques[c]) for c in rare_codes]
    if forced and rare_class_policy == "error":
        raise ValueError(f"Classes with < {min_class_count} rows cannot be stratified: {forced}")

    eligible = np.flatnonzero(~rare_mask)
    if eligible.size == 0:
        raise ValueError("No class has enough rows to stratify")
    train_ok, test_ok = train_test_split(
        eligible, test_size=test_size, random_state=seed, stratify=codes[eligible]
    )
    train_idx = np.sort(np.concatenate([train_ok, np.flatnonzero(rare_mask)]))
    test_idx = np.sort(test_ok)

    train_d, test_d = class_distribution(labels[train_idx]), class_distribution(labels[test_idx])
    meta = {
        "strategy": "stratified_random",
        "seed": seed,
        "test_size_requested": test_size,
        "n_train": int(train_idx.size),
        "n_test": int(test_idx.size),
        "test_fraction_actual": round(test_idx.size / len(labels), 6),
        "rare_class_policy": rare_class_policy,
        "min_class_count_for_stratification": min_class_count,
        "classes_forced_to_train": forced,
        "classes_absent_from_test": sorted(set(train_d["counts"]) - set(test_d["counts"])),
        "classes_with_unreliable_test_metrics": sorted(
            c for c in train_d["counts"] if test_d["counts"].get(c, 0) < min_test_per_class),
        "min_test_per_class_threshold": min_test_per_class,
        "train_distribution": train_d,
        "test_distribution": test_d,
        "notes": ["Random split: rows from the same capture are correlated, so scores are "
                  "optimistic relative to unseen-day evaluation. Do not pool with day-aware scores."],
    }
    return SplitResult("stratified_random", train_idx, test_idx, meta)


def _match_files(files: list[str], patterns: list[str]) -> set[str]:
    return {f for f in files if any(p.lower() in f.lower() for p in patterns)}


def day_aware_split(
    source: pd.Series | np.ndarray,
    y: pd.Series | np.ndarray,
    train_days: list[str],
    test_days: list[str],
    unassigned: str = "error",
) -> SplitResult:
    """Split by collection file/day. Patterns are case-insensitive substrings of file names.

    Every file must be assigned to train or test (unassigned='error') or explicitly excluded
    (unassigned='exclude'; excluded files are listed in the metadata). No row of a test file
    can enter training.
    """
    if unassigned not in ("error", "exclude"):
        raise ValueError("unassigned must be 'error' or 'exclude'")
    labels = _check_labels(y)
    src = pd.Series(source).astype(str).to_numpy()
    if len(src) != len(labels):
        raise ValueError("source and y must have the same length")
    files = sorted(set(src))

    for name, pats in (("train_days", train_days), ("test_days", test_days)):
        if not pats:
            raise ValueError(f"{name} must not be empty")
        for p in pats:
            if not _match_files(files, [p]):
                raise ValueError(f"{name} pattern '{p}' matches no file. Files: {files}")
    train_files, test_files = _match_files(files, train_days), _match_files(files, test_days)
    overlap = sorted(train_files & test_files)
    if overlap:
        raise ValueError(f"Files assigned to BOTH train and test: {overlap}")
    leftover = sorted(set(files) - train_files - test_files)
    if leftover and unassigned == "error":
        raise ValueError(f"Files not assigned to train or test: {leftover} (use unassigned='exclude' to drop explicitly)")

    train_idx = np.flatnonzero(np.isin(src, sorted(train_files)))
    test_idx = np.flatnonzero(np.isin(src, sorted(test_files)))
    train_d, test_d = class_distribution(labels[train_idx]), class_distribution(labels[test_idx])
    unseen = sorted(set(test_d["counts"]) - set(train_d["counts"]))
    unseen_rows = sum(test_d["counts"][c] for c in unseen)

    notes = ["Day-aware split: a held-out day measures generalization to that capture period only."]
    if unseen:
        notes.append(f"Classes in test but ABSENT from training {unseen} ({unseen_rows} test rows) cannot be "
                     "learned in multiclass mode; evaluate them in a binary attack-vs-benign setting or report separately.")
    meta = {
        "strategy": "day_aware",
        "train_patterns": train_days, "test_patterns": test_days,
        "train_files": sorted(train_files), "test_files": sorted(test_files),
        "excluded_files": leftover,
        "n_train": int(train_idx.size), "n_test": int(test_idx.size),
        "classes_absent_from_train": unseen,
        "test_rows_in_classes_absent_from_train": int(unseen_rows),
        "classes_absent_from_test": sorted(set(train_d["counts"]) - set(test_d["counts"])),
        "classes_evaluable_in_both": sorted(set(train_d["counts"]) & set(test_d["counts"])),
        "train_distribution": train_d, "test_distribution": test_d,
        "notes": notes,
    }
    return SplitResult("day_aware", train_idx, test_idx, meta)


def leave_one_group_out_splits(
    source: pd.Series | np.ndarray,
    y: pd.Series | np.ndarray,
    groups: dict[str, list[str]],
) -> Iterator[tuple[str, SplitResult]]:
    """Yield (held_out_name, day_aware split) holding out each named day-group in turn.

    `groups` maps a name to file-name patterns, e.g. {"Tuesday": ["tuesday"], "Friday": ["friday"]}.
    All files must be covered by some group.
    """
    for held_out, pats in groups.items():
        rest = [p for name, ps in groups.items() if name != held_out for p in ps]
        yield held_out, day_aware_split(source, y, train_days=rest, test_days=pats)


def validate_split(split: SplitResult, n_rows: int) -> None:
    """Raise AssertionError if a split is malformed (overlap, out-of-range, duplicates)."""
    tr, te = split.train_idx, split.test_idx
    assert tr.size and te.size, "empty partition"
    assert np.intersect1d(tr, te).size == 0, "train and test overlap"
    assert tr.min() >= 0 and te.min() >= 0 and tr.max() < n_rows and te.max() < n_rows, "index out of range"
    assert np.unique(tr).size == tr.size and np.unique(te).size == te.size, "duplicate indices"
