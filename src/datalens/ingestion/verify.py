"""Dataset verification: a cheap, chunked first look at raw CSV files.

Purpose (Phase 1): confirm the files exist, are readable, share one schema and
contain the label column, and report row counts, NaN/inf cell counts and the
label distribution -- WITHOUT loading whole files into memory.

Everything reported here is measured from the files on disk; nothing is assumed.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_ENCODINGS = ("utf-8", "latin-1", "cp1252")


def discover_files(raw_dir: str | Path, pattern: str = "*.csv") -> list[Path]:
    """Return sorted CSV paths in raw_dir. Raise a helpful error if none exist."""
    raw = Path(raw_dir)
    if not raw.is_dir():
        raise FileNotFoundError(f"Raw data directory does not exist: {raw}")
    files = sorted(p for p in raw.glob(pattern) if p.is_file())
    if not files:
        raise FileNotFoundError(
            f"No files matching '{pattern}' in {raw}. "
            "Download CIC-IDS2017 and place the CSV files there (see data/README.md)."
        )
    return files


def scan_file(
    path: str | Path,
    label_column: str = "Label",
    chunk_size: int = 200_000,
    encodings: tuple[str, ...] = DEFAULT_ENCODINGS,
) -> dict[str, Any]:
    """Scan one CSV in chunks and return measured facts about it.

    Tries each encoding in order; a UnicodeDecodeError anywhere in the file restarts
    the scan with the next encoding. Any other failure is recorded in the result
    under 'error' rather than raised, so one bad file does not hide the others.
    """
    path = Path(path)
    result: dict[str, Any] = {
        "file": path.name,
        "size_mb": round(path.stat().st_size / 1024**2, 2),
        "error": None,
    }

    for enc in encodings:
        rows = 0
        nan_cells = 0
        inf_cells = 0
        labels: Counter = Counter()
        columns: list[str] | None = None
        non_numeric: set[str] = set()
        try:
            for chunk in pd.read_csv(path, chunksize=chunk_size, encoding=enc, low_memory=False):
                chunk.columns = chunk.columns.astype(str).str.strip()
                if columns is None:
                    columns = list(chunk.columns)
                rows += len(chunk)
                nan_cells += int(chunk.isna().sum().sum())
                numeric = chunk.select_dtypes(include="number")
                inf_cells += int(np.isinf(numeric.to_numpy(dtype=float, copy=False)).sum())
                non_numeric.update(
                    c for c in chunk.columns
                    if c != label_column and not pd.api.types.is_numeric_dtype(chunk[c])
                )
                if label_column in chunk.columns:
                    labels.update(chunk[label_column].astype(str).str.strip().value_counts().to_dict())
        except UnicodeDecodeError:
            logger.info("%s: encoding %s failed, trying next", path.name, enc)
            continue
        except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result

        result.update(
            encoding=enc,
            rows=rows,
            n_columns=len(columns or []),
            columns=columns or [],
            has_label_column=label_column in (columns or []),
            nan_cells=nan_cells,
            inf_cells=inf_cells,
            non_numeric_columns=sorted(non_numeric),
            label_counts=dict(labels),
        )
        if not result["has_label_column"]:
            result["error"] = f"Label column '{label_column}' not found"
        return result

    result["error"] = f"Could not decode file with any of {list(encodings)}"
    return result


def verify_dataset(
    raw_dir: str | Path,
    pattern: str = "*.csv",
    label_column: str = "Label",
    chunk_size: int = 200_000,
    encodings: tuple[str, ...] = DEFAULT_ENCODINGS,
) -> dict[str, Any]:
    """Scan every file and combine the facts into one verification report."""
    files = discover_files(raw_dir, pattern)
    per_file = [scan_file(f, label_column, chunk_size, encodings) for f in files]

    ok = [r for r in per_file if r.get("rows") is not None]
    column_sets = {tuple(r["columns"]) for r in ok}
    total_labels: Counter = Counter()
    for r in ok:
        total_labels.update(r["label_counts"])

    return {
        "raw_dir": str(raw_dir),
        "n_files": len(files),
        "n_files_with_errors": sum(1 for r in per_file if r["error"]),
        "total_rows": sum(r["rows"] for r in ok),
        "total_size_mb": round(sum(r["size_mb"] for r in per_file), 2),
        "schema_consistent_across_files": len(column_sets) <= 1,
        "total_nan_cells": sum(r["nan_cells"] for r in ok),
        "total_inf_cells": sum(r["inf_cells"] for r in ok),
        "label_counts": dict(total_labels.most_common()),
        "files": per_file,
    }
