"""Label canonicalization with full traceability.

Problem: CIC-IDS2017 label names such as "Web Attack - Brute Force" contain a dash that
appears in the files as a non-UTF-8 byte (0x96 in cp1252). Decoded wrongly it becomes a
control character (latin-1) or a replacement character (errors="replace"), so one logical
class can end up with several spellings, splitting its counts.

Rules (deliberately narrow):
- Only characters in ARTIFACT_CHARS are treated as encoding artifacts and removed.
  ASCII hyphens are NOT touched, so 'FTP-Patator' stays 'FTP-Patator'.
- Two raw labels are merged only if they become IDENTICAL after artifact removal and
  whitespace collapsing. Labels that merely look similar (e.g. differ by an ASCII hyphen)
  are reported in `similar_not_merged` and are NEVER merged automatically.
- The original label is preserved in a separate column for traceability.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

# cp1252 dash read as latin-1, en dash, em dash, minus sign, Unicode replacement char.
ARTIFACT_CHARS = "\x96–—−�"


def clean_label(label: str, artifact_chars: str = ARTIFACT_CHARS) -> str:
    """Remove known artifact characters and collapse whitespace."""
    s = str(label)
    for ch in artifact_chars:
        s = s.replace(ch, " ")
    return re.sub(r"\s+", " ", s).strip()


def _similarity_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", label.lower())


def build_label_mapping(
    raw_counts: pd.Series, artifact_chars: str = ARTIFACT_CHARS
) -> tuple[dict[str, str], dict[str, Any]]:
    """Map raw labels to canonical labels from a value_counts() Series.

    Returns (mapping, report). The report lists every changed label, the merges it caused
    and similar-but-different labels that were deliberately left alone.
    """
    mapping = {str(raw): clean_label(raw, artifact_chars) for raw in raw_counts.index}
    clean_counts: dict[str, int] = {}
    merged_from: dict[str, list[str]] = {}
    for raw, n in raw_counts.items():
        c = mapping[str(raw)]
        clean_counts[c] = clean_counts.get(c, 0) + int(n)
        merged_from.setdefault(c, []).append(str(raw))

    changed = [
        {"raw_label": raw, "clean_label": c, "rows": int(raw_counts[raw])}
        for raw, c in mapping.items() if raw != c
    ]
    merges = {c: raws for c, raws in merged_from.items() if len(raws) > 1}

    by_key: dict[str, list[str]] = {}
    for c in clean_counts:
        by_key.setdefault(_similarity_key(c), []).append(c)
    similar = [sorted(v) for v in by_key.values() if len(v) > 1]

    report = {
        "n_raw_labels": int(len(raw_counts)),
        "n_clean_labels": len(clean_counts),
        "changed_labels": changed,
        "merged_groups": merges,
        "similar_not_merged": similar,
        "clean_counts": dict(sorted(clean_counts.items(), key=lambda kv: -kv[1])),
        "artifact_chars_removed": [f"U+{ord(c):04X}" for c in artifact_chars],
    }
    return mapping, report


def canonicalize_labels(
    df: pd.DataFrame,
    label_column: str,
    raw_column: str = "label_raw",
    artifact_chars: str = ARTIFACT_CHARS,
) -> dict[str, Any]:
    """Canonicalize df[label_column] IN PLACE, keeping the original in df[raw_column].

    Both columns are stored as pandas categoricals (cheap even for millions of rows).
    Returns the mapping report. Raises if raw_column already exists (never overwrite
    traceability information).
    """
    if label_column not in df.columns:
        raise KeyError(f"Label column '{label_column}' not in DataFrame")
    if raw_column in df.columns:
        raise ValueError(f"'{raw_column}' already exists; refusing to overwrite original labels")
    if df[label_column].isna().any():
        raise ValueError("Label column contains missing values; resolve them before canonicalizing")

    raw = df[label_column].astype(str)
    mapping, report = build_label_mapping(raw.value_counts(), artifact_chars)
    df[raw_column] = raw.astype("category")
    df[label_column] = raw.map(mapping).astype("category")
    return report


def binarize_labels(y, benign_label: str = "BENIGN"):
    """1 for any attack class, 0 for the benign label. Raises if benign_label is absent.

    Useful for held-out-day evaluation where attack classes are unseen in training.
    """
    arr = pd.Series(y).astype(str)
    if benign_label not in set(arr):
        raise ValueError(f"benign label '{benign_label}' not found in labels")
    return (arr != benign_label).astype(int).to_numpy()
