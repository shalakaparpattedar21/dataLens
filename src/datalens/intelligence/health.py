"""Dataset Health Score and ML-readiness assessment: deterministic, evidence-based, fully documented.

Every dimension is computed from backend findings with an explicit formula (METHODOLOGY). A dimension whose
evidence is missing is reported as ``score: null`` ("Insufficient data") and is excluded from the overall score;
the overall score is also null when the available dimensions carry under half of the total weight.
Leakage cannot be averaged away: confirmed/potential critical or high findings cap the overall score.
"""
from __future__ import annotations

import math
from typing import Any

WEIGHTS = {"completeness": 0.15, "validity": 0.15, "consistency": 0.15, "uniqueness": 0.15, "distribution": 0.15, "leakage": 0.25}
# A "rate cap" is the rate at which a penalty term reaches its maximum (score contribution 0).
CAPS = {"missing_cell_rate": 0.20, "columns_with_missing": 0.50, "infinite_cell_rate": 0.01, "non_negative_violations": 0.01,
        "constant_column_share": 0.20, "label_conflict_rate": 0.01, "duplicate_rate": 0.20, "outlier_column_share": 0.50,
        "rare_class_share": 0.50}
LEAKAGE_DEDUCTION = {("confirmed", "critical"): 60, ("confirmed", "high"): 40, ("confirmed", "medium"): 20, ("confirmed", "low"): 5,
                     ("potential", "critical"): 30, ("potential", "high"): 20, ("potential", "medium"): 10, ("potential", "low"): 3}
OVERALL_CAPS = [("confirmed", "critical", 40), ("confirmed", "high", 60), ("potential", "critical", 65), ("potential", "high", 75),
                ("confirmed", "medium", 85)]

METHODOLOGY = {
    "scale": "Each dimension is 0–100 (100 = no problems measured). Penalties use pen(x, cap) = min(1, x / cap); score = 100 × (1 − Σ weight_i × pen_i).",
    "completeness": "0.5 × pen(missing cells ÷ all cells, 20%) + 0.5 × pen(share of columns with >5% missing, 50%). Source: full-data profile.",
    "validity": "0.6 × pen(infinite cells ÷ all cells, 1%) + 0.4 × pen(share of numeric sample columns with negative values where ≥99.9% of values are ≥0 [likely sentinel values], 1% of cells, capped at 50% of columns). Source: full-data profile + seeded sample.",
    "consistency": "0.6 × pen(rows with identical features but different labels ÷ rows, 1%) + 0.4 × pen(constant columns ÷ columns, 20%). Null without a target for the label-conflict term (that term is then dropped and weights renormalised).",
    "uniqueness": "pen(exact duplicate rows ÷ rows, 20%). Source: full-data duplicate scan.",
    "distribution": "With a target: 0.4 × (1 − normalised class entropy) + 0.3 × pen(share of classes with <100 rows, 50%) + 0.3 × pen(share of numeric columns with >5% IQR outliers, 50%); without a target only the outlier term is used.",
    "leakage": "100 − Σ deductions over confirmed/potential findings (confirmed: critical 60, high 40, medium 20, low 5; potential: critical 30, high 20, medium 10, low 3), floored at 0. Null if leakage has not been analysed. Not-assessed checks do not change the score but are listed.",
    "overall": "Weighted mean of the available dimensions (weights: " + ", ".join(f"{k} {v:.0%}" for k, v in WEIGHTS.items()) +
               "), renormalised over available dimensions; null if available weight < 50%. Then capped: " +
               "; ".join(f"{s} {sev} leakage ⇒ ≤{c}" for s, sev, c in OVERALL_CAPS) + ". So high completeness cannot hide serious leakage.",
    "missing_evidence": "A dimension without its inputs is 'Insufficient data' and is excluded, never imputed.",
    "readiness": "Separate from the score. 'High risk' if a confirmed critical/high leakage finding, label conflicts ≥1% of rows, or overlap ≥1% of test rows; "
                 "'Insufficient evidence' if there is no target, leakage has not been analysed, or too few dimensions; 'Needs improvement' if any other finding of medium or higher severity "
                 "is open, any dimension < 80, or no prepared run has passed validation; otherwise 'Ready for experimentation'. Successful preprocessing validation is necessary but not sufficient.",
}


def pen(x: float, cap: float) -> float:
    return min(1.0, max(0.0, x / cap))


def _round(v: float) -> float:
    return round(float(v), 1)


