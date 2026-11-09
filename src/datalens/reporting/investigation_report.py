"""Write the dataset investigation (label encoding, missing, inf, duplicates) to disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def df_to_md(df: pd.DataFrame, index: bool = True) -> str:
    """Minimal Markdown table (avoids a 'tabulate' dependency)."""
    d = df.reset_index() if index else df
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    sep = "|" + "---|" * len(d.columns)
    rows = ["| " + " | ".join(str(v).replace("|", "\\|") for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def _split_key(key: str) -> tuple[str, str]:
    label, col = key.rsplit("|", 1)
    return label, col


def build_investigation_markdown(inv: dict[str, Any], hardware: dict[str, Any] | None = None) -> str:
    le, mi, dup = inv["label_encoding"], inv["missing_and_infinite"], inv["duplicates"]
    L = ["# Dataset investigation (measured from raw files)", "",
         f"Files ({len(inv['files'])}): " + ", ".join(inv["files"]), ""]
    if hardware:
        L += [f"Hardware: {hardware}", ""]

    L += ["## C. Label encoding", "",
          f"- Distinct raw label byte-strings: {le['n_distinct_raw_byte_labels']}",
          f"- Kinds found: {le['kinds_found']}",
          f"- **Original files contain a UTF-8 replacement character: {le['original_files_contain_utf8_replacement_char']}**",
          f"- **Class counts split by inconsistent encoding: {le['class_counts_split_by_inconsistent_encoding']}**",
          f"- Interpretation hint: {le['interpretation_hint']}", ""]
    if le["non_ascii_labels"]:
        t = pd.DataFrame([{"file": r["file"], "bytes_hex": r["raw_bytes_hex"], "kind": r["kind"], "rows": r["rows"],
                           "loader_style_decoding": r["loader_style_decoding"]} for r in le["non_ascii_labels"]])
        L += [df_to_md(t, index=False), ""]
    if le["distinct_raw_forms_per_clean_label"]:
        L += ["Clean labels that have several raw spellings (safe merges: identical after artifact removal):", "",
              *[f"- `{c}` <- {raws}" for c, raws in le["distinct_raw_forms_per_clean_label"].items()], ""]
    if le["similar_not_merged"]:
        L += [f"Similar but NOT merged (differ by more than an artifact): {le['similar_not_merged']}", ""]
    L += ["Label counts after artifact removal:", "",
          df_to_md(pd.Series(le["clean_label_counts"], name="rows").to_frame(), index=True), ""]

    L += ["## A. Missing values", "",
          f"- Total NaN cells: {mi['total_nan_cells']:,}  (rows scanned: {mi['rows']:,})",
          f"- Cells that were non-numeric text and failed to parse: {sum(mi['unparseable_by_column'].values()):,}", ""]
    if mi["nan_by_column"]:
        L += [df_to_md(pd.Series(mi["nan_by_column"], name="nan_cells").sort_values(ascending=False).to_frame()), ""]
    L += ["## B. Infinite values", "",
          f"- +inf cells: {mi['total_pos_inf_cells']:,}   -inf cells: {mi['total_neg_inf_cells']:,}", ""]
    if mi["pos_inf_by_column"] or mi["neg_inf_by_column"]:
        inf_t = pd.DataFrame({"pos_inf": pd.Series(mi["pos_inf_by_column"]), "neg_inf": pd.Series(mi["neg_inf_by_column"]),
                              "inf_with_flow_duration_0": pd.Series(mi["inf_cells_with_zero_flow_duration"])}).fillna(0).astype(int)
        L += [df_to_md(inf_t), "",
              "`inf_with_flow_duration_0` counts inf cells in rows whose Flow Duration is 0: evidence for/against "
              "the division-by-zero explanation.", ""]
    L += ["### By file", "", df_to_md(pd.DataFrame(mi["by_file"]).T), "",
          "### By class (share of that class's rows)", "", df_to_md(pd.DataFrame(mi["by_class"]).T), ""]

    L += ["## D. Duplicates", ""]
    for k in ("rows", "exact_duplicate_rows_global", "exact_duplicate_rows_within_file", "exact_duplicates_only_across_files",
              "label_conflict_groups", "label_conflict_rows", "vectors_spanning_multiple_files", "rows_in_spanning_vectors",
              "spanning_vectors_with_label_disagreement"):
        L.append(f"- {k}: {dup[k]:,}")
    L += ["", "### Per class (what `drop_exact` would remove)", "",
          df_to_md(pd.DataFrame(dup["per_class"]).T.sort_values("rows", ascending=False)), ""]
    return "\n".join(L) + "\n"


def write_investigation_outputs(inv: dict[str, Any], out_dir: str | Path, hardware: dict[str, Any] | None = None) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mi, dup = inv["missing_and_infinite"], inv["duplicates"]
    paths = {k: out / v for k, v in {
        "json": "investigation.json", "report": "investigation_report.md", "missing_by_class": "missing_inf_by_class.csv",
        "inf_by_class_column": "inf_cells_by_class_column.csv", "duplicates_by_class": "duplicates_by_class.csv"}.items()}
    paths["json"].write_text(json.dumps(inv, indent=2, default=str), encoding="utf-8")
    paths["report"].write_text(build_investigation_markdown(inv, hardware), encoding="utf-8")
    pd.DataFrame(mi["by_class"]).T.to_csv(paths["missing_by_class"], index_label="class")
    rows = [{"class": _split_key(k)[0], "column": _split_key(k)[1], "inf_cells": v}
            for k, v in mi["inf_cells_by_class_column"].items()]
    pd.DataFrame(rows, columns=["class", "column", "inf_cells"]).to_csv(paths["inf_by_class_column"], index=False)
    pd.DataFrame(dup["per_class"]).T.to_csv(paths["duplicates_by_class"], index_label="class")
    return paths
