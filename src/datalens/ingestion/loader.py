"""Dataset loading: chunked CSV reading, optional sampling, metadata and fingerprint.

Design notes
- Files are read in chunks; with sample_fraction set, each chunk is sampled *before*
  concatenation, so peak memory stays near (sample size + one chunk).
- Column names are stripped of whitespace (CIC-IDS2017 headers have leading spaces).
- The loader adds a `source_column` holding the originating file name. For CIC-IDS2017
  this identifies the capture day, which later phases need for day-aware evaluation.
  It is metadata, NOT a model feature.
- Metadata always records whether the loaded frame is the full dataset or a sample,
  so a sample can never be silently reported as full-dataset results.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from datalens.ingestion.verify import DEFAULT_ENCODINGS, discover_files

logger = logging.getLogger(__name__)


def file_sha256(path: str | Path, block_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def dataset_fingerprint(files: list[Path], compute_hash: bool = True) -> str:
    """Stable fingerprint of the raw inputs (names, sizes and, optionally, content hashes)."""
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.name.encode())
        h.update(str(f.stat().st_size).encode())
        if compute_hash:
            h.update(file_sha256(f).encode())
    return h.hexdigest()[:16]


def clean_columns(columns: pd.Index) -> list[str]:
    """Strip whitespace from column names; raise if stripping creates duplicates."""
    cleaned = [str(c).strip() for c in columns]
    dupes = sorted({c for c in cleaned if cleaned.count(c) > 1})
    if dupes:
        raise ValueError(f"Duplicate column names after stripping whitespace: {dupes}")
    return cleaned


def _read_one(
    path: Path,
    label_column: str,
    source_column: str,
    chunk_size: int,
    sample_fraction: float | None,
    seed: int,
    encodings: tuple[str, ...],
) -> tuple[pd.DataFrame, int, str]:
    """Read one CSV in chunks. Returns (frame, rows_in_file, encoding_used)."""
    last_error: Exception | None = None
    for enc in encodings:
        parts: list[pd.DataFrame] = []
        rows_in_file = 0
        try:
            for i, chunk in enumerate(
                pd.read_csv(path, chunksize=chunk_size, encoding=enc, low_memory=False)
            ):
                chunk.columns = clean_columns(chunk.columns)
                if label_column not in chunk.columns:
                    raise ValueError(f"{path.name}: label column '{label_column}' not found")
                rows_in_file += len(chunk)
                if sample_fraction is not None:
                    chunk = chunk.sample(frac=sample_fraction, random_state=seed + i)
                chunk[label_column] = chunk[label_column].astype(str).str.strip()
                parts.append(chunk)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        df[source_column] = path.name
        return df, rows_in_file, enc
    raise ValueError(f"{path.name}: could not decode with {list(encodings)} ({last_error})")


def load_dataset(
    raw_dir: str | Path,
    pattern: str = "*.csv",
    label_column: str = "Label",
    source_column: str = "source_file",
    chunk_size: int = 200_000,
    sample_fraction: float | None = None,
    seed: int = 42,
    encodings: tuple[str, ...] = DEFAULT_ENCODINGS,
    compute_hash: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load all matching CSVs into one DataFrame and return (df, metadata).

    Raises ValueError for an invalid sample_fraction, a missing label column, or
    files whose column names differ from the first file.
    """
    if sample_fraction is not None and not (0 < sample_fraction <= 1):
        raise ValueError(f"sample_fraction must be in (0, 1] or None, got {sample_fraction}")
    if sample_fraction == 1:
        sample_fraction = None

    files = discover_files(raw_dir, pattern)
    frames: list[pd.DataFrame] = []
    per_file: list[dict[str, Any]] = []
    reference_columns: list[str] | None = None

    for f in files:
        df, rows_in_file, enc = _read_one(
            f, label_column, source_column, chunk_size, sample_fraction, seed, encodings
        )
        cols = [c for c in df.columns if c != source_column]
        if reference_columns is None:
            reference_columns = cols
        elif cols != reference_columns:
            raise ValueError(
                f"{f.name}: columns differ from {files[0].name} "
                f"(missing={sorted(set(reference_columns) - set(cols))}, "
                f"extra={sorted(set(cols) - set(reference_columns))})"
            )
        per_file.append(
            {"file": f.name, "rows_in_file": rows_in_file, "rows_loaded": len(df), "encoding": enc}
        )
        frames.append(df)
        logger.info("Loaded %s: %d of %d rows (%s)", f.name, len(df), rows_in_file, enc)

    data = pd.concat(frames, ignore_index=True)
    meta = {
        "raw_dir": str(raw_dir),
        "n_files": len(files),
        "files": per_file,
        "rows_in_files": sum(p["rows_in_file"] for p in per_file),
        "rows_loaded": len(data),
        "n_columns": data.shape[1],
        "label_column": label_column,
        "source_column": source_column,
        "sample_fraction": sample_fraction,
        "is_full_dataset": sample_fraction is None,
        "random_seed": seed,
        "fingerprint": dataset_fingerprint(files, compute_hash),
        "fingerprint_includes_content_hash": compute_hash,
    }
    return data, meta