def _dim(name: str, score: float | None, summary: str, factors: list[dict[str, Any]], actions: list[str]) -> dict[str, Any]:
    return {"name": name, "score": None if score is None else _round(score), "label": "Insufficient data" if score is None else None,
            "weight": WEIGHTS.get(name), "summary": summary, "factors": factors, "actions": actions, "methodology": METHODOLOGY.get(name)}


def compute_health(profile: dict[str, Any] | None, distributions: dict[str, Any] | None, leakage_reports: list[dict[str, Any]],
                   run: dict[str, Any] | None, created_at: str) -> dict[str, Any]:
    if not profile:
        return {"kind": "health", "overall": None, "overall_label": "Insufficient data", "dimensions": [], "readiness": {
            "status": "insufficient_evidence", "label": "Insufficient evidence", "blockers": ["Dataset has not been profiled."]},
            "methodology": METHODOLOGY, "created_at": created_at}
    rows = max(1, int(profile.get("rows") or 0))
    cols = max(1, int(profile.get("columns") or 0))
    cells = rows * cols
    dtypes = profile.get("dtypes") or []
    target = profile.get("label_column")
    dims: list[dict[str, Any]] = []
    critical: list[dict[str, Any]] = []

    # completeness
    miss_cells = int(profile.get("missing_cells") or 0)
    cols_missing = sum(1 for c in dtypes if rows and (c.get("missing_cells", 0) / rows) > 0.05)
    p1, p2 = pen(miss_cells / cells, CAPS["missing_cell_rate"]), pen(cols_missing / cols, CAPS["columns_with_missing"])
    dims.append(_dim("completeness", 100 * (1 - (0.5 * p1 + 0.5 * p2)),
                     f"{miss_cells:,} missing cells ({100 * miss_cells / cells:.3f}% of all cells); {cols_missing} column(s) exceed 5% missing.",
                     [{"factor": "missing cell rate", "value": round(miss_cells / cells, 6), "cap": CAPS["missing_cell_rate"], "penalty": round(p1, 4), "weight": 0.5},
                      {"factor": "share of columns >5% missing", "value": round(cols_missing / cols, 4), "cap": CAPS["columns_with_missing"], "penalty": round(p2, 4), "weight": 0.5}],
                     ["Choose an imputation strategy on the Prepare page."] if miss_cells else []))

    # validity
    inf_cells = int(profile.get("positive_infinity_cells") or 0) + int(profile.get("negative_infinity_cells") or 0)
    q1 = pen(inf_cells / cells, CAPS["infinite_cell_rate"])
    neg_cols: list[str] = []
    if distributions and distributions.get("numeric"):
        for c in distributions["numeric"]:
            if c["min"] < 0 and c["q1"] >= 0 and c["outliers_low"] <= max(1, 0.001 * c["n"]) and c["median"] >= 0:
                neg_cols.append(c["column"])
        num_n = len(distributions["numeric"])
        q2 = pen(len(neg_cols) / max(1, num_n), 0.5)
        validity_terms = [(0.6, q1), (0.4, q2)]
        v_factors = [{"factor": "infinite cell rate", "value": round(inf_cells / cells, 6), "cap": CAPS["infinite_cell_rate"], "penalty": round(q1, 4), "weight": 0.6},
                     {"factor": "columns with negative sentinel-like values", "value": len(neg_cols), "of": num_n, "penalty": round(q2, 4), "weight": 0.4}]
    else:
        validity_terms = [(1.0, q1)]
        v_factors = [{"factor": "infinite cell rate", "value": round(inf_cells / cells, 6), "cap": CAPS["infinite_cell_rate"], "penalty": round(q1, 4), "weight": 1.0},
                     {"factor": "negative sentinel check", "value": None, "note": "Insufficient data: run the analysis to sample numeric columns"}]
    dims.append(_dim("validity", 100 * (1 - sum(w * p for w, p in validity_terms)),
                     f"{inf_cells:,} infinite cells" + (f"; negative values in otherwise non-negative columns: {', '.join(neg_cols[:5])}" if neg_cols else "") + ".",
                     v_factors, (["Infinite values are treated as missing during preparation."] if inf_cells else []) +
                                (["Check negative values in " + ", ".join(neg_cols[:3]) + " (often -1 sentinels)."] if neg_cols else [])))

    # consistency
    dup = profile.get("duplicates") or {}
    conflicts = int(dup.get("label_conflict_rows") or 0)
    const = len(profile.get("constant_columns") or [])
    c_terms, c_factors = [], []
    if target:
        pc = pen(conflicts / rows, CAPS["label_conflict_rate"])
        c_terms.append((0.6, pc))
        c_factors.append({"factor": "label-conflict rows ÷ rows", "value": round(conflicts / rows, 6), "cap": CAPS["label_conflict_rate"], "penalty": round(pc, 4), "weight": 0.6})
    pk = pen(const / cols, CAPS["constant_column_share"])
    c_terms.append((0.4, pk))
    c_factors.append({"factor": "constant columns ÷ columns", "value": round(const / cols, 4), "cap": CAPS["constant_column_share"], "penalty": round(pk, 4), "weight": 0.4})
    tw = sum(w for w, _ in c_terms)
    dims.append(_dim("consistency", 100 * (1 - sum(w * p for w, p in c_terms) / tw),
                     f"{conflicts:,} rows share features but disagree on the label; {const} constant column(s)." if target else f"{const} constant column(s); no target, label conflicts not assessable.",
                     c_factors, (["Investigate conflicting labels: they cap achievable accuracy."] if conflicts else []) + (["Constant columns carry no signal; use 'Remove zero variance'."] if const else [])))

    # uniqueness
    dups = int(profile.get("duplicate_rows") or 0)
    pd_ = pen(dups / rows, CAPS["duplicate_rate"])
    dims.append(_dim("uniqueness", 100 * (1 - pd_), f"{dups:,} exact duplicate rows ({100 * dups / rows:.2f}%).",
                     [{"factor": "duplicate rate", "value": round(dups / rows, 6), "cap": CAPS["duplicate_rate"], "penalty": round(pd_, 4), "weight": 1.0}],
                     ["Choose a duplicate policy on the Prepare page."] if dups else []))

    # distribution
    terms, factors, actions = [], [], []
    classes = profile.get("class_distribution") or []
    outlier_cols = profile.get("outliers") or []
    n_numeric = sum(1 for c in dtypes if c.get("dtype") and ("int" in c["dtype"] or "float" in c["dtype"]) and not c.get("constant") and c["column"] != target)
    if n_numeric:
        heavy = sum(1 for o in outlier_cols if o.get("estimated_percent", 0) > 5)
        po = pen(heavy / n_numeric, CAPS["outlier_column_share"])
        terms.append((0.3 if len(classes) >= 2 else 1.0, po))
        factors.append({"factor": "numeric columns with >5% IQR outliers", "value": heavy, "of": n_numeric, "penalty": round(po, 4), "cap": CAPS["outlier_column_share"]})
        if heavy:
            actions.append("Use robust scaling; inspect heavy-tailed columns before transforming.")
    if len(classes) >= 2:
        counts = [c["count"] for c in classes if c["count"] > 0]
        tot = sum(counts)
        h = -sum((c / tot) * math.log(c / tot) for c in counts) / math.log(len(counts)) if len(counts) > 1 else 0.0
        rare = sum(1 for c in counts if c < 100) / len(counts)
        pr = pen(rare, CAPS["rare_class_share"])
        terms += [(0.4, 1 - h), (0.3, pr)]
        factors += [{"factor": "class imbalance (1 − normalised entropy)", "value": round(1 - h, 4), "penalty": round(1 - h, 4), "weight": 0.4, "majority_share": round(max(counts) / tot, 4)},
                    {"factor": "share of classes with <100 rows", "value": round(rare, 4), "cap": CAPS["rare_class_share"], "penalty": round(pr, 4), "weight": 0.3}]
        if 1 - h > 0.3:
            actions.append("Evaluate with stratified metrics (PR-AUC, per-class recall); consider class weights.")
        if rare:
            actions.append("Rare classes may be absent from a split: prepare the full dataset and check class coverage.")
    if terms:
        dims.append(_dim("distribution", 100 * (1 - sum(w * p for w, p in terms) / sum(w for w, _ in terms)),
                         (f"{len(classes)} classes; majority class {100 * classes[0]['percent'] / 100:.1f}% of rows. " if len(classes) >= 2 else "No target classes. ") +
                         f"{len(outlier_cols)} numeric column(s) with IQR outliers.", factors, actions))
    else:
        dims.append(_dim("distribution", None, "No numeric columns or target classes to assess.", [], []))

    # leakage
    findings = [f for rep in leakage_reports for f in rep.get("findings", [])]
    if leakage_reports:
        ded = sum(LEAKAGE_DEDUCTION.get((f["status"], f["severity"]), 0) for f in findings)
        active = [f for f in findings if f["status"] in ("confirmed", "potential")]
        na = [f for f in findings if f["status"] == "not_assessed"]
        dims.append(_dim("leakage", max(0.0, 100 - ded),
                         f"{len(active)} active finding(s) ({sum(1 for f in active if f['status'] == 'confirmed')} confirmed); {len(na)} check(s) not assessed.",
                         [{"factor": f["title"], "status": f["status"], "severity": f["severity"], "deduction": LEAKAGE_DEDUCTION.get((f["status"], f["severity"]), 0)} for f in active],
                         list(dict.fromkeys(f["recommended_action"] for f in active if f.get("recommended_action")))[:3]))
        critical = [f for f in active if f["severity"] in ("critical", "high")]
    else:
        dims.append(_dim("leakage", None, "Leakage has not been analysed yet.", [], ["Run the dataset analysis."]))

    avail = [d for d in dims if d["score"] is not None]
    wsum = sum(WEIGHTS[d["name"]] for d in avail)
    overall = None
    cap_applied = None
    if wsum >= 0.5:
        overall = sum(d["score"] * WEIGHTS[d["name"]] for d in avail) / wsum
        for status, sev, cap in OVERALL_CAPS:
            if any(f["status"] == status and f["severity"] == sev for f in findings):
                if overall > cap:
                    overall, cap_applied = float(cap), f"{status} {sev} leakage finding caps the overall score at {cap}"
                break
    # --- readiness
    blockers: list[str] = []
    conf_hi = [f for f in findings if f["status"] == "confirmed" and f["severity"] in ("critical", "high")]
    unmet: list[str] = []
    status = "ready"
    ps = ((run or {}).get("comparison") or {}).get("processed_sample", {})
    passed = None if not run else (ps.get("missing_feature_cells_after") == 0 and ps.get("infinite_feature_cells_after") == 0)
    if not target:
        unmet.append("No target column: supervised readiness cannot be judged.")
    if not leakage_reports:
        unmet.append("Leakage has not been analysed.")
    if wsum < 0.5:
        unmet.append("Too few health dimensions have evidence.")
    if conf_hi:
        blockers += [f"{f['title']}: {f['evidence_text']}" for f in conf_hi]
    if conflicts / rows >= 0.01:
        blockers.append(f"{conflicts:,} rows ({100 * conflicts / rows:.2f}%) have identical features but different labels.")
    if blockers:
        status = "high_risk"
    elif unmet:
        status = "insufficient_evidence"
    else:
        improve = [f"{f['title']} ({f['severity']}, {f['status']})" for f in findings if f["status"] in ("confirmed", "potential") and f["severity"] in ("critical", "high", "medium")]
        low_dims = [f"{d['name']} {d['score']:.0f}/100" for d in avail if d["score"] < 80]
        if not run:
            improve.append("No preparation has been run and validated yet.")
        elif passed is False:
            improve.append("Latest preparation run did not pass feature validation.")
        blockers += improve + [f"Dimension below 80: {d}" for d in low_dims]
        status = "needs_improvement" if blockers else "ready"
    labels = {"ready": "Ready for experimentation", "needs_improvement": "Needs improvement", "high_risk": "High risk", "insufficient_evidence": "Insufficient evidence"}
    key = {"ready": "ready_for_experimentation"}.get(status, status)
    readiness = {"status": key, "label": labels[status], "blockers": blockers if blockers else unmet,
                 "note": "Preprocessing validation passing is necessary but not sufficient: it checks missing/infinite values in exported features, not label quality, leakage or evaluation validity.",
                 "preparation_validation": passed}
    if status == "insufficient_evidence" and unmet:
        readiness["blockers"] = unmet
    top_actions: list[dict[str, str]] = []
    for d in sorted(avail, key=lambda d: d["score"]):
        for a in d["actions"][:1]:
            top_actions.append({"dimension": d["name"], "action": a})
    return {"kind": "health", "overall": None if overall is None else _round(overall), "overall_label": "Insufficient data" if overall is None else None,
            "overall_cap": cap_applied, "dimensions": dims, "critical_findings": critical, "top_actions": top_actions[:6],
            "readiness": readiness, "methodology": METHODOLOGY, "created_at": created_at,
            "inputs": {"profile_created_at": profile.get("created_at"), "leakage_scopes": [r.get("scope") for r in leakage_reports],
                       "run_id": (run or {}).get("id")}}
