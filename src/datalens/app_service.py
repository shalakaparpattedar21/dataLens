from __future__ import annotations

import codecs
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
WORKSPACE = Path(os.environ.get("DATALENS_WORKSPACE", PROJECT_ROOT / "data" / "workspace")).resolve()
DATASETS_DIR = WORKSPACE / "datasets"
PREPARED_DIR = WORKSPACE / "prepared"
CHUNK_ROWS = 50_000
PROFILE_SAMPLE_ROWS = 30_000
RARE_CLASS_ROWS = 100
IDENTIFIER_TOKENS = {"id", "ip", "port", "timestamp", "time", "date", "mac", "uuid"}


def _name_tokens(name: str) -> set[str]:
    """Lower-case word tokens of a column name ('Destination Port' -> {'destination', 'port'})."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))
    return {t for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if t}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in " ._-()")
    return cleaned.strip(" .")[:120] or "dataset.csv"


class DatasetStore:
    def __init__(self, root: Path = WORKSPACE):
        self.root = root
        self.datasets = root / "datasets"
        self.prepared = root / "prepared"
        self.datasets.mkdir(parents=True, exist_ok=True)
        self.prepared.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self, dataset_id: str) -> Path:
        if not dataset_id or any(c not in "0123456789abcdef-" for c in dataset_id.lower()):
            raise ValueError("Invalid dataset id")
        return self.datasets / dataset_id / "dataset.json"

    def _write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        tmp.replace(path)

    def create_upload(self, filename: str, source: Path, size_bytes: int) -> dict[str, Any]:
        dataset_id = str(uuid.uuid4())
        name = _safe_name(filename)
        folder = self.datasets / dataset_id
        folder.mkdir(parents=True, exist_ok=False)
        destination = folder / name
        if source.resolve() != destination.resolve():
            source.replace(destination)
        record = {
            "id": dataset_id, "name": Path(name).stem, "created_at": utc_now(),
            "kind": "upload", "files": [str(destination)],
            "file_names": [name], "size_bytes": int(size_bytes), "profile": None,
        }
        self._write(folder / "dataset.json", record)
        return record

    def register_local(self, files: list[Path], name: str) -> dict[str, Any]:
        dataset_id = str(uuid.uuid4())
        record = {
            "id": dataset_id, "name": name, "created_at": utc_now(), "kind": "local_read_only",
            "files": [str(p.resolve()) for p in files], "file_names": [p.name for p in files],
            "size_bytes": sum(p.stat().st_size for p in files), "profile": None,
        }
        self._write(self._manifest_path(dataset_id), record)
        return record

    def get(self, dataset_id: str) -> dict[str, Any] | None:
        try:
            path = self._manifest_path(dataset_id)
        except ValueError:  # malformed id: treat as "not found" instead of failing the request
            return None
        if not path.is_file():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if any(not Path(p).is_file() for p in record.get("files", [])):
            record["source_status"] = "missing"
        else:
            record["source_status"] = "available"
        return record

    def save(self, record: dict[str, Any]) -> None:
        self._write(self._manifest_path(record["id"]), record)

    def find_local(self, files: list[Path]) -> dict[str, Any] | None:
        """Return an already-registered local dataset with exactly this set of source files."""
        wanted = sorted(str(p.resolve()) for p in files)
        for rec in self.list():
            if rec.get("kind") == "local_read_only" and sorted(rec.get("files", [])) == wanted:
                return rec
        return None

    def delete_dataset(self, dataset_id: str) -> bool:
        """Remove a dataset registration and its prepared outputs.

        Uploaded datasets own a copy of the CSV inside the workspace, and that copy is removed.
        Local (read-only) datasets only own a small manifest: the source CSV files they point to
        are NEVER touched.
        """
        if self.get(dataset_id) is None:
            return False
        for base in (self.datasets / dataset_id, self.prepared / dataset_id):
            if base.is_dir() and base.resolve().parent in (self.datasets.resolve(), self.prepared.resolve()):
                shutil.rmtree(base)
        return True

    def delete_preparation(self, run_id: str) -> bool:
        """Remove one prepared run (train/test/config/reports). Source datasets are untouched."""
        if not run_id or any(c not in "0123456789abcdefghijklmnopqrstuvwxyz-" for c in run_id.lower()):
            return False
        removed = False
        for folder in self.prepared.glob(f"*/{run_id}"):
            if folder.is_dir() and folder.resolve().parent.parent == self.prepared.resolve():
                shutil.rmtree(folder)
                removed = True
        return removed

    def list(self) -> list[dict[str, Any]]:
        records = []
        for path in self.datasets.glob("*/dataset.json"):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
                rec["source_status"] = "available" if all(Path(p).is_file() for p in rec["files"]) else "missing"
                records.append(rec)
            except (OSError, ValueError, KeyError):
                continue
        return sorted(records, key=lambda r: r.get("created_at", ""), reverse=True)


def validate_csv_upload(path: Path) -> None:
    """Cheap sanity check of an uploaded file (reads at most the first MiB). Raises ValueError.

    Rejects binary content, unparsable text and files with a header but no data rows, so a bad
    upload fails immediately with a clear message instead of failing later inside a job.
    """
    with path.open("rb") as stream:
        head = stream.read(1 << 20)
    if b"\x00" in head:
        raise ValueError("This does not look like a text CSV file (it contains binary data)")
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            sample = pd.read_csv(path, nrows=50, encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
        except pd.errors.EmptyDataError as exc:
            raise ValueError("The CSV has no header row") from exc
        except (pd.errors.ParserError, ValueError) as exc:
            raise ValueError(f"The CSV could not be parsed: {exc}") from exc
    else:  # pragma: no cover - latin-1 decodes every byte sequence
        raise ValueError(f"The CSV could not be decoded: {last_error}")
    if sample.shape[1] == 0:
        raise ValueError("The CSV has no columns")
    if sample.empty:
        raise ValueError("The CSV has a header but no data rows")


def _encoding_for(path: Path) -> str:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        with path.open("rb") as stream:
            while block := stream.read(1 << 20):
                decoder.decode(block, final=False)
            decoder.decode(b"", final=True)
        return "utf-8-sig"
    except UnicodeDecodeError:
        try:
            decoder = codecs.getincrementaldecoder("cp1252")("strict")
            with path.open("rb") as stream:
                while block := stream.read(1 << 20):
                    decoder.decode(block, final=False)
                decoder.decode(b"", final=True)
            return "cp1252"
        except UnicodeDecodeError:
            return "latin-1"


def _upsert_counts(conn: sqlite3.Connection, table: str, keys: list[str], values: list[tuple]) -> None:
    placeholders = ",".join("?" for _ in keys)
    key_columns = ",".join(keys[:-1])
    sql = (f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders}) "
           f"ON CONFLICT({key_columns}) DO UPDATE SET n=n+excluded.n")
    conn.executemany(sql, values)


def _duplicate_summary(conn: sqlite3.Connection, rows: int, n_files: int) -> dict[str, Any]:
    distinct_global = conn.execute("SELECT COUNT(*) FROM exact_counts").fetchone()[0]
    distinct_file = conn.execute("SELECT COUNT(*) FROM within_counts").fetchone()[0]
    spans = conn.execute("SELECT h FROM within_counts GROUP BY h HAVING COUNT(DISTINCT source)>1").fetchall()
    span_hashes = [row[0] for row in spans]
    if span_hashes:
        # Avoid SQLite's parameter limit by using a temporary join table.
        conn.execute("CREATE TEMP TABLE spanning(h TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO spanning VALUES (?)", [(h,) for h in span_hashes])
        span_rows = conn.execute("SELECT COALESCE(SUM(w.n),0) FROM within_counts w JOIN spanning s USING(h)").fetchone()[0]
        conflict_groups = conn.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT e.h FROM exact_counts e JOIN spanning s USING(h) "
            "GROUP BY e.h HAVING COUNT(*)>1)"
        ).fetchone()[0]
        per_file = dict(conn.execute(
            "SELECT w.source, COUNT(DISTINCT w.h) FROM within_counts w JOIN spanning s USING(h) GROUP BY w.source"
        ).fetchall())
    else:
        span_rows = conflict_groups = 0
        per_file = {}
    all_conflict = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total),0) FROM ("
        "SELECT h, SUM(n) total FROM exact_counts GROUP BY h HAVING COUNT(*)>1)"
    ).fetchone()
    return {
        "exact_duplicate_rows_global": int(rows - distinct_global),
        "exact_duplicate_rows_within_file": int(rows - distinct_file),
        "exact_duplicates_only_across_files": int((rows - distinct_global) - (rows - distinct_file)),
        "label_conflict_groups": int(all_conflict[0]),
        "label_conflict_rows": int(all_conflict[1]),
        "vectors_spanning_multiple_files": int(len(span_hashes)),
        "rows_in_spanning_vectors": int(span_rows),
        "spanning_vectors_with_label_disagreement": int(conflict_groups),
        "per_file_spanning_vectors": {str(k): int(v) for k, v in per_file.items()},
        "source_files": int(n_files),
    }


def profile_files(
    files: list[Path], label_column: str | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Profile one or more CSVs in bounded chunks; full-dataset counts remain exact."""
    if not files:
        raise ValueError("No CSV files were provided")
    rows = 0
    missing: Counter[str] = Counter()
    pos_inf: Counter[str] = Counter()
    neg_inf: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    first_value: dict[str, Any] = {}
    constant = {} 
    dtypes: dict[str, str] = {}
    schema = None
    sample_parts: list[pd.DataFrame] = []
    file_stats = []
    with tempfile.TemporaryDirectory(prefix="datalens-profile-") as tmp:
        conn = sqlite3.connect(Path(tmp) / "duplicates.sqlite")
        conn.execute("CREATE TABLE exact_counts(h TEXT,label TEXT,n INTEGER,PRIMARY KEY(h,label))")
        conn.execute("CREATE TABLE within_counts(h TEXT,label TEXT,source TEXT,n INTEGER,PRIMARY KEY(h,label,source))")
        total_chunks = max(1, sum(max(1, p.stat().st_size // (3 * 1024 * 1024)) for p in files))
        chunks_done = 0
        for file_index, path in enumerate(files):
            encoding = _encoding_for(path)
            local_rows = 0
            for chunk_index, chunk in enumerate(pd.read_csv(path, chunksize=CHUNK_ROWS, encoding=encoding, low_memory=False)):
                chunk.columns = [str(c).strip() for c in chunk.columns]
                if schema is None:
                    schema = list(chunk.columns)
                    if label_column is not None and label_column not in schema:
                        raise ValueError(f"Label column '{label_column}' was not found in {path.name}")
                    if label_column is None:
                        label_column = next((c for c in schema if c.lower() in {"label", "target", "class", "y"}), None)
                elif list(chunk.columns) != schema:
                    raise ValueError(f"{path.name}: columns differ from the first CSV")
                count = len(chunk)
                rows += count
                local_rows += count
                dtypes.update({c: str(chunk[c].dtype) for c in chunk.columns})
                for col in chunk.columns:
                    if col not in first_value:
                        first_value[col] = chunk[col].iloc[0] if count else None
                        constant[col] = True
                    if constant[col]:
                        initial = first_value[col]
                        same = chunk[col].isna() if pd.isna(initial) else chunk[col].eq(initial).fillna(False)
                        if not bool(same.all()):
                            constant[col] = False
                nulls = chunk.isna().sum()
                for col, value in nulls[nulls > 0].items():
                    missing[col] += int(value)
                numeric = chunk.select_dtypes(include=[np.number])
                if not numeric.empty:
                    pos_inf.update({c: int(np.isposinf(numeric[c].to_numpy()).sum()) for c in numeric.columns})
                    neg_inf.update({c: int(np.isneginf(numeric[c].to_numpy()).sum()) for c in numeric.columns})
                if label_column and label_column in chunk.columns:
                    label_counts.update(chunk[label_column].fillna("(missing)").astype(str).value_counts().to_dict())
                feature_cols = [c for c in chunk.columns if c != label_column] if label_column else list(chunk.columns)
                feature_hash = pd.util.hash_pandas_object(chunk[feature_cols], index=False).astype("uint64").map(lambda n: f"{int(n):016x}")
                labels = chunk[label_column].fillna("(missing)").astype(str) if label_column else pd.Series([""] * count)
                dup_frame = pd.DataFrame({"h": feature_hash, "label": labels, "source": path.name})
                global_groups = dup_frame.groupby(["h", "label"], sort=False).size().reset_index(name="n")
                file_groups = dup_frame.groupby(["h", "label", "source"], sort=False).size().reset_index(name="n")
                conn.executemany("INSERT INTO exact_counts VALUES (?,?,?) ON CONFLICT(h,label) DO UPDATE SET n=n+excluded.n",
                                 global_groups.itertuples(index=False, name=None))
                conn.executemany("INSERT INTO within_counts VALUES (?,?,?,?) ON CONFLICT(h,label,source) DO UPDATE SET n=n+excluded.n",
                                 file_groups.itertuples(index=False, name=None))
                # Deterministic bounded sample used only for approximate IQR outlier estimates.
                take = min(1_500, count)
                if take:
                    sample_parts.append(chunk.sample(n=take, random_state=7919 + file_index * 100_003 + chunk_index))
                chunks_done += 1
                if progress:
                    progress(min(0.94, chunks_done / total_chunks * 0.94), f"Scanned {rows:,} rows")
            file_stats.append({"name": path.name, "rows": local_rows, "size_bytes": path.stat().st_size})
        if schema is None:
            raise ValueError("The CSV files are empty")
        duplicates = _duplicate_summary(conn, rows, len(files))
        conn.close()
    profile_sample = pd.concat(sample_parts, ignore_index=True) if sample_parts else pd.DataFrame(columns=schema)
    if len(profile_sample) > PROFILE_SAMPLE_ROWS:
        profile_sample = profile_sample.sample(n=PROFILE_SAMPLE_ROWS, random_state=42)
    outliers = []
    numeric_sample = profile_sample.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)
    for col in numeric_sample.columns:
        values = numeric_sample[col].dropna()
        if len(values) < 4:
            continue
        q1, q3 = values.quantile([0.25, 0.75])
        spread = q3 - q1
        if spread <= 0:
            continue
        n_out = int(((values < q1 - 1.5 * spread) | (values > q3 + 1.5 * spread)).sum())
        if n_out:
            outliers.append({"column": col, "sample_outlier_rows": n_out, "sample_rows": int(len(values)),
                             "estimated_percent": round(100 * n_out / len(values), 3), "method": "IQR on deterministic sample"})
    dtype_map = dict(dtypes)
    type_rows = [{"column": c, "dtype": dtype_map.get(c, "unknown"), "constant": bool(constant.get(c, False)),
                  "missing_cells": int(missing.get(c, 0)), "positive_infinity_cells": int(pos_inf.get(c, 0)),
                  "negative_infinity_cells": int(neg_inf.get(c, 0))} for c in schema]
    top_missing = sorted(missing.items(), key=lambda item: item[1], reverse=True)
    issues = []
    for col, n in top_missing:
        pct = 100 * n / max(1, rows)
        issues.append({"severity": "warning", "title": "Missing values", "column": col, "count": int(n),
                       "explanation": f"{n:,} cells ({pct:.2f}% of rows) are empty.",
                       "recommendation": "Pick an imputation method on the Prepare page (median is robust to outliers). "
                                         "It is fitted on training rows only."})
    for col, n in (pos_inf + neg_inf).most_common():
        issues.append({"severity": "warning", "title": "Infinite values", "column": col, "count": int(n),
                       "explanation": "Infinite values break many estimators. They usually come from dividing by zero when "
                                      "the feature was computed (for example a rate over a zero duration).",
                       "recommendation": "DataLens converts them to missing and imputes them using training rows only. "
                                         "Also check how the source calculated this column."})
    if duplicates["exact_duplicate_rows_global"]:
        issues.append({"severity": "warning", "title": "Duplicate rows", "count": duplicates["exact_duplicate_rows_global"],
                       "explanation": "Rows repeating an earlier row exactly (features and label). If copies land in both "
                                      "train and test, test scores look better than they are.",
                       "recommendation": "Choose 'Remove global exact repeats' (or within-file) on the Prepare page. "
                                         "'Keep all' leaves them in and reports how many test rows also appear in train."})
    if duplicates["label_conflict_rows"]:
        issues.append({"severity": "warning", "title": "Conflicting labels", "count": duplicates["label_conflict_rows"],
                       "explanation": f"{duplicates['label_conflict_groups']:,} identical feature vectors carry more than one "
                                      f"label ({duplicates['label_conflict_rows']:,} rows). No model can separate them, so they "
                                      "set a floor on achievable error and may be label noise.",
                       "recommendation": "Inspect these rows at the source. DataLens keeps them: no duplicate policy removes them."})
    constants = [c for c, value in constant.items() if value]
    if constants:
        issues.append({"severity": "info", "title": "Constant columns", "count": len(constants), "columns": constants,
                       "explanation": "These columns have a single observed value and cannot distinguish records.",
                       "recommendation": "Choose 'Remove zero variance' under feature selection to drop them from the output."})
    if outliers:
        issues.append({"severity": "info", "title": "Potential outliers", "count": sum(o["sample_outlier_rows"] for o in outliers),
                       "explanation": "IQR flags unusual numeric values in a deterministic sample. Extreme values can be "
                                      "legitimate (bursts, attacks), so they are flagged, never removed.",
                       "recommendation": "Prefer robust scaling, or tree-based models that tolerate extremes."})
    identifier_like = [c for c in schema if c != label_column and _name_tokens(c) & IDENTIFIER_TOKENS]
    if identifier_like:
        issues.append({"severity": "info", "title": "Identifier-like columns", "count": len(identifier_like), "columns": identifier_like,
                       "explanation": "Names suggest identifiers, addresses, ports or timestamps. Such columns can reflect how "
                                      "the data was collected rather than real behaviour, and may act as shortcuts for a model.",
                       "recommendation": "Compare model results with and without them before relying on a score. "
                                         "DataLens does not remove them automatically."})
    if label_column and label_counts:
        class_total = sum(label_counts.values())
        majority = max(label_counts.values())
        if class_total and majority / class_total > 0.8:
            issues.append({"severity": "warning", "title": "Imbalanced target", "count": len(label_counts),
                           "explanation": f"'{max(label_counts, key=label_counts.get)}' is {majority / class_total:.1%} of rows, so accuracy alone is misleading.",
                           "recommendation": "Judge models by per-class recall and macro-F1. Check the class coverage warnings after preparation."})
        rare = sorted(((k, int(v)) for k, v in label_counts.items() if v < RARE_CLASS_ROWS and k != "(missing)"), key=lambda kv: kv[1])
        if rare:
            issues.append({"severity": "warning", "title": "Rare classes", "count": len(rare),
                           "classes": [{"label": k, "count": v} for k, v in rare[:25]],
                           "explanation": f"{len(rare)} class(es) have fewer than {RARE_CLASS_ROWS} rows. They may be absent from the "
                                          "train or test split, and their metrics will be unreliable.",
                           "recommendation": "Report such classes separately with their support instead of averaging them away."})
    elif not label_column:
        issues.append({"severity": "info", "title": "No target column detected", "count": 0,
                       "explanation": "No column named label, target, class or y was found.",
                       "recommendation": "Choose the target column yourself on the Prepare page, or prepare without a target."})
    return {
        "rows": rows, "columns": len(schema), "column_names": schema, "label_column": label_column,
        "dtypes": type_rows, "missing_cells": int(sum(missing.values())),
        "positive_infinity_cells": int(sum(pos_inf.values())), "negative_infinity_cells": int(sum(neg_inf.values())),
        "duplicate_rows": duplicates["exact_duplicate_rows_global"], "duplicates": duplicates,
        "constant_columns": constants, "outliers": outliers, "outlier_sample_rows": int(len(profile_sample)),
        "class_distribution": [{"label": k, "count": int(v), "percent": round(100 * v / max(1, sum(label_counts.values())), 4)}
                               for k, v in label_counts.most_common()],
        "issues": issues, "files": file_stats, "sampling": {"used": False, "profile_rows": rows},
        "created_at": utc_now(), "encoding_note": "CSV rows were scanned in chunks; label values are preserved as read.",
    }
