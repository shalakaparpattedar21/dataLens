from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from datalens.app_service import DatasetStore, profile_files
from datalens.prepare_service import prepare_streaming


def test_chunked_profile_counts_quality_and_duplicates(tmp_path):
    source = tmp_path / "small.csv"
    source.write_text(
        "flow,label,category\n"
        "1,benign,a\n"
        "1,benign,a\n"
        "2,benign,b\n"
        "2,attack,b\n"
        ",attack,a\n"
        "inf,attack,a\n",
        encoding="utf-8",
    )

    result = profile_files([source])

    assert result["rows"] == 6
    assert result["columns"] == 3
    assert result["missing_cells"] == 1
    assert result["positive_infinity_cells"] == 1
    assert result["duplicate_rows"] == 1
    assert result["duplicates"]["label_conflict_groups"] == 1
    assert result["duplicates"]["label_conflict_rows"] == 2
    assert sum(item["count"] for item in result["class_distribution"]) == 6
    assert any(issue["title"] == "Missing values" for issue in result["issues"])


def test_streaming_prepare_exports_validate_and_preserve_source(tmp_path):
    source = tmp_path / "sample.csv"
    frame = pd.DataFrame({
        "duration": [float(i % 11) for i in range(120)],
        "protocol": ["tcp" if i % 3 else "udp" for i in range(120)],
        "label": ["normal" if i % 4 else "attack" for i in range(120)],
    })
    frame.loc[5, "duration"] = None
    frame.to_csv(source, index=False)
    original = source.read_bytes()
    store = DatasetStore(tmp_path / "workspace")
    record = store.register_local([source], "Synthetic sample")
    record["profile"] = profile_files([source], label_column="label")

    result = prepare_streaming(
        record,
        {
            "target_column": "label",
            "sample_fraction": 1.0,
            "test_size": 0.2,
            "seed": 42,
            "numeric_imputer": "median",
            "duplicate_policy": "keep",
            "encoding": "onehot",
            "scaler": "robust",
            "feature_selection": "none",
        },
        store,
    )

    out = Path(result["output_dir"])
    assert result["rows"]["train"] + result["rows"]["test"] == len(frame)
    assert result["validation"]["train"]["valid"]
    assert result["validation"]["test"]["valid"]
    assert json.loads((out / "config.json").read_text())["is_full_dataset"] is True
    assert json.loads((out / "comparison.json").read_text())["processed_sample"]["rows"] == len(frame)
    assert source.read_bytes() == original
    assert (out / "train.csv").is_file() and (out / "test.csv").is_file()


def test_upload_endpoint_stores_csv_in_local_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("DATALENS_WORKSPACE", str(tmp_path / "workspace"))
    import datalens.app_service as app_service
    import datalens.api as api

    importlib.reload(app_service)
    api = importlib.reload(api)
    client = TestClient(api.app)
    payload = b"feature,label\n1,ok\n2,bad\n"

    response = client.post("/api/datasets/upload?filename=demo.csv", content=payload, headers={"content-type": "text/csv"})

    assert response.status_code == 201
    record = response.json()["dataset"]
    uploaded = Path(record["files"][0])
    assert uploaded.read_bytes() == payload
    assert client.get("/api/datasets").json()["datasets"][0]["id"] == record["id"]
