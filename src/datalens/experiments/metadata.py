"""Experiment (run) metadata: everything needed to reproduce and audit a preparation run.

The run_id is a deterministic hash of the inputs that define the run (configuration, dataset
fingerprint, sampling fraction, seed, strategy). Re-running with the same inputs yields the same
id; changing any of them changes it. Wall-clock time is recorded separately and is NOT part of
the id.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from datalens import __version__
from datalens.config import PROJECT_ROOT

REQUIRED_KEYS = (
    "run_id", "created_utc", "run_kind", "strategy", "code", "hardware", "dataset", "cleaning", "split",
    "preprocessing", "features", "class_imbalance", "results", "config_snapshot", "reproduce",
)


def to_jsonable(obj: Any) -> Any:
    """Convert numpy/pandas/Path/set values into plain JSON types (recursively)."""
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in (sorted(obj, key=str) if isinstance(obj, set) else obj)]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def config_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(to_jsonable(obj), sort_keys=True, default=str).encode()).hexdigest()[:16]


def make_run_id(config_snapshot: dict, dataset_fingerprint: str, sample_fraction: float | None, seed: int, strategy: str) -> str:
    payload = {"config": config_snapshot, "fingerprint": dataset_fingerprint, "sample_fraction": sample_fraction,
               "seed": seed, "strategy": strategy}
    return config_hash(payload)[:12]


def get_git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def library_versions() -> dict[str, str]:
    import pandas, sklearn, sys
    return {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pandas.__version__,
            "scikit-learn": sklearn.__version__}


def build_run_metadata(
    strategy: str, cfg: dict[str, Any], dataset_meta: dict[str, Any], label_report: dict[str, Any],
    duplicate_report: dict[str, Any], split_meta: dict[str, Any], fit_record: dict[str, Any],
    feature_meta: dict[str, Any], handling: dict[str, Any], imbalance: dict[str, Any],
    transformed: dict[str, Any], hardware: dict[str, Any], timings: dict[str, float],
    effective_preprocessing: dict[str, Any], command: str = "python scripts/prepare_dataset.py",
) -> dict[str, Any]:
    """Assemble the full, JSON-safe record of one preparation run."""
    seed = int(dataset_meta["random_seed"])
    run_id = make_run_id(cfg, dataset_meta["fingerprint"], dataset_meta["sample_fraction"], seed, strategy)
    num = effective_preprocessing["numeric"]
    meta = {
        "run_id": run_id,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "run_kind": "phase3_preparation",
        "strategy": strategy,
        "code": {"git_commit": get_git_commit(), "datalens_version": __version__, "libraries": library_versions()},
        "hardware": hardware,
        "dataset": {
            "fingerprint": dataset_meta["fingerprint"],
            "fingerprint_includes_content_hash": dataset_meta["fingerprint_includes_content_hash"],
            "source_files": [f["file"] for f in dataset_meta["files"]],
            "rows_in_files": dataset_meta["rows_in_files"],
            "rows_loaded": dataset_meta["rows_loaded"],
            "sample_fraction": dataset_meta["sample_fraction"],
            "is_full_dataset": dataset_meta["is_full_dataset"],
            "random_seed": seed,
            "rows_after_cleaning": duplicate_report["rows_after"],
        },
        "cleaning": {"label_canonicalization": label_report, "duplicates": duplicate_report},
        "split": {
            "strategy": split_meta["strategy"], "n_train": split_meta["n_train"], "n_test": split_meta["n_test"],
            "train_distribution": split_meta["train_distribution"], "test_distribution": split_meta["test_distribution"],
            "full_metadata": split_meta,
        },
        "preprocessing": {
            "effective_config": effective_preprocessing,
            "inf_handling": num["inf_strategy"], "imputation": {"numeric": num["imputer"],
                                                                 "categorical": effective_preprocessing["categorical"]["imputer"]},
            "missing_indicator": num["missing_indicator"],
            "encoding": f"one-hot (handle_unknown={effective_preprocessing['categorical']['handle_unknown']})",
            "scaling": num["scaler"],
            "duplicate_treatment": duplicate_report["policy"],
            "fit": fit_record,
        },
        "features": {
            "original_features": feature_meta["original_features"], "excluded_features": feature_meta["excluded_features"],
            "modeling_features": feature_meta["modeling_features"], "n_transformed": len(feature_meta.get("transformed_features", [])),
            "selected_features": feature_meta.get("selected_features"),
        },
        "class_imbalance": {k: imbalance[k] for k in ("n_rows", "n_classes", "majority_class", "majority_percent",
                                                      "overall_imbalance_ratio", "minority_classes")},
        "results": {"handling": handling, "transformed_summary": transformed, "timings_seconds": timings},
        "config_snapshot": to_jsonable(cfg),
        "reproduce": {
            "command": command,
            "notes": "Same raw files (check the fingerprint), same config_snapshot, same sampling fraction and seed "
                     "reproduce this run; the run_id is a hash of exactly those inputs.",
        },
    }
    return to_jsonable(meta)


def write_run_metadata(meta: dict[str, Any], out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"phase3_{meta['strategy']}_{meta['run_id']}.json"
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path
