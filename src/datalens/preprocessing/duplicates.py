"""Configurable duplicate handling, with per-class accounting.

Why duplicates matter for evaluation
- Exact duplicates split across train and test let a model "recognise" test rows it has
  memorised, inflating test scores. Removing them BEFORE splitting prevents this.
- Identical feature vectors with different labels are irreducible label noise. Keeping
  them lowers attainable accuracy honestly; removing them makes the benchmark easier.
- Under a day-aware split, identical vectors that appear on different days leak across
  the train/test boundary. See `cross_file_duplicates`.

Policies (config: preprocessing.duplicates.policy)
- keep:                      retain everything (default for exploration)
- drop_exact:                drop repeats of an earlier row (features + label), keep first
- drop_conflicts:            drop EVERY row of a feature vector that has >1 label
- drop_exact_and_conflicts:  both of the above

Nothing is removed silently: the report lists removals per class and warns when a class
loses a large share of its rows or disappears.
Hashing uses pandas row hashes (same approach as profiling.profile_duplicates); hash
collisions are negligible but non-zero.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

POLICIES = ("keep", "drop_exact", "drop_conflicts", "drop_exact_and_conflicts")


def duplicate_masks(
    df: pd.DataFrame, feature_columns: list[str], label_column: str
) -> dict[str, np.ndarray]:
    """Boolean masks: `exact` (repeat of an earlier row) and `conflict` (label-conflicting vector)."""
    n = len(df)
    if n == 0 or not feature_columns:
        return {"exact": np.zeros(n, dtype=bool), "conflict": np.zeros(n, dtype=bool)}
    h_feat = pd.util.hash_pandas_object(df[feature_columns], index=False).to_numpy()
    labels = df[label_column].astype(str).to_numpy()
    h_full = pd.util.hash_pandas_object(df[[*feature_columns, label_column]], index=False)
    tmp = pd.DataFrame({"h": h_feat, "label": labels})
    per_hash = tmp.groupby("h")["label"].nunique()
    conflicting = per_hash[per_hash > 1].index
    return {
        "exact": h_full.duplicated().to_numpy(),
        "conflict": tmp["h"].isin(conflicting).to_numpy(),
    }


def cross_file_duplicates(
    df: pd.DataFrame, feature_columns: list[str], label_column: str, source_column: str
) -> dict[str, Any]:
    """Feature vectors that occur in more than one source file (capture day)."""
    if source_column not in df.columns:
        raise KeyError(f"Source column '{source_column}' not in DataFrame")
    h = pd.util.hash_pandas_object(df[feature_columns], index=False).to_numpy()
    pairs = pd.DataFrame({"h": h, "src": df[source_column].astype(str).to_numpy(),
                          "label": df[label_column].astype(str).to_numpy()})
    hf = pairs[["h", "src"]].drop_duplicates()
    files_per_hash = hf.groupby("h").size()
    spanning = files_per_hash[files_per_hash > 1].index
    sp = pairs[pairs["h"].isin(spanning)]
    labels_per_hash = sp[["h", "label"]].drop_duplicates().groupby("h").size()
    per_file = hf[hf["h"].isin(spanning)].groupby("src").size()
    return {
        "n_groups_spanning_files": int(len(spanning)),
        "n_rows_in_spanning_groups": int(len(sp)),
        "n_spanning_groups_with_label_disagreement": int((labels_per_hash > 1).sum()),
        "distinct_spanning_vectors_per_file": {str(k): int(v) for k, v in per_file.items()},
    }


def apply_duplicate_policy(
    df: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
    policy: str = "keep",
    max_class_loss_pct: float = 50.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply a duplicate policy. Returns (frame, report).

    With policy 'keep' the SAME frame is returned (no copy). Otherwise one filtered copy
    is made with a fresh RangeIndex (splitters use positional indices); delete the input
    frame afterwards on memory-constrained machines.
    """
    if policy not in POLICIES:
        raise ValueError(f"Unknown duplicate policy '{policy}'. Choose from {POLICIES}")
    before = df[label_column].astype(str).value_counts()
    masks = duplicate_masks(df, feature_columns, label_column)

    if policy == "keep":
        drop = np.zeros(len(df), dtype=bool)
    elif policy == "drop_exact":
        drop = masks["exact"]
    elif policy == "drop_conflicts":
        drop = masks["conflict"]
    else:
        drop = masks["exact"] | masks["conflict"]

    out = df if policy == "keep" else df.loc[~drop].reset_index(drop=True)
    after = out[label_column].astype(str).value_counts()

    removed = {c: int(before[c] - after.get(c, 0)) for c in before.index if before[c] - after.get(c, 0) > 0}
    loss_pct = {c: round(100 * removed[c] / before[c], 3) for c in removed}
    warnings = []
    for c, pct in loss_pct.items():
        if after.get(c, 0) == 0:
            warnings.append(f"Class '{c}' was removed ENTIRELY by policy '{policy}'")
        elif pct >= max_class_loss_pct:
            warnings.append(f"Class '{c}' lost {pct}% of its rows under policy '{policy}'")
    report = {
        "policy": policy,
        "rows_before": int(len(df)),
        "rows_after": int(len(out)),
        "rows_removed": int(drop.sum()),
        "exact_duplicate_rows": int(masks["exact"].sum()),
        "label_conflict_rows": int(masks["conflict"].sum()),
        "removed_by_class": removed,
        "class_loss_pct": loss_pct,
        "classes_lost_entirely": [c for c in before.index if after.get(c, 0) == 0],
        "warnings": warnings,
    }
    return out, report
