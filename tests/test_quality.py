"""Tests for quality findings and report writing."""

import json

import numpy as np
import pandas as pd
import pytest

from datalens.config import load_config
from datalens.profiling import profile_dataframe
from datalens.quality import assess_quality, summarize_findings
from datalens.quality.assessment import _tokens
from datalens.reporting import write_quality_outputs


@pytest.fixture
def cfg():
    c = load_config()
    return c["quality"], c["profiling"]


def _assess(df, cfg, meta=None):
    q, p = cfg
    return assess_quality(profile_dataframe(df, "Label"), q, p, meta)


def _has(findings, dimension, metric, column=None):
    return any(f.dimension == dimension and f.metric == metric and (column is None or f.column == column)
               for f in findings)


def test_tokens_match_whole_words_only():
    assert "id" in _tokens("Flow ID")
    assert "port" in _tokens("Destination Port")
    assert "id" not in _tokens("Idle Mean")     # 'Idle' must not match 'id'
    assert "ip" not in _tokens("Flow Packets/s")


def test_completeness_and_validity_findings(cfg):
    df = pd.DataFrame({
        "Flow Duration": [1.0, -5.0, 3.0, np.nan, 5.0],
        "rate": [1.0, np.inf, 2.0, 3.0, 4.0],
        "Label": ["A", "A", "B", "B", "A"],
    })
    f = _assess(df, cfg)
    assert _has(f, "Completeness", "missing_pct", "Flow Duration")
    assert _has(f, "Validity", "inf_count", "rate")
    assert _has(f, "Validity", "negative_count", "Flow Duration")
    assert not _has(f, "Validity", "negative_count", "rate")   # no negatives there


def test_negative_in_unrelated_column_not_flagged(cfg):
    df = pd.DataFrame({"temperature": [-3.0, 1.0, 2.0, 3.0], "Label": list("AABB")})
    assert not _has(_assess(df, cfg), "Validity", "negative_count")


def test_duplicate_and_label_conflict_findings(cfg):
    df = pd.DataFrame({"x": [1, 1, 1, 2], "Label": ["A", "A", "B", "A"]})
    f = _assess(df, cfg)
    assert _has(f, "Uniqueness", "duplicate_rows_pct")
    conflict = [x for x in f if x.metric == "label_conflict_rows"][0]
    assert conflict.severity == "high" and conflict.value == 3


def test_constant_near_constant_and_identifier_findings(cfg):
    n = 200
    df = pd.DataFrame({
        "const": [7] * n,
        "near": [0] * (n - 1) + [1],
        "Destination Port": np.arange(n),
        "Idle Mean": np.arange(n, dtype=float),
        "Label": ["A", "B"] * (n // 2),
    })
    f = _assess(df, cfg)
    assert _has(f, "Relevance", "n_unique", "const")
    assert _has(f, "Relevance", "top_value_share", "near")
    assert _has(f, "Relevance", "identifier_like_name", "Destination Port")
    assert not _has(f, "Relevance", "identifier_like_name", "Idle Mean")


def test_class_imbalance_and_tiny_class(cfg):
    df = pd.DataFrame({"x": range(1010), "Label": ["BENIGN"] * 1000 + ["Rare"] * 10})
    f = _assess(df, cfg)
    imb = [x for x in f if x.metric == "imbalance_ratio"][0]
    assert imb.severity == "high" and imb.value == 100.0
    assert not _has(f, "Class imbalance", "classes_below_min_samples")  # 10 is not < 10

    df2 = pd.DataFrame({"x": range(1005), "Label": ["BENIGN"] * 1000 + ["Rare"] * 5})
    tiny = [x for x in _assess(df2, cfg) if x.metric == "classes_below_min_samples"][0]
    assert tiny.value == {"Rare": 5}


def test_balanced_classes_produce_no_imbalance_finding(cfg):
    df = pd.DataFrame({"x": range(100), "Label": ["A", "B"] * 50})
    assert not any(f.dimension == "Class imbalance" for f in _assess(df, cfg))


def test_label_variants_and_encoding_artifacts(cfg):
    df = pd.DataFrame({"x": range(4), "Label": ["Web Attack", "web attack", "Web Attack � XSS", "BENIGN"]})
    f = _assess(df, cfg)
    assert _has(f, "Consistency", "label_spelling_variants")
    assert _has(f, "Consistency", "labels_with_non_ascii_chars")


def test_dtype_mismatch_numeric_stored_as_text(cfg):
    df = pd.DataFrame({"n": ["1", "2", "3", "4"], "Label": list("AABB")})
    assert _has(_assess(df, cfg), "Data type", "numeric_like_share", "n")


def test_outliers_are_info_only(cfg):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 1000.0, 2.5, 3.5], "Label": list("AABBAAB")})
    out = [f for f in _assess(df, cfg) if f.dimension == "Outliers"]
    assert out and all(f.severity == "info" for f in out)


def test_sample_provenance_finding(cfg):
    df = pd.DataFrame({"x": [1, 2], "Label": ["A", "B"]})
    assert _has(_assess(df, cfg, {"is_full_dataset": False, "sample_fraction": 0.1}), "Provenance", "sample_fraction")
    assert not _has(_assess(df, cfg, {"is_full_dataset": True}), "Provenance", "sample_fraction")


def test_no_composite_score_in_summary(cfg):
    df = pd.DataFrame({"x": [1, 1, 2], "Label": ["A", "A", "B"]})
    summary = summarize_findings(_assess(df, cfg))
    assert "score" not in " ".join(map(str, summary.columns)).lower()


def test_report_files_written(cfg, tmp_path):
    q, p = cfg
    df = pd.DataFrame({"Destination Port": [1, 2, 3, 4], "x": [1.0, np.nan, 3.0, 4.0], "Label": list("AABB")})
    profile = profile_dataframe(df, "Label")
    findings = assess_quality(profile, q, p)
    meta = {"n_files": 1, "fingerprint": "abc", "fingerprint_includes_content_hash": True,
            "rows_in_files": 4, "rows_loaded": 4, "is_full_dataset": True,
            "sample_fraction": None, "random_seed": 42}
    paths = write_quality_outputs(profile, findings, meta, tmp_path)
    assert all(pth.exists() for pth in paths.values())
    md = paths["report"].read_text(encoding="utf-8")
    assert "No composite quality score" in md and "Full dataset: True" in md
    assert json.loads(paths["summary"].read_text())["metadata"]["fingerprint"] == "abc"
