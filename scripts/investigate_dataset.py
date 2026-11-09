"""CLI: investigate the raw dataset (label bytes, missing, inf, duplicates). Streams; low memory.

Usage:
    python scripts/investigate_dataset.py
    python scripts/investigate_dataset.py --raw-dir DIR --out-dir DIR

Outputs (reports/tables/): investigation_report.md, investigation.json and CSV tables.
Everything is computed over ALL rows of ALL files (no sampling).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from datalens.config import load_config, resolve_path
from datalens.profiling.investigate import investigate_dataset
from datalens.reporting.investigation_report import write_investigation_outputs
from datalens.resources import hardware_summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    logging.basicConfig(level=cfg["logging"]["level"], format="%(levelname)s %(message)s")
    ing = cfg["ingestion"]
    raw_dir = resolve_path(args.raw_dir or cfg["paths"]["raw_dir"])
    out_dir = resolve_path(args.out_dir or cfg["paths"]["tables_dir"])

    hw = hardware_summary()
    print(f"Hardware: {hw}")
    t0 = time.perf_counter()
    try:
        inv = investigate_dataset(raw_dir, ing["file_glob"], ing["label_column"], ing["chunk_size"])
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    paths = write_investigation_outputs(inv, out_dir, hw)

    le, mi, dup = inv["label_encoding"], inv["missing_and_infinite"], inv["duplicates"]
    print(f"\nScanned {mi['rows']:,} rows in {len(inv['files'])} files in {time.perf_counter() - t0:.1f}s (no sampling)")
    print(f"Label kinds: {le['kinds_found']}")
    print(f"Original files contain U+FFFD: {le['original_files_contain_utf8_replacement_char']}   "
          f"class counts split by encoding: {le['class_counts_split_by_inconsistent_encoding']}")
    print(f"NaN cells: {mi['total_nan_cells']:,}   +inf: {mi['total_pos_inf_cells']:,}   -inf: {mi['total_neg_inf_cells']:,}")
    print(f"Exact duplicate rows: {dup['exact_duplicate_rows_global']:,}   label-conflict rows: {dup['label_conflict_rows']:,}   "
          f"vectors spanning files: {dup['vectors_spanning_multiple_files']:,}")
    print("\nWritten:")
    for p in paths.values():
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
