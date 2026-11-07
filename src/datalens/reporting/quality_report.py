"""Write profiling and quality outputs to disk (CSV, JSON and a Markdown report)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens.profiling import columns_frame
from datalens.quality import Finding, findings_frame, summarize_findings


def _md_escape(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def build_markdown(profile: dict[str, Any], findings: list[Finding], metadata: dict[str, Any]) -> str:
    t, d, shape = profile["target"], profile["duplicates"], profile["shape"]
    lines = [
        "# Dataset quality report",
        "",
        "Sections marked **Measured** are computed from the data. Explanations and "
        "recommendations are **interpretation**.",
        "",
        "## Dataset (measured)",
        "",
        f"- Files: {metadata['n_files']}; fingerprint `{metadata['fingerprint']}` "
        f"(content hash included: {metadata['fingerprint_includes_content_hash']})",
        f"- Rows in files: {metadata['rows_in_files']:,}; rows analysed: {metadata['rows_loaded']:,}",
        f"- **Full dataset: {metadata['is_full_dataset']}**"
        + ("" if metadata["is_full_dataset"] else f" (random sample, fraction {metadata['sample_fraction']}, seed {metadata['random_seed']})"),
        f"- Feature columns: {shape['feature_columns']}; in-memory size: {profile['memory_mb']} MB",
        f"- Exact duplicate rows: {d['duplicate_rows_full']:,}; rows in label-conflicting feature groups: {d['label_conflict_rows']:,}",
        "",
        "## Class distribution (measured)",
        "",
        "| class | rows | percent |",
        "|---|---:|---:|",
        *[f"| {_md_escape(k)} | {v:,} | {t['percent'][k]} |" for k, v in t["counts"].items()],
        "",
        "## Findings per dimension and severity (measured counts)",
        "",
        "No composite quality score is computed: a single number would hide trade-offs.",
        "",
    ]
    summary = summarize_findings(findings)
    if summary.empty:
        lines.append("_No findings._")
    else:
        lines += ["| dimension | " + " | ".join(summary.columns) + " |",
                  "|---|" + "---:|" * len(summary.columns)]
        lines += [f"| {dim} | " + " | ".join(str(v) for v in row) + " |" for dim, row in summary.iterrows()]
    lines += ["", "## Findings (measured value, then interpretation)", ""]
    if findings:
        lines += ["| severity | dimension | column | metric | value | explanation | recommendation |",
                  "|---|---|---|---|---|---|---|"]
        for f in findings:
            lines.append(
                f"| {f.severity} | {f.dimension} | {_md_escape(f.column or '-')} | {f.metric} | "
                f"{_md_escape(f.value)} | {_md_escape(f.explanation)} | {_md_escape(f.recommendation)} |"
            )
    return "\n".join(lines) + "\n"


def write_quality_outputs(
    profile: dict[str, Any],
    findings: list[Finding],
    metadata: dict[str, Any],
    out_dir: str | Path,
) -> dict[str, Path]:
    """Write profile_columns.csv, quality_findings.csv, profile_summary.json, quality_report.md."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "columns": out / "profile_columns.csv",
        "findings": out / "quality_findings.csv",
        "summary": out / "profile_summary.json",
        "report": out / "quality_report.md",
    }
    columns_frame(profile).to_csv(paths["columns"], index=False)
    findings_frame(findings).to_csv(paths["findings"], index=False)
    summary = {k: v for k, v in profile.items() if k != "columns"}
    paths["summary"].write_text(
        json.dumps({"metadata": metadata, "profile": summary}, indent=2, default=str), encoding="utf-8"
    )
    paths["report"].write_text(build_markdown(profile, findings, metadata), encoding="utf-8")
    return paths
