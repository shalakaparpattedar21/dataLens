"""Data quality assessment: turn profile measurements into findings.

Each Finding separates what was MEASURED (metric/value) from what it MEANS
(explanation) and what to DO (recommendation).

There is deliberately NO composite "quality score". A single number would hide
trade-offs (e.g. 30% duplicates vs. one NaN column) and depend on arbitrary weights.
Use summarize_findings() for counts per dimension and severity instead.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

SEVERITY_ORDER = ["high", "medium", "low", "info"]


@dataclass
class Finding:
    dimension: str       # Completeness | Validity | Uniqueness | Consistency | Data type |
                         # Relevance | Cardinality | Class imbalance | Outliers | Provenance
    severity: str        # high | medium | low | info
    column: str | None
    metric: str
    value: Any           # the measured number(s)
    explanation: str     # interpretation
    recommendation: str


def _tokens(name: str) -> set[str]:
    """Lower-case word tokens of a column name ('Flow ID' -> {'flow','id'})."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))
    return {t for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if t}


def _normalize_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(label).lower())


def assess_quality(
    profile: dict[str, Any],
    quality_cfg: dict[str, Any],
    profiling_cfg: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> list[Finding]:
    """Generate quality findings from a profile (see datalens.profiling)."""
    findings: list[Finding] = []
    n_rows = profile["shape"]["rows"]
    cols = profile["columns"]

    # ---- Provenance: never let a sample pass as the full dataset -------------------
    if metadata is not None and not metadata.get("is_full_dataset", True):
        findings.append(Finding(
            "Provenance", "info", None, "sample_fraction", metadata["sample_fraction"],
            "All numbers in this report come from a random sample, not the full dataset.",
            "Label every result with the sample fraction; rerun on the full data before concluding.",
        ))

    # ---- Completeness ----------------------------------------------------------------
    for c in cols:
        if c["missing_n"] > 0:
            pct = c["missing_pct"]
            sev = "high" if pct >= quality_cfg["missing_pct_high"] else ("medium" if pct >= 1 else "low")
            findings.append(Finding(
                "Completeness", sev, c["column"], "missing_pct", pct,
                f"{c['missing_n']} of {n_rows} values are missing.",
                "Impute with statistics fitted on the training split only; check whether "
                "missingness differs by class before dropping rows.",
            ))

    # ---- Validity: infinite values, suspicious negatives -------------------------------
    nonneg_kw = set(quality_cfg["non_negative_keywords"])
    for c in cols:
        if c["kind"] != "numeric":
            continue
        if c.get("inf_n", 0) > 0:
            pct = round(100 * c["inf_n"] / n_rows, 4)
            sev = "high" if pct >= quality_cfg["missing_pct_high"] else "medium"
            findings.append(Finding(
                "Validity", sev, c["column"], "inf_count", c["inf_n"],
                "Infinite values are not valid measurements; they typically come from a "
                "division by zero when the feature was computed (e.g. a rate over zero duration).",
                "Convert inf to NaN, then handle like missing values (train-fit imputation). "
                "Investigate which rows are affected.",
            ))
        if c.get("negative_n", 0) > 0 and (_tokens(c["column"]) & nonneg_kw):
            findings.append(Finding(
                "Validity", "medium", c["column"], "negative_count", c["negative_n"],
                "Negative values in a column that should be non-negative by name. They may be "
                "legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, "
                "not proven invalid.",
                "Check the dataset documentation / feature definition before changing anything; "
                "do not drop these rows blindly.",
            ))

    # ---- Uniqueness ---------------------------------------------------------------------
    d = profile["duplicates"]
    if d["n_rows"]:
        dup_pct = round(100 * d["duplicate_rows_full"] / d["n_rows"], 4)
        if d["duplicate_rows_full"] > 0:
            sev = "medium" if dup_pct >= quality_cfg["duplicate_pct_warn"] else "low"
            findings.append(Finding(
                "Uniqueness", sev, None, "duplicate_rows_pct", dup_pct,
                f"{d['duplicate_rows_full']} rows repeat an earlier row exactly (features and label). "
                "If duplicates land in both train and test, test scores are inflated.",
                "Deduplicate BEFORE splitting, and report how many rows were removed.",
            ))
        if d["label_conflict_rows"] > 0:
            findings.append(Finding(
                "Uniqueness", "high", None, "label_conflict_rows", d["label_conflict_rows"],
                f"{d['label_conflict_groups']} feature vectors appear with more than one label "
                f"({d['label_conflict_rows']} rows). No model can separate identical inputs, so this "
                "sets a floor on achievable error and may indicate label noise.",
                "Inspect which classes conflict; decide (and document) whether to merge, drop, or keep "
                "them as irreducible error.",
            ))

    # ---- Consistency: label naming and encoding artifacts ------------------------------------
    labels = list(profile["target"]["counts"].keys())
    groups: dict[str, list[str]] = {}
    for lab in labels:
        groups.setdefault(_normalize_label(lab), []).append(lab)
    variants = {k: v for k, v in groups.items() if len(v) > 1}
    if variants:
        findings.append(Finding(
            "Consistency", "medium", None, "label_spelling_variants", list(variants.values()),
            "Different label strings normalize to the same text (case/spacing/punctuation).",
            "Map variants to one canonical label before training.",
        ))
    odd = [lab for lab in labels if "�" in lab or not lab.isascii()]
    if odd:
        findings.append(Finding(
            "Consistency", "medium", None, "labels_with_non_ascii_chars", odd,
            "Label names contain non-ASCII or replacement characters, usually a file-encoding artifact.",
            "Normalize label text (decode with the right encoding or map to ASCII names).",
        ))

    # ---- Data type mismatches ---------------------------------------------------------------------
    for c in cols:
        if c["kind"] == "categorical" and (c.get("numeric_like_share") or 0) >= 0.95:
            findings.append(Finding(
                "Data type", "medium", c["column"], "numeric_like_share", round(c["numeric_like_share"], 4),
                "Column is stored as text but almost all values parse as numbers.",
                "Convert with pd.to_numeric(errors='coerce') and inspect the values that fail to parse.",
            ))

    # ---- Relevance: constant / near-constant / identifier-like ------------------------------------------
    near_thr = profiling_cfg["near_constant_threshold"]
    id_kw = set(quality_cfg["identifier_keywords"])
    for c in cols:
        if c["is_constant"]:
            findings.append(Finding(
                "Relevance", "medium", c["column"], "n_unique", c["n_unique"],
                "Constant column: carries no information for classification.",
                "Safe to drop (constant on all loaded data). Re-check if you are working from a sample.",
            ))
        elif c["top_value_share"] is not None and c["top_value_share"] >= near_thr:
            findings.append(Finding(
                "Relevance", "low", c["column"], "top_value_share", round(c["top_value_share"], 5),
                "Near-constant column. In intrusion data a rare value can still mark an attack.",
                "Do NOT drop automatically; judge with feature importance on training data.",
            ))
        if _tokens(c["column"]) & id_kw:
            findings.append(Finding(
                "Relevance", "medium", c["column"], "identifier_like_name", True,
                "Name suggests an identifier, address, port or timestamp. Such columns can act as "
                "shortcuts that reflect how the data was collected rather than attack behaviour.",
                "Treat as a leakage risk: compare model performance with and without it before deciding.",
            ))

    # ---- High cardinality -------------------------------------------------------------------------------------
    for c in cols:
        if c["kind"] == "categorical" and c["unique_ratio"] > profiling_cfg["high_cardinality_ratio"]:
            findings.append(Finding(
                "Cardinality", "medium", c["column"], "unique_ratio", c["unique_ratio"],
                "Most values are unique: one-hot encoding would explode the feature space and the "
                "column behaves like an identifier.",
                "Drop it or use a justified compact encoding; do not one-hot encode.",
            ))

    # ---- Class imbalance ------------------------------------------------------------------------------------------------
    t = profile["target"]
    ratio = t["imbalance_ratio"]
    if ratio is not None and ratio >= quality_cfg["imbalance_ratio_warn"]:
        sev = "high" if ratio >= quality_cfg["imbalance_ratio_high"] else "medium"
        findings.append(Finding(
            "Class imbalance", sev, None, "imbalance_ratio", round(ratio, 2),
            f"Majority class '{t['majority_class']}' vs minority '{t['minority_class']}'. "
            "Accuracy will be dominated by the majority class and can look high for a poor detector.",
            "Report macro-F1, per-class recall and PR-AUC; use stratified splits; any resampling "
            "or class weighting must be applied to the training split only.",
        ))
    tiny = {k: v for k, v in t["counts"].items() if v < quality_cfg["min_class_samples"]}
    if tiny:
        findings.append(Finding(
            "Class imbalance", "high", None, "classes_below_min_samples", tiny,
            f"Classes with fewer than {quality_cfg['min_class_samples']} rows cannot be stratified "
            "across train/test/CV folds and give unreliable per-class metrics.",
            "Merge with a related class, exclude from per-class claims, or evaluate separately; document it.",
        ))

    # ---- Outliers (informational only) ----------------------------------------------------------------------------------------
    flagged = [(c["column"], c["outlier_iqr_n"]) for c in cols
               if c["kind"] == "numeric" and c.get("outlier_iqr_n", 0) > 0 and not c.get("iqr_zero")]
    if flagged:
        flagged.sort(key=lambda x: -x[1])
        findings.append(Finding(
            "Outliers", "info", None, "columns_with_iqr_outliers", len(flagged),
            "IQR-flagged points are SUSPICIOUS, not wrong: in traffic data, extreme values are often "
            "legitimate bursts or the attacks themselves.",
            "Do not remove by rule. If handling is needed, prefer robust scaling or tree models; "
            f"largest counts: {flagged[:5]}",
        ))

    order = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    findings.sort(key=lambda f: (order[f.severity], f.dimension, f.column or ""))
    return findings


def findings_frame(findings: list[Finding]) -> pd.DataFrame:
    return pd.DataFrame([asdict(f) for f in findings])


def summarize_findings(findings: list[Finding]) -> pd.DataFrame:
    """Count of findings per dimension x severity (no composite score by design)."""
    if not findings:
        return pd.DataFrame()
    df = findings_frame(findings)
    table = pd.crosstab(df["dimension"], df["severity"])
    return table.reindex(columns=[s for s in SEVERITY_ORDER if s in table.columns])
