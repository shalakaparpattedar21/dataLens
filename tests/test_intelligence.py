"""Tests for the dataset-intelligence services and their API. Synthetic data only; no CIC-IDS2017 results."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from datalens.intelligence import anomalies as an
from datalens.intelligence import health as hl
from datalens.intelligence import leakage as lk
from datalens.intelligence import relationships as rel
from datalens.intelligence.recommendations import build_recommendations
from datalens.intelligence.sampling import ROW_ID, load_sample, split_feature_types
from tests.test_app_hardening import env, make_df, prepare, profile, upload, wait_job  # noqa: F401

INFO = {"rows_total": 0, "rows_sampled": 0, "sampled": False}


def rich(n: int = 1500, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    a = rng.normal(size=n)
    y = rng.choice(["BENIGN", "ATTACK"], n, p=[.8, .2])
    df = pd.DataFrame({
        "flow_id": np.arange(n), "a": a, "b": a * 2 + rng.normal(scale=.01, size=n), "c": rng.normal(size=n),
        "noise": rng.normal(size=n), "const": 1.0, "proto": rng.choice(["tcp", "udp", "icmp"], n),
        "host": rng.choice([f"h{i}" for i in range(40)], n), "cat_hi": [f"v{i}" for i in range(n)],
        "ts": pd.date_range("2024-01-01", periods=n, freq="min").astype(str), "label": y,
    })
    df["leak"] = (df["label"] == "ATTACK").astype(float) * 10 + rng.normal(scale=.05, size=n)
    df.loc[::40, "c"] = np.nan
    df.loc[3, "noise"] = np.inf
    return df


def frame_info(df):
    f = df.copy()
    f[ROW_ID] = np.arange(len(f))
    return f, {"rows_total": len(f), "rows_sampled": len(f), "sampled": False}


# ------------------------------------------------------------------------------- sampling
def test_sample_is_seeded_bounded_and_keeps_row_ids(tmp_path):
    df = make_df(3000)
    p = tmp_path / "d.csv"
    df.to_csv(p, index=False)
    a, info = load_sample([p], 3000, cap=500, seed=1)
    b, _ = load_sample([p], 3000, cap=500, seed=1)
    c, _ = load_sample([p], 3000, cap=500, seed=2)
    assert a[ROW_ID].tolist() == b[ROW_ID].tolist() != c[ROW_ID].tolist()
    assert 300 < len(a) <= 550 and info["sampled"]
    assert (df.loc[a[ROW_ID], "dur"].to_numpy() == a["dur"].to_numpy()).all()  # row id points at the source row


def test_split_types_handles_constant_and_high_cardinality():
    t = split_feature_types(rich(), exclude=["label"])
    assert "const" in t["constant"] and "cat_hi" in t["high_cardinality"] and "proto" in t["categorical"] and "a" in t["numeric"]


# ---------------------------------------------------------------------------- relationships
def test_relationships_find_correlated_pair_redundancy_and_target_signal():
    f, info = frame_info(rich())
    r = rel.compute_relationships(f, "label", info, seed=1)
    assert any({p["a"], p["b"]} == {"a", "b"} and p["abs_max"] > .99 for p in r["high_correlation_pairs"])
    assert any(set(g["members"]) == {"a", "b"} for g in r["redundancy_groups"])
    assert r["target_kind"] == "classification"
    assert r["feature_target"][0]["column"] == "leak"
    cols = r["heatmap"]["columns"]
    assert len(r["heatmap"]["pearson"]) == len(cols) and all(len(row) == len(cols) for row in r["heatmap"]["pearson"])
    assert "const" not in cols and any(s["column"] == "const" for s in r["skipped"])
    assert any(s["column"] == "cat_hi" for s in r["skipped"])
    vif = {v["column"]: v for v in r["vif"]}
    assert (vif["a"]["vif"] or 1e9) > 100 or vif["a"]["perfect_collinearity"]


def test_relationships_match_independent_pearson():
    df = rich()
    f, info = frame_info(df)
    r = rel.compute_relationships(f, "label", info)
    cols = r["heatmap"]["columns"]
    i, j = cols.index("a"), cols.index("b")
    assert r["heatmap"]["pearson"][i][j] == pytest.approx(df["a"].corr(df["b"]), abs=1e-3)


def test_relationships_without_target_and_with_regression_target():
    f, info = frame_info(rich().drop(columns=["label"]))
    assert rel.compute_relationships(f, None, info)["target_kind"] == "none"
    g, info = frame_info(rich())
    g["y"] = g["a"] * 3 + 1
    r = rel.compute_relationships(g.drop(columns=["label"]), "y", info)
    assert r["target_kind"] == "regression" and r["feature_target"][0]["column"] in ("a", "b")


def test_relationships_cap_wide_dataset():
    rng = np.random.default_rng(0)
    wide = pd.DataFrame(rng.normal(size=(300, 90)), columns=[f"x{i}" for i in range(90)])
    wide["y"] = rng.choice(["p", "q"], 300)
    f, info = frame_info(wide)
    r = rel.compute_relationships(f, "y", info)
    assert len(r["heatmap"]["columns"]) == rel.MAX_NUMERIC and r["cap_note"] and len(r["skipped"]) == 30


def test_cramers_v_known_cases():
    a = pd.Series(list("xyxyxyxy" * 20))
    assert rel.cramers_v(a, a) > 0.95
    rng = np.random.default_rng(0)
    assert (rel.cramers_v(pd.Series(rng.choice(list("xy"), 2000)), pd.Series(rng.choice(list("pqrs"), 2000))) or 0) < 0.1
    assert rel.cramers_v(pd.Series(["a"] * 10), pd.Series(["b"] * 10)) is None


# -------------------------------------------------------------------------------- anomalies
@pytest.mark.parametrize("method", ["isolation_forest", "lof", "iqr", "dbscan"])
def test_anomaly_methods_flag_planted_outliers(method):
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.normal(size=(1000, 4)), columns=list("wxyz"))
    df.loc[:9, :] = rng.uniform(15, 40, (10, 4)) * rng.choice([-1, 1], (10, 4))  # scattered, so DBSCAN sees noise, not a cluster
    df["label"] = "n"
    f, info = frame_info(df)
    r = an.run_anomaly_detection(f, "label", info, method=method, contamination=0.02, seed=1)
    flagged = {x["row_id"] for x in r["records"]}
    assert len(flagged & set(range(10))) >= 8, method
    assert r["summary"]["rows_analyzed"] == 1000 and r["config"]["seed"] == 1
    assert r["category"] == ("statistical_outlier" if method == "iqr" else "multivariate_anomaly")
    assert sum(r["score_histogram"]["all"]) == 1000 and r["scatter"]["points"]
    assert all(rec["top_features"] for rec in r["records"][:5])


def test_anomaly_is_reproducible_and_never_mutates_input():
    df = rich()
    f, info = frame_info(df)
    before = f.copy()
    a = an.run_anomaly_detection(f, "label", info, seed=5)
    b = an.run_anomaly_detection(f, "label", info, seed=5)
    assert a["records"] == b["records"]
    pd.testing.assert_frame_equal(f, before)


def test_anomaly_flags_data_error_indicators_but_labels_them_heuristic():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"dur": rng.exponential(5, 3000), "size": rng.exponential(9, 3000), "label": "x"})
    df.loc[0, "dur"] = -1.0
    df.loc[1, "size"] = np.inf
    f, info = frame_info(df)
    r = an.run_anomaly_detection(f, "label", info, method="isolation_forest", contamination=0.05)
    cands = {x["row_id"]: x for x in r["data_error_candidates"]}
    assert "negative value" in cands[0]["reasons"][0] and "infinite value" in cands[1]["reasons"][0]
    assert r["summary"]["data_error_indicator_rows"] == 2 and "never removes" in r["interpretation"] and "Heuristic" in r["data_error_note"]


def test_default_anomaly_features_skip_identifiers():
    f, info = frame_info(rich())
    r = an.run_anomaly_detection(f, "label", info)
    assert "flow_id" not in r["config"]["features"] and "a" in r["config"]["features"]


def test_anomaly_input_validation():
    f, info = frame_info(rich())
    for kw in ({"method": "nope"}, {"contamination": 0.9}, {"features": ["proto"]}, {"features": ["const"]}):
        with pytest.raises(ValueError):
            an.run_anomaly_detection(f, "label", info, **kw)
    with pytest.raises(ValueError):
        an.run_anomaly_detection(f.head(5), "label", info)


# ---------------------------------------------------------------------------------- leakage
def test_source_leakage_flags_identifier_proxy_group_time_and_marks_unassessed():
    df = rich()
    f, info = frame_info(df)
    prof = {"rows": len(df), "duplicates": {"exact_duplicate_rows_global": 0}}
    rep = lk.source_leakage(f, "label", info, prof, seed=1)
    by_type = {}
    for x in rep["findings"]:
        by_type.setdefault(x["type"], []).append(x)
    assert any(x["features"] == ["leak"] and x["status"] == "potential" and x["severity"] == "critical" for x in by_type["suspicious_feature_target"])
    assert any(x["features"] == ["flow_id"] for x in by_type["identifier_like_column"])
    assert any(x["features"] == ["host"] for x in by_type["group_leakage"])
    assert any(x["features"] == ["ts"] for x in by_type["temporal_leakage"])
    pre = by_type["preprocessing_leakage"][0]
    assert pre["status"] == "not_assessed"
    assert all(x["status"] != "confirmed" for x in rep["findings"])  # nothing at source level is proven
    assert all(x["evidence_text"] for x in rep["findings"] if x["status"] in ("potential", "confirmed"))
    assert rep["summary"]["level"] == "critical"


def test_source_leakage_not_assessed_without_metadata_or_target():
    df = pd.DataFrame(np.random.default_rng(1).normal(size=(400, 3)), columns=list("abc"))
    f, info = frame_info(df)
    rep = lk.source_leakage(f, None, info, {"rows": 400, "duplicates": {}})
    statuses = {x["type"]: x["status"] for x in rep["findings"]}
    assert statuses["group_leakage"] == "not_assessed" and statuses["temporal_leakage"] == "not_assessed"
    assert statuses["suspicious_feature_target"] == "not_assessed"


def test_identifier_check_matches_whole_words_only():
    df = pd.DataFrame({"width": np.random.default_rng(1).normal(size=300), "label": np.random.default_rng(2).choice(list("ab"), 300)})
    f, info = frame_info(df)
    rep = lk.source_leakage(f, "label", info, {"rows": 300, "duplicates": {}})
    assert not any(x["type"] == "identifier_like_column" for x in rep["findings"])


def test_constant_integer_column_is_not_an_identifier():
    df = pd.DataFrame({"k": np.ones(300, dtype=int), "flag": np.tile([0, 1, 2], 100), "label": np.random.default_rng(0).choice(list("ab"), 300)})
    f, info = frame_info(df)
    rep = lk.source_leakage(f, "label", info, {"rows": 300, "duplicates": {}})
    assert not any(x["type"] == "identifier_like_column" for x in rep["findings"])


def test_summarize_rule():
    s = lk.summarize([lk.finding("a", "high", "potential", "t"), lk.finding("b", "critical", "not_assessed", "t")])
    assert s["highest_active_severity"] == "high" and s["by_status"]["not_assessed"] == 1


# ------------------------------------------------------------------------------------ health
def _profile(**kw):
    base = {"rows": 1000, "columns": 10, "missing_cells": 0, "positive_infinity_cells": 0, "negative_infinity_cells": 0, "duplicate_rows": 0,
            "duplicates": {"label_conflict_rows": 0}, "constant_columns": [], "outliers": [], "label_column": "y", "created_at": "t",
            "dtypes": [{"column": f"c{i}", "dtype": "float64", "missing_cells": 0} for i in range(9)],
            "class_distribution": [{"label": "a", "count": 500, "percent": 50}, {"label": "b", "count": 500, "percent": 50}]}
    base.update(kw)
    return base


def test_health_clean_dataset_scores_high_and_is_deterministic():
    leak = [{"scope": "source", "findings": [lk.finding("x", "info", "clear", "ok")]}]
    h1 = hl.compute_health(_profile(), None, leak, None, "t")
    h2 = hl.compute_health(_profile(), None, leak, None, "t")
    assert h1 == h2 and h1["overall"] >= 95
    assert {d["name"] for d in h1["dimensions"]} == set(hl.WEIGHTS)
    assert all(d["methodology"] for d in h1["dimensions"])


def test_health_formulas_exact():
    p = _profile(missing_cells=1000, duplicate_rows=100)  # 1000/10000 cells = 10%; 100/1000 dups = 10%
    h = {d["name"]: d for d in hl.compute_health(p, None, [], None, "t")["dimensions"]}
    assert h["completeness"]["score"] == pytest.approx(100 * (1 - 0.5 * 0.5), abs=0.1)
    assert h["uniqueness"]["score"] == pytest.approx(50.0)
    assert h["leakage"]["score"] is None and h["leakage"]["label"] == "Insufficient data"


def test_critical_leakage_cannot_be_hidden_by_other_dimensions():
    leak = [{"scope": "run", "findings": [lk.finding("exact_overlap", "critical", "confirmed", "overlap", evidence_text="12% shared")]}]
    h = hl.compute_health(_profile(), None, leak, None, "t")
    assert h["overall"] <= 40 and h["overall_cap"]
    assert h["readiness"]["status"] == "high_risk" and h["readiness"]["blockers"]


def test_health_insufficient_data_when_little_evidence():
    h = hl.compute_health(None, None, [], None, "t")
    assert h["overall"] is None and h["readiness"]["status"] == "insufficient_evidence"
    h = hl.compute_health(_profile(), None, [], None, "t")  # leakage missing -> still enough weight for a score, readiness insufficient
    assert h["overall"] is not None and h["readiness"]["status"] == "insufficient_evidence"


def test_readiness_does_not_equate_validation_with_ready():
    leak = [{"scope": "source", "findings": [lk.finding("x", "info", "clear", "ok")]}]
    run = {"id": "r", "comparison": {"processed_sample": {"missing_feature_cells_after": 0, "infinite_feature_cells_after": 0}}}
    assert hl.compute_health(_profile(), None, leak, run, "t")["readiness"]["status"] == "ready_for_experimentation"
    h = hl.compute_health(_profile(), None, leak, None, "t")
    assert h["readiness"]["status"] == "needs_improvement" and any("prepar" in b.lower() for b in h["readiness"]["blockers"])
    leak2 = [{"scope": "source", "findings": [lk.finding("x", "medium", "potential", "id col", evidence_text="e")]}]
    assert hl.compute_health(_profile(), None, leak2, run, "t")["readiness"]["status"] == "needs_improvement"


# ------------------------------------------------------------------------- recommendations
def test_recommendations_are_evidence_based_and_apply_only_supported_fields():
    p = _profile(missing_cells=50, duplicate_rows=30, duplicates={"exact_duplicate_rows_global": 30, "label_conflict_rows": 4, "label_conflict_groups": 2},
                 constant_columns=["k"], outliers=[{"column": "c1", "estimated_percent": 12.0}], positive_infinity_cells=3,
                 dtypes=[{"column": "c1", "dtype": "float64", "missing_cells": 50}, {"column": "c2", "dtype": "object", "missing_cells": 5}],
                 class_distribution=[{"label": "a", "count": 9900, "percent": 99}, {"label": "b", "count": 40, "percent": 1}])
    out = build_recommendations(p, {"categorical": [{"column": "u", "high_cardinality": True}]},
                                {"redundancy_groups": [{"keep": "a", "candidates": ["b"], "members": ["a", "b"]}], "vif": [{"column": "b", "vif": 40.0, "perfect_collinearity": False}],
                                 "vif_thresholds": {"severe": 10}, "target_kind": "classification"}, [])
    ids = {i["id"] for i in out["items"]}
    assert {"impute-numeric", "impute-categorical", "infinite", "duplicates", "label-conflicts", "constants", "scaling", "cardinality", "imbalance",
            "rare-classes", "redundancy", "multicollinearity", "selection"} <= ids
    allowed = {"sample_fraction", "duplicate_policy", "numeric_imputer", "encoding", "scaler", "feature_selection"}
    for item in out["items"]:
        assert item["why"] and item["suggested_action"] and item["expected_benefit"] and item["tradeoffs"]
        if item["can_apply"]:
            assert set(item["apply"]) <= allowed and set(item["choices"]) == set(item["apply"])
        else:
            assert item["apply"] is None
    assert next(i for i in out["items"] if i["id"] == "imbalance")["can_apply"] is False  # DataLens cannot resample
    assert build_recommendations(None, None, None, [])["items"] == []


# --------------------------------------------------------------------------------------- API
def _analyze(client, ds, **body):
    r = client.post(f"/api/datasets/{ds['id']}/analyze", json=body)
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job"]["id"], timeout=120)
    assert job["status"] == "complete", job["error"]
    return client.get(f"/api/datasets/{ds['id']}/analysis").json()["analysis"]


def test_analyze_requires_profile_and_validates_inputs(env):
    client, _, _ = env
    ds = upload(client, make_df())
    assert client.post(f"/api/datasets/{ds['id']}/analyze").status_code == 409
    assert client.post("/api/datasets/not-a-real-id/analyze").status_code == 404
    profile(client, ds)
    assert client.post(f"/api/datasets/{ds['id']}/analyze", json={"target_column": "nope"}).status_code == 400
    assert client.post(f"/api/datasets/{ds['id']}/analyze", json={"anomaly": {"features": ["nope"]}}).status_code == 400
    assert client.post(f"/api/datasets/{ds['id']}/anomalies", json={"method": "bogus"}).status_code == 422
    assert client.post(f"/api/datasets/{ds['id']}/anomalies", json={"contamination": 0.9}).status_code == 422
    assert client.get("/api/datasets/zzz/analysis").status_code == 404
    empty = client.get(f"/api/datasets/{ds['id']}/analysis").json()["analysis"]
    assert empty["health"] is None and empty["relationships"] is None and empty["health_history"] == []


def test_full_analysis_workflow_over_api(env):
    client, _, _ = env
    df = rich()
    ds = upload(client, df)
    profile(client, ds, label_column="label")
    a = _analyze(client, ds)
    for key in ("distributions", "relationships", "leakage", "anomalies", "health", "recommendations"):
        assert a[key], key
    assert a["relationships"]["target"] == "label"
    assert a["anomalies"]["summary"]["rows_analyzed"] == len(df)
    assert a["health"]["overall"] is not None and a["health"]["readiness"]["label"]
    assert any(x["features"] == ["leak"] for x in a["leakage"]["findings"])
    assert len(a["health_history"]) == 1
    # configurable anomaly rerun
    r = client.post(f"/api/datasets/{ds['id']}/anomalies", json={"method": "lof", "contamination": 0.05, "features": ["a", "c"], "seed": 7})
    assert wait_job(client, r.json()["job"]["id"], 120)["status"] == "complete"
    an_ = client.get(f"/api/datasets/{ds['id']}/analysis").json()["analysis"]["anomalies"]
    assert an_["method"] == "lof" and an_["config"]["features"] == ["a", "c"] and an_["config"]["seed"] == 7
    # prepare -> automatic run leakage -> health refresh
    m = prepare(client, ds, duplicate_policy="keep")
    lr = client.get(f"/api/preparations/{m['id']}/leakage")
    assert lr.status_code == 200
    kinds = {f["type"]: f["status"] for f in lr.json()["leakage"]["findings"]}
    assert kinds["exact_overlap"] == "clear" and kinds["preprocessing_leakage"] == "clear"
    after = client.get(f"/api/datasets/{ds['id']}/analysis").json()["analysis"]
    assert after["health"]["inputs"]["run_id"] == m["id"] and len(after["health_history"]) >= 2
    assert client.get(f"/api/preparations/{m['id']}/files/leakage_report.json").status_code == 200
    # delete run, then dataset: analysis files go with them
    assert client.delete(f"/api/preparations/{m['id']}").status_code == 200
    assert client.get(f"/api/preparations/{m['id']}/leakage").status_code == 404
    assert client.delete(f"/api/datasets/{ds['id']}").status_code == 200
    assert client.get(f"/api/datasets/{ds['id']}/analysis").status_code == 404


def test_run_leakage_confirms_overlap_with_exact_evidence(env):
    client, _, _ = env
    base = make_df(400)
    ds = upload(client, pd.concat([base] * 3, ignore_index=True))  # every row repeated 3x -> copies on both sides
    profile(client, ds)
    m = prepare(client, ds, duplicate_policy="keep")
    rep = client.get(f"/api/preparations/{m['id']}/leakage").json()["leakage"]
    ov = next(f for f in rep["findings"] if f["type"] == "exact_overlap")
    assert ov["status"] == "confirmed" and ov["severity"] in ("critical", "high")
    assert ov["evidence"]["test_rows_also_in_train"] == m["train_test_overlap"]["test_rows_also_in_train"] > 0
    near = next(f for f in rep["findings"] if f["type"] == "near_duplicates")
    assert near["evidence"]["threshold_rms"] == 0.05
    _analyze(client, ds)
    h = client.get(f"/api/datasets/{ds['id']}/analysis").json()["analysis"]["health"]
    assert h["overall"] <= 40 and h["readiness"]["status"] == "high_risk"
    # dedupe -> overlap disappears and the score recovers
    m2 = prepare(client, ds, duplicate_policy="drop_exact")
    rep2 = client.get(f"/api/preparations/{m2['id']}/leakage").json()["leakage"]
    assert next(f for f in rep2["findings"] if f["type"] == "exact_overlap")["status"] == "clear"
    assert client.get(f"/api/datasets/{ds['id']}/analysis").json()["analysis"]["health"]["overall"] > h["overall"]


def test_run_leakage_endpoint_validation_and_old_runs(env):
    client, _, _ = env
    ds = upload(client, make_df(300))
    profile(client, ds)
    m = prepare(client, ds)
    assert client.post(f"/api/preparations/{m['id']}/leakage", json={"threshold": 0}).status_code == 422
    assert client.post("/api/preparations/nope/leakage").status_code == 404
    r = client.post(f"/api/preparations/{m['id']}/leakage", json={"threshold": 0.2})
    assert wait_job(client, r.json()["job"]["id"])["status"] == "complete"
    assert client.get(f"/api/preparations/{m['id']}/leakage").json()["leakage"]["near_duplicate_threshold"] == 0.2
    # an older run whose config lacks fit_scope must be "not assessed", never claimed clear
    import datalens.api as api
    cfg = next(api.store.prepared.glob(f"*/{m['id']}/config.json"))
    c = json.loads(cfg.read_text())
    c.pop("fit_scope")
    cfg.write_text(json.dumps(c))
    wait_job(client, client.post(f"/api/preparations/{m['id']}/leakage").json()["job"]["id"])
    f = client.get(f"/api/preparations/{m['id']}/leakage").json()["leakage"]["findings"]
    assert next(x for x in f if x["type"] == "preprocessing_leakage")["status"] == "not_assessed"


def test_analysis_job_failure_is_reported(env, monkeypatch):
    client, _, _ = env
    ds = upload(client, make_df(300))
    profile(client, ds)
    import datalens.api as api
    p = next(api.store.datasets.glob(f"{ds['id']}/*.csv"))
    p.write_text("a,b\n1,2\n")  # source changed under us: profile says 300 rows, columns differ
    r = client.post(f"/api/datasets/{ds['id']}/analyze", json={"target_column": "label"})
    job = wait_job(client, r.json()["job"]["id"], 60)
    assert job["status"] == "failed" and job["error"]


def test_analysis_on_wide_mixed_and_tiny_data(env):
    client, _, _ = env
    rng = np.random.default_rng(0)
    wide = pd.DataFrame(rng.normal(size=(250, 70)), columns=[f"x{i}" for i in range(70)])
    wide["label"] = rng.choice(["a", "b", "c"], 250)
    wide["txt"] = rng.choice(["p", "q"], 250)
    ds = upload(client, wide)
    profile(client, ds)
    a = _analyze(client, ds)
    assert len(a["relationships"]["heatmap"]["columns"]) == 60 and a["relationships"]["cap_note"]
    assert len(a["anomalies"]["config"]["features"]) <= 25
    tiny = upload(client, pd.DataFrame({"x": range(10), "label": list("ababababab")}), "tiny.csv")
    profile(client, tiny)
    r = client.post(f"/api/datasets/{tiny['id']}/analyze")
    job = wait_job(client, r.json()["job"]["id"], 60)
    assert job["status"] == "failed" and "20" in job["error"]
