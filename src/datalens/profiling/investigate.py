"""Streaming investigation of raw CSV files (never loads a whole file).

Answers, from the actual bytes and rows on disk:
  A. Where are missing values (by column, file, class)?
  B. Where are infinite values, and do they coincide with zero flow duration?
  C. Do label bytes contain a replacement character, and does one class have several spellings?
  D. Exact duplicates, label-conflicting vectors, vectors repeated across files.

Files are read as latin-1 on purpose: latin-1 maps every byte to a code point, so reading is
LOSSLESS and independent of the loader's encoding choice. Label bytes are recovered with
`s.encode("latin-1")`. Numeric columns are plain ASCII, so the choice does not affect them.
Only counts and small examples are kept in memory.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from datalens.ingestion.verify import discover_files
from datalens.preprocessing.labels import build_label_mapping, clean_label

UTF8_REPLACEMENT = b"\xef\xbf\xbd"


# --------------------------------------------------------------------------- C. label bytes
def classify_label_bytes(raw: bytes) -> str:
    """Name the kind of non-ASCII content in a label's raw bytes."""
    if all(b < 128 for b in raw):
        return "ascii"
    if UTF8_REPLACEMENT in raw:
        return "utf8_replacement_char_in_file"   # information already lost inside the file
    if b"\xe2\x80\x93" in raw or b"\xe2\x80\x94" in raw:
        return "utf8_dash"
    if b"\x96" in raw or b"\x97" in raw:
        return "cp1252_dash_byte"
    return "other_non_ascii"


def decode_candidates(raw: bytes) -> dict[str, str]:
    """How each candidate encoding would render these bytes (shows what a loader could introduce)."""
    return {
        "utf-8(replace)": raw.decode("utf-8", errors="replace"),
        "cp1252(replace)": raw.decode("cp1252", errors="replace"),
        "latin-1": raw.decode("latin-1"),
    }


def best_decode(raw: bytes) -> str:
    """Strict UTF-8, else cp1252 (replace for its 5 undefined bytes): mirrors the loader's order."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def clean_label_series(series: pd.Series) -> np.ndarray:
    """Labels read as latin-1 -> true text (loader-style decode of the original bytes) -> clean label.

    Required because the files are read as latin-1: a UTF-8 replacement character (EF BF BD)
    would otherwise appear as three unrelated characters and split one class into two.
    """
    s = series.astype(str)
    mapping = {u: clean_label(best_decode(u.encode("latin-1"))) for u in s.unique()}
    return s.map(mapping).to_numpy()


def inspect_label_bytes(path: str | Path, label_column: str = "Label", chunk_size: int = 200_000) -> list[dict[str, Any]]:
    """Distinct raw label byte-strings in one file, with counts and classification."""
    counts: Counter = Counter()
    for chunk in pd.read_csv(path, usecols=lambda c: str(c).strip() == label_column,
                             encoding="latin-1", chunksize=chunk_size, dtype=str):
        counts.update(chunk.iloc[:, 0].fillna("<NA>").value_counts().to_dict())
    out = []
    for raw_latin1, n in counts.items():
        raw = raw_latin1.encode("latin-1")
        out.append({
            "file": Path(path).name, "raw_bytes_hex": raw.hex(), "raw_latin1": raw_latin1,
            "kind": classify_label_bytes(raw), "rows": int(n), "decodings": decode_candidates(raw),
            "loader_style_decoding": best_decode(raw),
        })
    return sorted(out, key=lambda r: -r["rows"])


def label_encoding_report(per_file: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Combine per-file label inspections into answers to the label-encoding questions."""
    records = [r for f in per_file for r in f]
    by_bytes: dict[str, int] = defaultdict(int)
    for r in records:
        by_bytes[r["raw_bytes_hex"]] += r["rows"]
    decoded_counts = pd.Series({bytes.fromhex(h).decode("latin-1"): n for h, n in by_bytes.items()}).sort_values(ascending=False)
    # Use the loader-style decoding for identity analysis.
    loader_counts: dict[str, int] = defaultdict(int)
    for h, n in by_bytes.items():
        loader_counts[best_decode(bytes.fromhex(h))] += n
    mapping, mapping_report = build_label_mapping(pd.Series(loader_counts).sort_values(ascending=False))
    kinds = Counter(r["kind"] for r in records)
    non_ascii = [r for r in records if r["kind"] != "ascii"]
    return {
        "n_distinct_raw_byte_labels": len(by_bytes),
        "kinds_found": dict(kinds),
        "original_files_contain_utf8_replacement_char": any(r["kind"] == "utf8_replacement_char_in_file" for r in records),
        "non_ascii_labels": [{k: r[k] for k in ("file", "raw_bytes_hex", "kind", "rows", "decodings", "loader_style_decoding")}
                             for r in non_ascii],
        "distinct_raw_forms_per_clean_label": {c: raws for c, raws in mapping_report["merged_groups"].items()},
        "class_counts_split_by_inconsistent_encoding": bool(mapping_report["merged_groups"]),
        "similar_not_merged": mapping_report["similar_not_merged"],
        "clean_label_counts": mapping_report["clean_counts"],
        "interpretation_hint": (
            "If kind is 'cp1252_dash_byte', the file stores a single byte 0x96; the replacement "
            "character only appears when a reader decodes it wrongly (the loader decodes cp1252). "
            "If kind is 'utf8_replacement_char_in_file', the character is baked into the file."
        ),
    }


