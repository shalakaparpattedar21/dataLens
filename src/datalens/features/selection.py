"""Feature selection as pipeline steps, exclusion logging and feature metadata.

LEAKAGE RULE: selectors are sklearn transformers. Placed inside a Pipeline they are fitted on
the training data only (and on each training fold under cross-validation). Never fit a selector
on the full dataset, and never score features with test labels.

Note on VarianceThreshold: it is scale-dependent. After StandardScaler every feature has
variance 1, so only threshold 0.0 (drop constants) is meaningful after scaling.

Order of operations: log and drop zero-variance features (ExclusionLog) BEFORE univariate
selectors such as kbest_f, whose F statistic is 0/0 = NaN for a constant column.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectFromModel, SelectKBest, VarianceThreshold, f_classif, mutual_info_classif
from sklearn.pipeline import Pipeline

SELECTION_METHODS = ("none", "variance", "kbest_f", "kbest_mi", "model_rf")


def build_selector(method: str, k: int = 30, variance_threshold: float = 0.0, seed: int = 42,
                   n_estimators: int = 100, n_jobs: int = 1):
    """Return an UNFITTED selector step ('passthrough' for 'none')."""
    if method not in SELECTION_METHODS:
        raise ValueError(f"method must be one of {SELECTION_METHODS}, got '{method}'")
    if method == "none":
        return "passthrough"
    if method == "variance":
        return VarianceThreshold(threshold=variance_threshold)
    if k <= 0:
        raise ValueError("k must be positive")
    if method == "kbest_f":
        return SelectKBest(f_classif, k=k)
    if method == "kbest_mi":
        # mutual information is expensive on millions of rows: fit it on a bounded sample (see fitting.py)
        return SelectKBest(lambda X, y: mutual_info_classif(X, y, random_state=seed), k=k)
    rf = RandomForestClassifier(n_estimators=n_estimators, max_depth=12, random_state=seed, n_jobs=n_jobs)
    return SelectFromModel(rf, max_features=k, threshold=-np.inf)


def make_selection_pipeline(preprocessor, selector, estimator: BaseEstimator) -> Pipeline:
    """preprocess -> select -> classify. One object: cross-validation refits every step per fold."""
    return Pipeline([("prep", preprocessor), ("select", selector), ("clf", estimator)])


def selected_feature_names(fitted_pipeline: Pipeline) -> list[str]:
    """Names kept by the (fitted) selector step, in transformed-feature space."""
    names = np.asarray(fitted_pipeline.named_steps["prep"].get_feature_names_out(), dtype=object)
    sel = fitted_pipeline.named_steps["select"]
    if sel == "passthrough":
        return list(names)
    return list(names[sel.get_support()])


class ExclusionLog:
    """Every excluded feature must come with a reason and evidence. Nothing is dropped silently."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    def add(self, feature: str, reason: str, evidence: Any) -> None:
        if not reason or evidence is None:
            raise ValueError(f"Exclusion of '{feature}' needs both a reason and evidence")
        if feature in self._entries:
            raise ValueError(f"Feature '{feature}' is already excluded: {self._entries[feature]['reason']}")
        self._entries[feature] = {"reason": reason, "evidence": evidence}

    @property
    def features(self) -> list[str]:
        return list(self._entries)

    def apply(self, columns: list[str]) -> list[str]:
        """Return `columns` without excluded features; raise if an excluded feature is unknown."""
        missing = [f for f in self._entries if f not in columns]
        if missing:
            raise KeyError(f"Excluded features not among the columns: {missing}")
        return [c for c in columns if c not in self._entries]

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return dict(self._entries)


def map_to_original(transformed: str, originals: list[str]) -> str | None:
    """Trace a transformed feature name to the original column it came from."""
    if transformed in originals:
        return transformed
    if transformed.startswith("missingindicator_") and transformed[len("missingindicator_"):] in originals:
        return transformed[len("missingindicator_"):]
    cands = [o for o in originals if transformed.startswith(o + "_")]   # one-hot: '<col>_<category>'
    return max(cands, key=len) if cands else None


def build_feature_metadata(
    original_features: list[str], exclusions: ExclusionLog, preprocessor=None, selected: list[str] | None = None,
    transformations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reproducible record: original, excluded (with reasons), modeling, transformed, selected, mapping."""
    excluded = exclusions.to_dict()
    unknown = [f for f in excluded if f not in original_features]
    if unknown:
        raise KeyError(f"Excluded features not in original features: {unknown}")
    modeling = [f for f in original_features if f not in excluded]
    meta: dict[str, Any] = {
        "original_features": list(original_features), "n_original": len(original_features),
        "excluded_features": excluded, "modeling_features": modeling, "n_modeling": len(modeling),
        "transformations": transformations or {},
    }
    if preprocessor is not None:
        names = [str(n) for n in preprocessor.get_feature_names_out()]
        meta["transformed_features"] = names
        meta["transformed_to_original"] = {n: map_to_original(n, modeling) for n in names}
    if selected is not None:
        meta["selected_features"] = list(selected)
        meta["n_selected"] = len(selected)
        meta["removed_by_selection"] = [n for n in meta.get("transformed_features", []) if n not in set(selected)]
    return meta
