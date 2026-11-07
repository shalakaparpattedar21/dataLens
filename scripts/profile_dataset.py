"""CLI: load the raw dataset, profile it, assess quality and write reports.

Usage:
    python scripts/profile_dataset.py                       # full dataset
    python scripts/profile_dataset.py --sample-fraction 0.1 # development sample (recorded in outputs)
    python scripts/profile_dataset.py --raw-dir DIR --out-dir DIR
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from datalens.config import load_config, resolve_path
from datalens.ingestion.loader import load_dataset
from datalens.profiling import profile_dataframe
from datalens.quality import assess_quality, summarize_findings
from datalens.reporting import write_quality_outputs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--sample-fraction", type=float, default=None,
                    help="Override ingestion.sample_fraction (0 < f <= 1)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    logging.basicConfig(level=cfg["logging"]["level"], format="%(levelname)s %(message)s")
    ing = cfg["ingestion"]
    frac = args.sample_fraction if args.sample_fraction is not None else ing["sample_fraction"]
    raw_dir = resolve_path(args.raw_dir or cfg["paths"]["raw_dir"])
    out_dir = resolve_path(args.out_dir or cfg["paths"]["tables_dir"])

    t0 = time.perf_counter()
    try:
        df, meta = load_dataset(
            raw_dir, pattern=ing["file_glob"], label_column=ing["label_column"],
            source_column=ing["source_column"], chunk_size=ing["chunk_size"],
            sample_fraction=frac, seed=cfg["project"]["random_seed"],
            encodings=tuple([ing["encoding"], *ing["fallback_encodings"]]),
            compute_hash=ing["compute_hash"],
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    meta["load_seconds"] = round(time.perf_counter() - t0, 2)

    t1 = time.perf_counter()
    profile = profile_dataframe(
        df, ing["label_column"], source_column=ing["source_column"],
        iqr_factor=cfg["profiling"]["outlier_iqr_factor"],
    )
    meta["profile_seconds"] = round(time.perf_counter() - t1, 2)

    findings = assess_quality(profile, cfg["quality"], cfg["profiling"], meta)
    paths = write_quality_outputs(profile, findings, meta, out_dir)

    print(f"\nRows analysed: {meta['rows_loaded']:,} of {meta['rows_in_files']:,} "
          f"(full dataset: {meta['is_full_dataset']})  load {meta['load_seconds']}s  "
          f"profile {meta['profile_seconds']}s  memory {profile['memory_mb']} MB")
    print(f"Fingerprint: {meta['fingerprint']}")
    print("\nFindings per dimension x severity:")
    print(summarize_findings(findings).to_string())
    print("\nWritten:")
    for p in paths.values():
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