# --------------------------------------------------------------------------- A/B. missing + inf
def _feature_columns(columns, label_column: str) -> list[str]:
    return [str(c).strip() for c in columns if str(c).strip() != label_column]


def scan_missing_inf(
    path: str | Path, label_column: str = "Label", chunk_size: int = 200_000, max_examples: int = 20,
    duration_column: str = "Flow Duration",
) -> dict[str, Any]:
    """Missing and infinite cells by column and class for ONE file, streaming."""
    path = Path(path)
    rows = 0
    nan_c: Counter = Counter()
    pinf_c: Counter = Counter()
    ninf_c: Counter = Counter()
    unparse_c: Counter = Counter()
    inf_zero_dur: Counter = Counter()
    by_label_rows: Counter = Counter()
    by_label_rows_inf: Counter = Counter()
    by_label_rows_nan: Counter = Counter()
    by_label_col_inf: Counter = Counter()
    by_label_col_nan: Counter = Counter()
    examples: list[dict[str, Any]] = []
    cols: list[str] | None = None

    for chunk in pd.read_csv(path, chunksize=chunk_size, encoding="latin-1", low_memory=False):
        chunk.columns = [str(c).strip() for c in chunk.columns]
        if label_column not in chunk.columns:
            raise ValueError(f"{path.name}: label column '{label_column}' not found")
        cols = _feature_columns(chunk.columns, label_column)
        labels = pd.Series(clean_label_series(chunk[label_column]))
        num = {}
        for c in cols:
            s = chunk[c]
            if not pd.api.types.is_numeric_dtype(s):
                coerced = pd.to_numeric(s, errors="coerce")
                unparse_c[c] += int((coerced.isna() & s.notna()).sum())
                s = coerced
            num[c] = s.to_numpy(dtype=float)
        A = np.column_stack([num[c] for c in cols])
        nan_m, pinf_m, ninf_m = np.isnan(A), np.isposinf(A), np.isneginf(A)
        inf_m = pinf_m | ninf_m
        for j, c in enumerate(cols):
            nan_c[c] += int(nan_m[:, j].sum())
            pinf_c[c] += int(pinf_m[:, j].sum())
            ninf_c[c] += int(ninf_m[:, j].sum())
        zero_dur = (num[duration_column] == 0) if duration_column in num else None
        if zero_dur is not None:
            for j, c in enumerate(cols):
                if inf_m[:, j].any():
                    inf_zero_dur[c] += int((inf_m[:, j] & zero_dur).sum())
        row_inf, row_nan = inf_m.any(axis=1), nan_m.any(axis=1)
        lab = labels.to_numpy()
        by_label_rows.update(Counter(lab))
        by_label_rows_inf.update(Counter(lab[row_inf]))
        by_label_rows_nan.update(Counter(lab[row_nan]))
        for mask, acc in ((inf_m, by_label_col_inf), (nan_m, by_label_col_nan)):
            g = pd.DataFrame(mask, columns=cols).groupby(lab).sum()
            for label, r in g.iterrows():
                for c, v in r[r > 0].items():
                    acc[(label, c)] += int(v)
        for i in np.flatnonzero(row_inf | row_nan):
            if len(examples) >= max_examples:
                break
            examples.append({
                "csv_line": int(rows + i + 2), "label": lab[i],
                "inf_columns": [cols[j] for j in np.flatnonzero(inf_m[i])],
                "nan_columns": [cols[j] for j in np.flatnonzero(nan_m[i])],
            })
        rows += len(chunk)

    return {
        "file": path.name, "rows": rows, "n_feature_columns": len(cols or []),
        "nan_by_column": {c: n for c, n in nan_c.items() if n},
        "pos_inf_by_column": {c: n for c, n in pinf_c.items() if n},
        "neg_inf_by_column": {c: n for c, n in ninf_c.items() if n},
        "unparseable_by_column": {c: n for c, n in unparse_c.items() if n},
        "inf_cells_with_zero_flow_duration": dict(inf_zero_dur),
        "rows_by_class": dict(by_label_rows),
        "rows_with_inf_by_class": dict(by_label_rows_inf),
        "rows_with_nan_by_class": dict(by_label_rows_nan),
        "inf_cells_by_class_column": {f"{l}|{c}": n for (l, c), n in by_label_col_inf.items()},
        "nan_cells_by_class_column": {f"{l}|{c}": n for (l, c), n in by_label_col_nan.items()},
        "examples": examples,
    }


