from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from datalens.app_service import DEFAULT_RAW_DIR, DatasetStore, profile_files, utc_now, validate_csv_upload
from datalens.ingestion.verify import discover_files
from datalens.prepare_service import prepare_streaming

logger = logging.getLogger("datalens.api")

app = FastAPI(title="DataLens API", version="0.3.0", description="Local dataset profiling and preparation service")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False, allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"]
)
store = DatasetStore()
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="datalens-job")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class ProfileRequest(BaseModel):
    label_column: str | None = None


class PrepareRequest(BaseModel):
    target_column: str | None = None
    sample_fraction: float = Field(default=0.1, gt=0, le=1)
    test_size: float = Field(default=0.2, ge=0.05, le=0.5)
    seed: int = Field(default=42, ge=0)
    numeric_imputer: Literal["median", "mean", "most_frequent"] = "median"
    duplicate_policy: Literal["keep", "drop_within_file", "drop_exact"] = "keep"
    encoding: Literal["onehot", "ordinal"] = "onehot"
    scaler: Literal["robust", "standard", "minmax", "none"] = "robust"
    missing_indicator: bool = True
    feature_selection: Literal["none", "variance", "kbest_f"] = "none"
    selection_k: int = Field(default=30, ge=1, le=500)


def _start_job(dataset_id: str, kind: str, work):
    job_id = str(uuid.uuid4())
    job = {"id": job_id, "dataset_id": dataset_id, "kind": kind, "status": "queued", "progress": 0.0,
           "message": "Queued", "created_at": utc_now(), "result": None, "error": None}
    with _jobs_lock:
        _jobs[job_id] = job

    def report(progress: float, message: str) -> None:
        with _jobs_lock:
            current = _jobs.get(job_id)
            if current and current["status"] not in ("failed", "complete"):
                current.update(status="running", progress=max(0.0, min(1.0, float(progress))), message=message)

    def run():
        report(0.01, "Starting")
        try:
            result = work(report)
            with _jobs_lock:
                _jobs[job_id].update(status="complete", progress=1.0, message="Complete", result=result)
        except Exception as exc:
            # Full traceback goes to the server log; the UI gets a readable message.
            logger.exception("Job %s (%s) failed", job_id, kind)
            known = isinstance(exc, (ValueError, FileNotFoundError, RuntimeError))
            message = str(exc) if known and str(exc) else f"Unexpected {type(exc).__name__}: {exc}"
            with _jobs_lock:
                _jobs[job_id].update(status="failed", progress=1.0, message="Job failed", error=message)

    executor.submit(run)
    return job


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "DataLens", "workspace": str(store.root)}


@app.get("/api/datasets")
def list_datasets():
    return {"datasets": store.list()}


@app.post("/api/datasets/upload", status_code=201)
async def upload_dataset(request: Request, filename: str):
    safe = Path(filename.replace("\\", "/")).name
    if not safe.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV file")
    store.root.mkdir(parents=True, exist_ok=True)
    temp = store.root / f"upload-{uuid.uuid4().hex}.part"
    written = 0
    limit = 5 * 1024 * 1024 * 1024
    try:
        with temp.open("wb") as output:
            async for block in request.stream():
                written += len(block)
                if written > limit:
                    raise HTTPException(413, "CSV exceeds the 5 GB upload limit")
                output.write(block)
        if written == 0:
            raise HTTPException(400, "The uploaded file is empty")
        try:
            validate_csv_upload(temp)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        record = store.create_upload(safe, temp, written)
        return {"dataset": record}
    except Exception:
        temp.unlink(missing_ok=True)
        raise


@app.post("/api/datasets/import-cicids", status_code=201)
def import_local_cicids(response: Response):
    """Register the CSV files in data/raw. Idempotent: importing the same files again returns the existing dataset."""
    try:
        files = discover_files(DEFAULT_RAW_DIR, "*.csv")
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    existing = store.find_local(files)
    if existing is not None:
        response.status_code = 200
        return {"dataset": existing, "already_registered": True}
    record = store.register_local(files, "CIC-IDS2017 · local files")
    return {"dataset": record, "already_registered": False}


def _active_job_for(dataset_id: str) -> bool:
    with _jobs_lock:
        return any(j["dataset_id"] == dataset_id and j["status"] in ("queued", "running") for j in _jobs.values())


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    """Remove a dataset from the workspace. Source CSV files of local datasets are never deleted."""
    record = store.get(dataset_id)
    if record is None:
        raise HTTPException(404, "Dataset not found")
    if _active_job_for(dataset_id):
        raise HTTPException(409, "A job is still running for this dataset")
    store.delete_dataset(dataset_id)
    return {"deleted": dataset_id, "kind": record.get("kind")}


@app.delete("/api/preparations/{run_id}")
def delete_preparation(run_id: str):
    if not store.delete_preparation(run_id):
        raise HTTPException(404, "Preparation not found")
    return {"deleted": run_id}


@app.post("/api/datasets/{dataset_id}/profile", status_code=202)
def profile_dataset(dataset_id: str, body: ProfileRequest | None = None):
    body = body or ProfileRequest()
    record = store.get(dataset_id)
    if record is None:
        raise HTTPException(404, "Dataset not found")
    if record.get("source_status") != "available":
        raise HTTPException(410, "One or more source files are unavailable")
    def work(progress):
        profile = profile_files([Path(p) for p in record["files"]], body.label_column, progress)
        record["profile"] = profile
        store.save(record)
        return {"dataset_id": dataset_id, "rows": profile["rows"], "columns": profile["columns"]}
    job = _start_job(dataset_id, "profile", work)
    return {"job": job}


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    record = store.get(dataset_id)
    if record is None:
        raise HTTPException(404, "Dataset not found")
    return {"dataset": record}


@app.post("/api/datasets/{dataset_id}/prepare", status_code=202)
def prepare_dataset(dataset_id: str, body: PrepareRequest):
    record = store.get(dataset_id)
    if record is None:
        raise HTTPException(404, "Dataset not found")
    if record.get("source_status") != "available":
        raise HTTPException(410, "One or more source files are unavailable")
    if not record.get("profile"):
        raise HTTPException(409, "Profile this dataset before preparing it")
    if body.target_column and body.target_column not in record["profile"]["column_names"]:
        raise HTTPException(400, "The target column is not in the dataset")
    if body.feature_selection == "kbest_f" and not body.target_column:
        raise HTTPException(400, "Top k (ANOVA F) selection requires a target column")
    options = body.model_dump()
    job = _start_job(dataset_id, "prepare", lambda progress: prepare_streaming(record, options, store, progress))
    return {"job": job}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return {"job": dict(job)}


@app.get("/api/preparations")
def list_preparations():
    runs = []
    for path in store.prepared.glob("*/*/manifest.json"):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return {"preparations": sorted(runs, key=lambda x: x.get("created_at", ""), reverse=True)}


@app.get("/api/preparations/{run_id}/files/{name}")
def download_prepared_file(run_id: str, name: str):
    allowed = {"train.csv", "test.csv", "config.json", "quality_report.json", "quality_report.md", "comparison.json", "manifest.json"}
    if name not in allowed or not run_id or any(ch not in "0123456789abcdefghijklmnopqrstuvwxyz-" for ch in run_id.lower()):
        raise HTTPException(404, "File not found")
    matches = list(store.prepared.glob(f"*/{run_id}/{name}"))
    if not matches or not matches[0].is_file():
        raise HTTPException(404, "File not found")
    path = matches[0]
    media = "text/csv" if name.endswith(".csv") else "text/markdown" if name.endswith(".md") else "application/json"
    return FileResponse(path, filename=name, media_type=media)
