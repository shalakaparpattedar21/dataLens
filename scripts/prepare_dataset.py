"""CLI: Phase 3 data preparation (labels, duplicates, splits, features, leakage-safe preprocessing).

Usage:
    python scripts/prepare_dataset.py --sample-fraction 0.1      # development run (recorded everywhere)
    python scripts/prepare_dataset.py                            # FULL dataset (check RAM first)
    python scripts/prepare_dataset.py --strategies random        # or: day_aware
    python scripts/prepare_dataset.py --skip-quality

Outputs: reports/tables/phase3/** and experiments/phase3_<strategy>_<run_id>.json
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from datalens.config import load_config, resolve_path
from datalens.preparation import STRATEGIES, prepare_dataset
from datalens.resources import hardware_summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--out-dir", default=None, help="Default: paths.tables_dir from the config")
    ap.add_argument("--experiments-dir", default=None)
    ap.add_argument("--sample-fraction", type=float, default=None, help="0 < f <= 1; overrides ingestion.sample_fraction")
    ap.add_argument("--strategies", nargs="+", default=list(STRATEGIES), choices=STRATEGIES)
    ap.add_argument("--skip-quality", action="store_true", help="Skip the profiling/quality step (saves time and memory)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    logging.basicConfig(level=cfg["logging"]["level"], format="%(levelname)s %(message)s")
    frac = args.sample_fraction if args.sample_fraction is not None else cfg["ingestion"]["sample_fraction"]
    print(f"Hardware: {hardware_summary()}")
    print(f"Sample fraction: {frac}  ({'FULL dataset' if frac in (None, 1) else 'SAMPLE - not full-dataset results'})")
    t0 = time.perf_counter()
    try:
        res = prepare_dataset(
            cfg, resolve_path(args.raw_dir or cfg["paths"]["raw_dir"]), resolve_path(args.out_dir or cfg["paths"]["tables_dir"]),
            resolve_path(args.experiments_dir or cfg["paths"]["experiments_dir"]), tuple(args.strategies), frac,
            run_quality=not args.skip_quality, command=" ".join(["python", *sys.argv]),
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    d = res["dataset_meta"]
    print(f"\nDone in {time.perf_counter() - t0:.1f}s. Rows loaded {d['rows_loaded']:,} -> {res['duplicate_report']['rows_after']:,} after duplicate policy "
          f"(full dataset: {d['is_full_dataset']})")
    for name, r in res["strategies"].items():
        sp = r["split"]
        print(f"\n[{name}] run {r['run_id']}: train {r['n_train']:,} / test {r['n_test']:,}")
        if name == "day_aware":
            print(f"  test classes absent from training: {sp['classes_absent_from_train']}")
        else:
            print(f"  classes forced to train: {sp['classes_forced_to_train']}  unreliable test metrics: {sp['classes_with_unreliable_test_metrics']}")
        for k, p in r["paths"].items():
            print(f"  {k}: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
