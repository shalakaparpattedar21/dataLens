"""CLI: verify raw dataset files and write a JSON verification report.

Usage:
    python scripts/verify_dataset.py
    python scripts/verify_dataset.py --raw-dir path/to/csvs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from datalens.config import load_config, resolve_path
from datalens.ingestion.verify import verify_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--raw-dir", default=None, help="Override raw data directory")
    args = parser.parse_args()

    cfg = load_config(args.config)
    logging.basicConfig(level=cfg["logging"]["level"], format="%(levelname)s %(message)s")
    ing = cfg["ingestion"]
    raw_dir = resolve_path(args.raw_dir or cfg["paths"]["raw_dir"])

    try:
        report = verify_dataset(
            raw_dir,
            pattern=ing["file_glob"],
            label_column=ing["label_column"],
            chunk_size=ing["chunk_size"],
            encodings=tuple([ing["encoding"], *ing["fallback_encodings"]]),
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nFiles: {report['n_files']}  (with errors: {report['n_files_with_errors']})")
    print(f"Total size: {report['total_size_mb']} MB   Total rows: {report['total_rows']:,}")
    print(f"Schema consistent across files: {report['schema_consistent_across_files']}")
    print(f"NaN cells: {report['total_nan_cells']:,}   inf cells: {report['total_inf_cells']:,}\n")
    print(f"{'file':<62}{'MB':>9}{'rows':>12}{'cols':>6}  enc")
    for r in report["files"]:
        print(f"{r['file']:<62}{r['size_mb']:>9}{r.get('rows', 0):>12,}{r.get('n_columns', 0):>6}  "
              f"{r.get('encoding', '-')}{'  ERROR: ' + r['error'] if r['error'] else ''}")
    print("\nLabel distribution (all files):")
    total = sum(report["label_counts"].values()) or 1
    for label, n in report["label_counts"].items():
        print(f"  {label:<35}{n:>10,}  {100 * n / total:6.3f}%")

    out = resolve_path(cfg["paths"]["tables_dir"]) / "dataset_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {out}")
    return 1 if report["n_files_with_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
