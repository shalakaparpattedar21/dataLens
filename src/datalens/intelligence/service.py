"""Orchestration and persistence for analyses. Results live in ``datasets/<id>/analysis/<kind>.json`` so that
deleting a dataset removes them, and a prepared run's leakage report lives beside its manifest."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from datalens.app_service import DatasetStore, utc_now
from datalens.intelligence.anomalies import run_anomaly_detection
from datalens.intelligence.distributions import compute_distributions
from datalens.intelligence.health import compute_health
from datalens.intelligence.leakage import run_leakage, source_leakage
from datalens.intelligence.recommendations import build_recommendations
from datalens.intelligence.relationships import compute_relationships
from datalens.intelligence.sampling import load_sample

KINDS = ("distributions", "relationships", "leakage", "anomalies", "health", "recommendations", "run_leakage")
HISTORY_LIMIT = 50
Progress = Callable[[float, str], None]


def _dir(store: DatasetStore, dataset_id: str) -> Path:
    path = store.datasets / dataset_id / "analysis"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(store: DatasetStore, dataset_id: str, kind: str, payload: dict[str, Any]) -> None:
    path = _dir(store, dataset_id) / f"{kind}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def load(store: DatasetStore, dataset_id: str, kind: str) -> dict[str, Any] | None:
    path = store.datasets / dataset_id / "analysis" / f"{kind}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_all(store: DatasetStore, dataset_id: str) -> dict[str, Any]:
    out = {k: load(store, dataset_id, k) for k in KINDS if k != "run_leakage"}
    out["health_history"] = (load(store, dataset_id, "health_history") or {}).get("snapshots", [])
    return out


def latest_run(store: DatasetStore, dataset_id: str) -> dict[str, Any] | None:
    runs = []
    for path in (store.prepared / dataset_id).glob("*/manifest.json"):
        try:
            runs.append((path.stat().st_mtime_ns, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    # created_at has one-second resolution, so the manifest write time breaks ties between quick successive runs
    return max(runs, key=lambda r: (r[1].get("created_at", ""), r[0]), default=(0, None))[1]


def run_dir(store: DatasetStore, run: dict[str, Any]) -> Path:
    return store.prepared / run["dataset_id"] / run["id"]


def refresh_scores(store: DatasetStore, dataset_id: str) -> dict[str, Any]:
    """Recompute recommendations and health from stored findings; append a health snapshot."""
    record = store.get(dataset_id)
    if record is None:
        raise ValueError("Dataset not found")
    profile = record.get("profile")
    reports = [r for r in (load(store, dataset_id, "leakage"),) if r]
    run = latest_run(store, dataset_id)
    if run and (run_dir(store, run) / "leakage_report.json").is_file():
        rl = json.loads((run_dir(store, run) / "leakage_report.json").read_text(encoding="utf-8"))
        reports.append(rl)
    distributions, relationships = load(store, dataset_id, "distributions"), load(store, dataset_id, "relationships")
    recs = build_recommendations(profile, distributions, relationships, reports)
    health = compute_health(profile, distributions, reports, run, utc_now())
    save(store, dataset_id, "recommendations", recs)
    save(store, dataset_id, "health", health)
    history = (load(store, dataset_id, "health_history") or {}).get("snapshots", [])
    if health["overall"] is not None:
        history.append({"created_at": health["created_at"], "overall": health["overall"],
                        "dimensions": {d["name"]: d["score"] for d in health["dimensions"]}, "run_id": (run or {}).get("id")})
        save(store, dataset_id, "health_history", {"snapshots": history[-HISTORY_LIMIT:]})
    return {"health": health, "recommendations": recs}


def _sample(record: dict[str, Any], seed: int):
    profile = record["profile"]
    return load_sample([Path(p) for p in record["files"]], int(profile["rows"]), seed=seed)


def run_analysis(store: DatasetStore, record: dict[str, Any], options: dict[str, Any], progress: Progress) -> dict[str, Any]:
    profile = record.get("profile")
    if not profile:
        raise ValueError("Profile this dataset before analysing it")
    seed = int(options.get("seed", 42))
    target = options.get("target_column") or profile.get("label_column")
    if target and target not in profile["column_names"]:
        raise ValueError(f"Target column '{target}' was not found in the dataset")
    progress(0.05, "Sampling rows")
    frame, info = _sample(record, seed)
    dataset_id = record["id"]
    progress(0.25, "Distributions")
    save(store, dataset_id, "distributions", compute_distributions(frame, target, info))
    progress(0.40, "Feature relationships")
    save(store, dataset_id, "relationships", compute_relationships(frame, target, info, seed))
    progress(0.65, "Leakage checks")
    save(store, dataset_id, "leakage", {**source_leakage(frame, target, info, profile, seed, float(options.get("test_size", 0.2))),
                                        "created_at": utc_now()})
    progress(0.80, "Anomaly detection")
    anomaly_options = {k: v for k, v in (options.get("anomaly") or {}).items() if v is not None}
    save(store, dataset_id, "anomalies", {**run_anomaly_detection(frame, target, info, seed=seed, **anomaly_options), "created_at": utc_now()})
    progress(0.95, "Health score and recommendations")
    refresh_scores(store, dataset_id)
    return {"dataset_id": dataset_id, "analyses": ["distributions", "relationships", "leakage", "anomalies", "health", "recommendations"],
            "rows_sampled": info["rows_sampled"]}


def run_anomalies(store: DatasetStore, record: dict[str, Any], options: dict[str, Any], progress: Progress) -> dict[str, Any]:
    profile = record.get("profile")
    if not profile:
        raise ValueError("Profile this dataset before analysing it")
    seed = int(options.get("seed", 42))
    target = options.get("target_column") or profile.get("label_column")
    progress(0.1, "Sampling rows")
    frame, info = _sample(record, seed)
    progress(0.4, "Detecting anomalies")
    opts = {k: options[k] for k in ("method", "contamination", "features", "max_rows") if options.get(k) is not None}
    result = run_anomaly_detection(frame, target, info, seed=seed, **opts)
    save(store, record["id"], "anomalies", {**result, "created_at": utc_now()})
    return {"dataset_id": record["id"], "flagged": result["summary"]["flagged"]}


def run_leakage_for_run(store: DatasetStore, manifest: dict[str, Any], threshold: float, seed: int, progress: Progress) -> dict[str, Any]:
    progress(0.1, "Checking train/test overlap and near-duplicates")
    folder = run_dir(store, manifest)
    report = run_leakage(folder, manifest, threshold, seed)
    report["created_at"] = utc_now()
    (folder / "leakage_report.json").write_text(json.dumps(report), encoding="utf-8")
    progress(0.9, "Updating health score")
    if store.get(manifest["dataset_id"]) and (store.get(manifest["dataset_id"]) or {}).get("profile"):
        refresh_scores(store, manifest["dataset_id"])
    return {"run_id": manifest["id"], "findings": len(report["findings"])}


def safe_kind(kind: str) -> bool:
    return bool(re.fullmatch(r"[a-z_]+", kind)) and kind in KINDS
