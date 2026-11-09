"""Regression tests for the web app backend: API robustness, preparation reporting and cleanup.

Every test here was written against a defect or gap found while exercising the real workflow
(upload -> profile -> prepare -> export). Data is synthetic and tiny; nothing here is a
CIC-IDS2017 result.
"""

from __future__ import annotations

import importlib
import io
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


# ----------------------------------------------------------------------------- helpers
@pytest.fixture
def env(tmp_path, monkeypatch):
    """A TestClient bound to an isolated workspace, plus the reloaded api module."""
    monkeypatch.setenv("DATALENS_WORKSPACE", str(tmp_path / "workspace"))
    import datalens.app_service as app_service
    import datalens.api as api

    importlib.reload(app_service)
    api = importlib.reload(api)
    return TestClient(api.app), api, tmp_path


def csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def make_df(n: int = 600, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "dur": rng.lognormal(2, 1, n), "bytes": rng.lognormal(5, 1, n), "port": rng.integers(0, 65535, n),
        "proto": rng.choice(["tcp", "udp"], n), "label": rng.choice(["BENIGN", "DoS"], n, p=[.8, .2]),
    })


def wait_job(client: TestClient, job_id: str, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()["job"]
        if job["status"] in ("complete", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def upload(client: TestClient, df: pd.DataFrame | bytes, name: str = "data.csv") -> dict:
    payload = csv_bytes(df) if isinstance(df, pd.DataFrame) else df
    r = client.post(f"/api/datasets/upload?filename={name}", content=payload, headers={"content-type": "text/csv"})
    assert r.status_code == 201, r.text
    return r.json()["dataset"]


def profile(client: TestClient, ds: dict, **body) -> dict:
    job = wait_job(client, client.post(f"/api/datasets/{ds['id']}/profile", json=body).json()["job"]["id"])
    assert job["status"] == "complete", job["error"]
    return client.get(f"/api/datasets/{ds['id']}").json()["dataset"]["profile"]


def prepare(client: TestClient, ds: dict, **options) -> dict:
    body = {"target_column": "label", "sample_fraction": 1.0, "test_size": 0.2, "seed": 42}
    body.update(options)
    r = client.post(f"/api/datasets/{ds['id']}/prepare", json=body)
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job"]["id"])
    assert job["status"] == "complete", job["error"]
    return job["result"]


def outputs(manifest: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    out = Path(manifest["output_dir"])
    return pd.read_csv(out / "train.csv"), pd.read_csv(out / "test.csv"), json.loads((out / "config.json").read_text())


# ----------------------------------------------------------------------------- error handling
@pytest.mark.parametrize("method,path", [
    ("get", "/api/datasets/not-a-valid-id!"), ("get", "/api/datasets/zzzz"), ("delete", "/api/datasets/zzzz"),
    ("get", "/api/datasets/00000000-0000-0000-0000-000000000000"),
])
def test_malformed_or_unknown_dataset_id_is_404_not_500(env, method, path):
    client, _, _ = env
    assert getattr(client, method)(path).status_code == 404


def test_profile_and_prepare_unknown_dataset_are_404(env):
    client, _, _ = env
    assert client.post("/api/datasets/zzzz/profile", json={}).status_code == 404
    assert client.post("/api/datasets/zzzz/prepare", json={}).status_code == 404


def test_profile_without_request_body_is_accepted(env):
    client, _, _ = env
    ds = upload(client, make_df())
    r = client.post(f"/api/datasets/{ds['id']}/profile")
    assert r.status_code == 202
    assert wait_job(client, r.json()["job"]["id"])["status"] == "complete"


@pytest.mark.parametrize("payload,fragment", [
    (bytes(range(256)) * 40, "binary"),
    (b"a,b,c\n", "no data rows"),
    (b"\n\n   \n", "header"),
    (b"a,b\n1,2,3,4,5\n\"unterminated,1\n", "parsed"),
])
def test_upload_rejects_unusable_files_with_a_clear_message(env, payload, fragment):
    client, _, _ = env
    r = client.post("/api/datasets/upload?filename=bad.csv", content=payload)
    assert r.status_code == 400
    assert fragment in r.json()["detail"]
    assert client.get("/api/datasets").json()["datasets"] == []          # nothing registered
    leftovers = [p for p in (Path(client.get("/api/health").json()["workspace"])).glob("upload-*")]
    assert leftovers == []                                              # temp file removed


def test_upload_accepts_cp1252_csv(env):
    client, _, _ = env
    payload = "a,label\n1,Web Attack – XSS\n2,BENIGN\n".encode("cp1252")
    assert upload(client, payload)["size_bytes"] == len(payload)


def test_upload_rejects_non_csv_extension(env):
    client, _, _ = env
    assert client.post("/api/datasets/upload?filename=notes.txt", content=b"a,b\n1,2\n").status_code == 400


def test_unknown_label_column_fails_profile_job_with_message(env):
    client, _, _ = env
    ds = upload(client, make_df())
    job = wait_job(client, client.post(f"/api/datasets/{ds['id']}/profile", json={"label_column": "nope"}).json()["job"]["id"])
    assert job["status"] == "failed" and "nope" in job["error"]


def test_unexpected_job_error_is_logged_with_traceback(env, monkeypatch, caplog):
    client, api, _ = env
    ds = upload(client, make_df())
    monkeypatch.setattr(api, "profile_files", lambda *a, **k: (_ for _ in ()).throw(NameError("name 'Counter' is not defined")))
    with caplog.at_level(logging.ERROR, logger="datalens.api"):
        job = wait_job(client, client.post(f"/api/datasets/{ds['id']}/profile", json={}).json()["job"]["id"])
    assert job["status"] == "failed" and "Unexpected NameError" in job["error"]
    record = next(r for r in caplog.records if "failed" in r.getMessage())
    assert record.exc_info and record.exc_info[0] is NameError           # traceback reaches the server log


# ----------------------------------------------------------------------------- profile findings
def test_profile_findings_carry_recommendations_and_new_checks(env):
    client, _, _ = env
    rng = np.random.default_rng(3)
    n = 400
    df = pd.DataFrame({"Destination Port": rng.integers(0, 65535, n), "dur": rng.random(n),
                       "label": ["BENIGN"] * (n - 7) + ["Rare"] * 7})
    df = pd.concat([df, df.iloc[[0]].assign(label="Rare")], ignore_index=True)   # same features, different label
    p = profile(client, upload(client, df))
    titles = {i["title"] for i in p["issues"]}
    assert {"Conflicting labels", "Rare classes", "Identifier-like columns", "Imbalanced target"} <= titles
    assert all(i.get("recommendation") for i in p["issues"])
    ident = next(i for i in p["issues"] if i["title"] == "Identifier-like columns")
    assert ident["columns"] == ["Destination Port"]                      # 'dur' and the target are not flagged
    rare = next(i for i in p["issues"] if i["title"] == "Rare classes")
    assert {c["label"] for c in rare["classes"]} == {"Rare"}


def test_identifier_check_matches_whole_words_only(env):
    client, _, _ = env
    df = pd.DataFrame({"Idle Mean": [1.0, 2.0, 3.0, 4.0], "Flow Duration": [1, 2, 3, 4], "label": list("aabb")})
    p = profile(client, upload(client, df))
    assert not any(i["title"] == "Identifier-like columns" for i in p["issues"])


def test_profile_without_target_column_says_so(env):
    client, _, _ = env
    p = profile(client, upload(client, pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})))
    assert p["label_column"] is None
    assert any(i["title"] == "No target column detected" for i in p["issues"])


# ----------------------------------------------------------------------------- preparation correctness
def test_rare_classes_missing_from_a_split_are_reported_never_silent(env):
    client, _, _ = env
    df = make_df(500)
    df.loc[0, "label"] = "solo"                      # one row: it can only land in one partition
    df.loc[1:3, "label"] = "tiny"                    # three rows
    ds = upload(client, df); profile(client, ds, label_column="label")
    m = prepare(client, ds)
    tr, te, cfg = outputs(m)
    counts = {c["label"]: c for c in m["class_coverage"]}
    assert counts["solo"]["total"] == 1
    # reported coverage equals what is really in the exported files
    for name, frame_counts in (("train", tr["label"].value_counts()), ("test", te["label"].value_counts())):
        for label, row in counts.items():
            assert row[name] == int(frame_counts.get(label, 0))
    assert sum(c["total"] for c in m["class_coverage"]) == len(df)       # no class silently lost
    assert any("'solo'" in w for w in m["warnings"])
    # every class flagged absent/low has a matching warning sentence, and vice versa
    flagged = {c["label"] for c in m["class_coverage"] if c["flags"]}
    assert flagged and all(any(f"'{label}'" in w for w in m["warnings"]) for label in flagged)
    assert "## Class coverage" in (Path(m["output_dir"]) / "quality_report.md").read_text(encoding="utf-8")
    assert json.loads((Path(m["output_dir"]) / "quality_report.json").read_text())["class_coverage"] == m["class_coverage"]


def test_overlap_between_train_and_test_is_measured_and_removed_by_drop_exact(env):
    client, _, _ = env
    base = make_df(300, seed=11)
    ds = upload(client, pd.concat([base] * 3, ignore_index=True))       # every row appears 3 times
    profile(client, ds, label_column="label")

    keep = prepare(client, ds, duplicate_policy="keep")
    tr, te, _ = outputs(keep)
    merged = te.merge(tr.drop_duplicates(), how="left", indicator=True)
    independent = int((merged["_merge"] == "both").sum())               # recomputed from the exported CSVs
    assert independent > 0
    assert keep["train_test_overlap"]["test_rows_also_in_train"] == independent
    assert any("exact copies of training rows" in w for w in keep["warnings"])

    dropped = prepare(client, ds, duplicate_policy="drop_exact")
    assert dropped["train_test_overlap"]["test_rows_also_in_train"] == 0
    assert dropped["rows"]["train"] + dropped["rows"]["test"] == 300
    assert not any("exact copies" in w for w in dropped["warnings"])


def test_scaler_is_fitted_on_training_rows_only(env):
    """Train features have mean 0 / std 1 under StandardScaler; test features do not (they used train statistics)."""
    client, _, _ = env
    df = make_df(2000, seed=5)
    df.loc[df["label"] == "DoS", "dur"] *= 8                             # make test differ from train distribution
    ds = upload(client, df); profile(client, ds, label_column="label")
    tr, te, cfg = outputs(prepare(client, ds, scaler="standard", missing_indicator=False, numeric_imputer="mean"))
    assert abs(tr["dur"].mean()) < 1e-9 and abs(tr["dur"].std(ddof=0) - 1) < 1e-9
    assert abs(te["dur"].mean()) > 1e-6                                  # would be ~0 if test had leaked into the fit
    assert cfg["fit_record"]["fit_rows_used"] == len(tr)                 # fitted on exactly the training rows


def test_target_is_exported_and_never_used_as_a_feature(env):
    client, _, _ = env
    df = make_df(300)
    df["label_copy_name"] = df["label"].map({"BENIGN": 0, "DoS": 1})     # a different column that merely resembles the target
    ds = upload(client, df); profile(client, ds, label_column="label")
    tr, te, cfg = outputs(prepare(client, ds))
    assert "label" in tr.columns and "label" in te.columns
    assert list(tr.columns) == list(te.columns) and tr.columns[-1] == "label"
    assert cfg["target_column"] == "label"
    assert set(tr["label"]) | set(te["label"]) == {"BENIGN", "DoS"}
    assert [c for c in tr.columns if c.startswith("label") and c != "label"] == ["label_copy_name"]


def test_row_counts_reconcile_with_sampling_and_duplicate_policy(env):
    client, _, _ = env
    base = make_df(400, seed=2)
    ds = upload(client, pd.concat([base, base.iloc[:50]], ignore_index=True))   # 450 rows, 50 exact repeats
    profile(client, ds, label_column="label")
    full = prepare(client, ds, duplicate_policy="drop_exact")
    assert full["rows"]["train"] + full["rows"]["test"] == 400
    comp = full["comparison"]["processed_sample"]
    assert comp["rows"] == 450 and comp["duplicate_rows_removed"] == 50
    assert comp["rows_after_duplicate_policy"] == 400
    part = prepare(client, ds, sample_fraction=0.5, duplicate_policy="keep")
    assert part["comparison"]["processed_sample"]["rows"] < 450
    assert part["rows"]["train"] + part["rows"]["test"] == part["comparison"]["processed_sample"]["rows"]
    assert any("sample" in w.lower() for w in part["warnings"])
    assert not any("sample" in w.lower() for w in full["warnings"])


def test_same_configuration_and_seed_reproduce_identical_files(env):
    client, _, _ = env
    ds = upload(client, make_df(500, seed=9)); profile(client, ds, label_column="label")
    a = prepare(client, ds, duplicate_policy="drop_exact", scaler="robust", seed=7)
    b = prepare(client, ds, duplicate_policy="drop_exact", scaler="robust", seed=7)
    c = prepare(client, ds, duplicate_policy="drop_exact", scaler="robust", seed=8)
    read = lambda m, f: (Path(m["output_dir"]) / f).read_bytes()
    assert read(a, "train.csv") == read(b, "train.csv") and read(a, "test.csv") == read(b, "test.csv")
    assert read(a, "train.csv") != read(c, "train.csv")


def test_drop_within_file_keeps_cross_file_copies_but_drop_exact_removes_them(env, tmp_path):
    client, _, _ = env
    import datalens.api as api

    df = make_df(100, seed=4)
    f1, f2 = tmp_path / "day1.csv", tmp_path / "day2.csv"
    df.to_csv(f1, index=False); df.to_csv(f2, index=False)             # same 100 rows in two files
    record = api.store.register_local([f1, f2], "two days")
    profile_rec = client.post(f"/api/datasets/{record['id']}/profile", json={"label_column": "label"}).json()["job"]
    assert wait_job(client, profile_rec["id"])["status"] == "complete"
    ds = {"id": record["id"]}
    within = prepare(client, ds, duplicate_policy="drop_within_file")
    exact = prepare(client, ds, duplicate_policy="drop_exact")
    assert within["rows"]["train"] + within["rows"]["test"] == 200
    assert exact["rows"]["train"] + exact["rows"]["test"] == 100


def test_ordinal_encoding_produces_one_column_and_is_recorded(env):
    client, _, _ = env
    ds = upload(client, make_df(400)); profile(client, ds, label_column="label")
    tr, _, cfg = outputs(prepare(client, ds, encoding="ordinal"))
    assert "proto" in tr.columns and not any(c.startswith("proto_") for c in tr.columns)
    assert set(tr["proto"].unique()) <= {-1.0, 0.0, 1.0}
    assert cfg["encoding"] == "ordinal" and cfg["categorical_min_frequency"] is None


def test_onehot_infrequent_category_grouping_is_recorded_not_hidden(env):
    client, _, _ = env
    df = make_df(600)
    df.loc[:2, "proto"] = "rare"                                          # 3 of 600 rows = 0.5% < the 1% threshold
    ds = upload(client, df); profile(client, ds, label_column="label")
    m = prepare(client, ds, encoding="onehot")
    tr, _, cfg = outputs(m)
    assert cfg["categorical_min_frequency"] == 0.01
    assert "infrequent" in cfg["categorical_note"]
    assert not any(c == "proto_rare" for c in tr.columns)                 # grouped, as the note says
    assert any("infrequent" in c for c in tr.columns)
    assert "infrequent" in (Path(m["output_dir"]) / "quality_report.md").read_text(encoding="utf-8")


def test_missing_target_values_are_kept_as_a_class_and_warned_about(env):
    client, _, _ = env
    df = make_df(400)
    df.loc[:9, "label"] = None
    ds = upload(client, df); profile(client, ds, label_column="label")
    m = prepare(client, ds)
    tr, te, _ = outputs(m)
    assert int((tr["label"] == "(missing)").sum() + (te["label"] == "(missing)").sum()) == 10
    assert any("no target value" in w for w in m["warnings"])


def test_preparing_without_a_target_has_no_class_warnings(env):
    client, _, _ = env
    ds = upload(client, make_df(200)); profile(client, ds)
    m = prepare(client, ds, target_column=None)
    tr, _, _ = outputs(m)
    assert "label" not in tr.columns and m["class_coverage"] == []
    assert not any("Class '" in w for w in m["warnings"])


def test_failed_preparation_leaves_no_partial_output(env, monkeypatch):
    client, api, _ = env
    import datalens.prepare_service as ps

    ds = upload(client, make_df(200)); profile(client, ds, label_column="label")
    monkeypatch.setattr(ps, "fit_preprocessor", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = client.post(f"/api/datasets/{ds['id']}/prepare", json={"target_column": "label"})
    job = wait_job(client, r.json()["job"]["id"])
    assert job["status"] == "failed" and "boom" in job["error"]
    assert list(api.store.prepared.glob("*/*")) == []                     # no orphaned run folder
    assert client.get("/api/preparations").json()["preparations"] == []


def test_invalid_options_are_rejected_before_any_work(env):
    client, _, _ = env
    ds = upload(client, make_df(100)); profile(client, ds, label_column="label")
    for body in ({"target_column": "nope"}, {"sample_fraction": 0}, {"test_size": 0.9}, {"scaler": "weird"},
                 {"feature_selection": "kbest_f", "target_column": None}):
        assert client.post(f"/api/datasets/{ds['id']}/prepare", json=body).status_code in (400, 422), body
    assert client.post(f"/api/datasets/{upload(client, make_df(50))['id']}/prepare", json={}).status_code == 409  # not profiled


# ----------------------------------------------------------------------------- downloads and management
def test_all_six_artifacts_download_and_are_valid(env):
    client, _, _ = env
    ds = upload(client, make_df(300)); profile(client, ds, label_column="label")
    m = prepare(client, ds)
    for name in ("train.csv", "test.csv", "config.json", "quality_report.json", "quality_report.md", "comparison.json"):
        r = client.get(f"/api/preparations/{m['id']}/files/{name}")
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"], name
        if name.endswith(".json"):
            json.loads(r.text)
    assert client.get(f"/api/preparations/{m['id']}/files/secret.txt").status_code == 404
    assert client.get("/api/preparations/..%2F..%2Fetc/files/train.csv").status_code == 404
    comparison = json.loads(client.get(f"/api/preparations/{m['id']}/files/comparison.json").text)
    assert comparison["processed_sample"]["train_rows"] == m["rows"]["train"]


def test_delete_preparation_removes_its_files_only(env):
    client, api, _ = env
    ds = upload(client, make_df(200)); profile(client, ds, label_column="label")
    a, b = prepare(client, ds), prepare(client, ds, seed=1)
    assert client.delete(f"/api/preparations/{a['id']}").status_code == 200
    assert not Path(a["output_dir"]).exists() and Path(b["output_dir"]).is_dir()
    assert client.delete(f"/api/preparations/{a['id']}").status_code == 404
    assert client.delete("/api/preparations/..").status_code in (404, 405)
    assert [p["id"] for p in client.get("/api/preparations").json()["preparations"]] == [b["id"]]
    assert client.get(f"/api/datasets/{ds['id']}").status_code == 200   # dataset itself untouched


def test_delete_uploaded_dataset_removes_copy_and_outputs(env):
    client, api, _ = env
    ds = upload(client, make_df(150)); profile(client, ds, label_column="label")
    m = prepare(client, ds)
    assert client.delete(f"/api/datasets/{ds['id']}").status_code == 200
    assert not Path(ds["files"][0]).exists() and not Path(m["output_dir"]).exists()
    assert client.get(f"/api/datasets/{ds['id']}").status_code == 404
    assert client.get("/api/datasets").json()["datasets"] == []


def test_delete_local_dataset_never_touches_source_files(env, tmp_path):
    client, api, _ = env
    src = tmp_path / "precious.csv"
    make_df(120).to_csv(src, index=False)
    before = src.read_bytes()
    record = api.store.register_local([src], "local")
    assert client.delete(f"/api/datasets/{record['id']}").status_code == 200
    assert src.read_bytes() == before
    assert client.get(f"/api/datasets/{record['id']}").status_code == 404


def test_delete_is_blocked_while_a_job_is_active(env):
    client, api, _ = env
    ds = upload(client, make_df(100))
    api._jobs["fake"] = {"id": "fake", "dataset_id": ds["id"], "status": "running", "kind": "prepare"}
    assert client.delete(f"/api/datasets/{ds['id']}").status_code == 409
    api._jobs["fake"]["status"] = "complete"
    assert client.delete(f"/api/datasets/{ds['id']}").status_code == 200


def test_cors_allows_delete_from_the_dev_server(env):
    client, _, _ = env
    r = client.options("/api/preparations/x", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"})
    assert r.status_code == 200 and "DELETE" in r.headers["access-control-allow-methods"]


def test_import_cicids_is_idempotent_and_missing_folder_is_404(env, monkeypatch, tmp_path):
    client, api, _ = env
    raw = tmp_path / "raw"
    monkeypatch.setattr(api, "DEFAULT_RAW_DIR", raw)
    assert client.post("/api/datasets/import-cicids").status_code == 404        # folder does not exist yet
    raw.mkdir()
    assert client.post("/api/datasets/import-cicids").status_code == 404        # exists but empty
    make_df(50).to_csv(raw / "monday.csv", index=False)
    first = client.post("/api/datasets/import-cicids")
    second = client.post("/api/datasets/import-cicids")
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["dataset"]["id"] == second.json()["dataset"]["id"] and second.json()["already_registered"] is True
    assert len(client.get("/api/datasets").json()["datasets"]) == 1
    make_df(50).to_csv(raw / "tuesday.csv", index=False)                       # a different file set registers separately
    assert client.post("/api/datasets/import-cicids").status_code == 201
