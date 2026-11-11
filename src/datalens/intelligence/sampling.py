"""Seeded, bounded sampling shared by all analyses.

The sample is drawn in one streaming pass (per-chunk Bernoulli with a seed derived from file and chunk
indices), so memory is bounded and the same seed always returns the same rows. Every sampled row keeps a
stable ``row_id``: its 0-based position among the data rows of all source files, read in file order.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from datalens.app_service import CHUNK_ROWS, _encoding_for

ANALYSIS_SAMPLE_ROWS = 50_000
ROW_ID = "__row_id__"


def load_sample(files: list[Path], total_rows: int, cap: int = ANALYSIS_SAMPLE_ROWS, seed: int = 42) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return (frame with a row-id column, sampling info). Rows are kept in original order."""
    if total_rows <= 0:
        raise ValueError("The dataset has no rows to analyze")
    fraction = min(1.0, cap / total_rows)
    parts: list[pd.DataFrame] = []
    offset = 0
    for file_index, path in enumerate(files):
        for chunk_index, chunk in enumerate(pd.read_csv(path, chunksize=CHUNK_ROWS, encoding=_encoding_for(path), low_memory=False)):
            chunk.columns = [str(c).strip() for c in chunk.columns]
            ids = np.arange(offset, offset + len(chunk), dtype=np.int64)
            offset += len(chunk)
            if fraction < 1.0:
                rng = np.random.default_rng([seed, file_index, chunk_index, 7919])
                keep = rng.random(len(chunk)) < fraction
                chunk = chunk.loc[keep]
                ids = ids[keep]
            chunk = chunk.copy()
            chunk[ROW_ID] = ids
            parts.append(chunk)
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if len(frame) > int(cap * 1.1):  # Bernoulli overshoot guard, still seeded
        keep_idx = np.sort(np.random.default_rng([seed, 31337]).choice(len(frame), size=cap, replace=False))
        frame = frame.iloc[keep_idx].reset_index(drop=True)
    frame = _normalise_types(frame)
    info = {"rows_total": int(total_rows), "rows_sampled": int(len(frame)), "sampled": bool(len(frame) < total_rows),
            "sample_cap": int(cap), "seed": int(seed),
            "method": "seeded per-chunk Bernoulli sample; row_id = 0-based data-row position across files"}
    return frame, info


def _normalise_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Chunks infer dtypes independently; re-unify columns that are numeric apart from stray text."""
    for col in frame.columns:
        if col == ROW_ID or pd.api.types.is_numeric_dtype(frame[col]):
            continue
        if frame[col].dtype == object or str(frame[col].dtype).startswith("str"):
            converted = pd.to_numeric(frame[col], errors="coerce")
            non_null = frame[col].notna().sum()
            if non_null and converted.notna().sum() >= 0.99 * non_null:
                frame[col] = converted
    return frame


def split_feature_types(frame: pd.DataFrame, exclude: list[str] | None = None, max_categories: int = 50) -> dict[str, list[str]]:
    """Classify columns. Constant columns and the excluded ones (target, row id) are reported separately."""
    exclude = set(exclude or []) | {ROW_ID}
    numeric: list[str] = []
    categorical: list[str] = []
    high_card: list[str] = []
    constant: list[str] = []
    for col in frame.columns:
        if col in exclude:
            continue
        series = frame[col].replace([np.inf, -np.inf], np.nan)
        if series.nunique(dropna=True) <= 1:
            constant.append(col)
        elif pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            numeric.append(col)
        elif series.nunique(dropna=True) <= max_categories:
            categorical.append(col)
        else:
            high_card.append(col)
    return {"numeric": numeric, "categorical": categorical, "high_cardinality": high_card, "constant": constant}


def target_kind(series: pd.Series | None, max_classes: int = 50) -> str:
    """'classification', 'regression' or 'none'. A numeric target with many distinct values is regression."""
    if series is None:
        return "none"
    n = series.nunique(dropna=True)
    if n < 2:
        return "none"
    if pd.api.types.is_numeric_dtype(series) and n > max_classes:
        return "regression"
    return "classification"


def clean_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Float copy with infinities turned into NaN (never altering the source frame)."""
    return frame[columns].astype("float64").replace([np.inf, -np.inf], np.nan)