def combine_missing_inf(per_file: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-file scans into dataset-level tables."""
    def total(key):
        acc: Counter = Counter()
        for f in per_file:
            acc.update(f[key])
        return dict(acc)
    rows_by_class = total("rows_by_class")
    inf_rows = total("rows_with_inf_by_class")
    nan_rows = total("rows_with_nan_by_class")
    pos, neg = total("pos_inf_by_column"), total("neg_inf_by_column")
    return {
        "rows": sum(f["rows"] for f in per_file),
        "total_nan_cells": sum(total("nan_by_column").values()),
        "total_pos_inf_cells": sum(pos.values()), "total_neg_inf_cells": sum(neg.values()),
        "nan_by_column": total("nan_by_column"),
        "pos_inf_by_column": pos, "neg_inf_by_column": neg,
        "unparseable_by_column": total("unparseable_by_column"),
        "inf_cells_with_zero_flow_duration": total("inf_cells_with_zero_flow_duration"),
        "by_file": {f["file"]: {
            "rows": f["rows"], "nan_cells": sum(f["nan_by_column"].values()),
            "inf_cells": sum(f["pos_inf_by_column"].values()) + sum(f["neg_inf_by_column"].values()),
        } for f in per_file},
        "by_class": {c: {"rows": n, "rows_with_inf": inf_rows.get(c, 0), "rows_with_nan": nan_rows.get(c, 0),
                         "pct_rows_with_inf": round(100 * inf_rows.get(c, 0) / n, 4),
                         "pct_rows_with_nan": round(100 * nan_rows.get(c, 0) / n, 4)}
                     for c, n in sorted(rows_by_class.items(), key=lambda kv: -kv[1])},
        "inf_cells_by_class_column": total("inf_cells_by_class_column"),
        "nan_cells_by_class_column": total("nan_cells_by_class_column"),
        "examples": [dict(e, file=f["file"]) for f in per_file for e in f["examples"]][:50],
    }


# --------------------------------------------------------------------------- D. duplicates
def duplicate_stats_from_hashes(h: np.ndarray, labels: np.ndarray, sources: np.ndarray) -> dict[str, Any]:
    """Duplicate statistics from per-row feature hashes (h), clean labels and source files."""
    df = pd.DataFrame({"h": h, "label": labels, "src": sources})
    n = len(df)
    exact = df.duplicated(["h", "label"])                      # repeat of an earlier row (any file)
    exact_within = df.duplicated(["h", "label", "src"])        # repeat inside the same file
    labels_per_h = df.groupby("h")["label"].nunique()
    conflict_h = labels_per_h[labels_per_h > 1].index
    conflict = df["h"].isin(conflict_h)
    files_per_h = df.groupby("h")["src"].nunique()
    span_h = files_per_h[files_per_h > 1].index
    spanning = df["h"].isin(span_h)
    span_conflict_h = df[spanning].groupby("h")["label"].nunique()
    per_class = pd.DataFrame({"label": df["label"], "exact": exact, "conflict": conflict, "spanning": spanning}) \
        .groupby("label").agg(rows=("exact", "size"), exact_duplicate_rows=("exact", "sum"),
                              rows_in_label_conflicts=("conflict", "sum"), rows_in_cross_file_vectors=("spanning", "sum"))
    per_class["pct_removed_by_drop_exact"] = (100 * per_class["exact_duplicate_rows"] / per_class["rows"]).round(3)
    return {
        "rows": n,
        "exact_duplicate_rows_global": int(exact.sum()),
        "exact_duplicate_rows_within_file": int(exact_within.sum()),
        "exact_duplicates_only_across_files": int(exact.sum() - exact_within.sum()),
        "label_conflict_groups": int(len(conflict_h)), "label_conflict_rows": int(conflict.sum()),
        "vectors_spanning_multiple_files": int(len(span_h)), "rows_in_spanning_vectors": int(spanning.sum()),
        "spanning_vectors_with_label_disagreement": int((span_conflict_h > 1).sum()),
        "per_class": {c: {k: (float(v) if "pct" in k else int(v)) for k, v in r.items()} for c, r in per_class.iterrows()},
    }


def scan_duplicates(paths: list[Path], label_column: str = "Label", chunk_size: int = 200_000) -> dict[str, Any]:
    """Hash feature vectors file by file (streaming) and compute duplicate statistics."""
    hs, labs, srcs = [], [], []
    for p in paths:
        for chunk in pd.read_csv(p, chunksize=chunk_size, encoding="latin-1", low_memory=False):
            chunk.columns = [str(c).strip() for c in chunk.columns]
            cols = _feature_columns(chunk.columns, label_column)
            hs.append(pd.util.hash_pandas_object(chunk[cols], index=False).to_numpy())
            labs.append(clean_label_series(chunk[label_column]))
            srcs.append(np.full(len(chunk), p.name, dtype=object))
    return duplicate_stats_from_hashes(np.concatenate(hs), np.concatenate(labs), np.concatenate(srcs))


# --------------------------------------------------------------------------- driver
def investigate_dataset(raw_dir: str | Path, pattern: str = "*.csv", label_column: str = "Label",
                        chunk_size: int = 200_000) -> dict[str, Any]:
    """Run all four investigations over every file, streaming."""
    files = discover_files(raw_dir, pattern)
    return {
        "files": [f.name for f in files],
        "label_encoding": label_encoding_report([inspect_label_bytes(f, label_column, chunk_size) for f in files]),
        "missing_and_infinite": combine_missing_inf([scan_missing_inf(f, label_column, chunk_size) for f in files]),
        "duplicates": scan_duplicates(files, label_column, chunk_size),
    }
