"""K-means clustering for Phase C (T071, FR-009, research D2).

Determinism axes used here (Phase 2 §5):
  1. KMeans random_state = caller-provided seed (qa Stage-2 candidate 2).
  2. Sort the substantive scores by ``student_id`` ascending before fit so
     row order is invariant under input permutation.
  4. n_init="auto" pinned (sklearn ≥1.4) so re-runs converge identically.

NaN handling: rows whose every axis score is NaN are excluded from the fit
*and* from the labelled output. Their student_ids are returned in
``info["excluded_student_ids"]`` so the pipeline can mark them in the manifest
(adversary H-3 mitigation: never silently drop).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

if TYPE_CHECKING:
    pass

_AXIS_COLUMNS: tuple[str, ...] = (
    "motivation",
    "anxiety",
    "self_efficacy",
    "interest",
    "prior_knowledge",
    "life_context",
)


def _present_axis_columns(scores_df: pd.DataFrame) -> list[str]:
    return [c for c in _AXIS_COLUMNS if c in scores_df.columns]


def _drop_all_nan_rows(
    scores_df: pd.DataFrame, axes: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    """Return (substantive_df, excluded_student_ids) sorted by student_id."""
    sorted_df = scores_df.sort_values("student_id").reset_index(drop=True)
    if not axes:
        return sorted_df.iloc[0:0], sorted_df["student_id"].tolist()
    mask = sorted_df[axes].notna().any(axis=1)
    excluded = sorted_df.loc[~mask, "student_id"].tolist()
    return sorted_df.loc[mask].reset_index(drop=True), excluded


def cluster_students(
    scores_df: pd.DataFrame,
    k: int,
    seed: int,  # required-for: SC-002 / FR-009 (qa Stage-2 candidate 2 closure)
) -> tuple[np.ndarray, dict]:
    """K-means cluster the substantive students into ``k`` groups.

    Args:
        scores_df: One row per student with at least one of the six standard
            axis columns + a ``student_id`` column. NaN cells in remaining axes
            are mean-imputed *within the substantive subset* before fitting so
            students with partial coverage still cluster.
        k: Number of clusters (1 ≤ k ≤ 6). ``k=1`` short-circuits to a
            single-cluster assignment without invoking sklearn.
        seed: Random seed for ``KMeans(random_state=seed)`` — no default to
            force pipeline to thread NeedsMapArgs.seed through (qa Stage-2 #2).

    Returns:
        ``(labels, info)`` — ``labels`` is an ``np.ndarray`` of length equal to
        the substantive (non-all-NaN) row count, in student_id-sorted order.
        ``info`` carries ``centroids`` (k × len(axes)), ``axes_used`` (list),
        ``excluded_student_ids`` (list of student_ids dropped for all-NaN),
        and ``substantive_student_ids`` (sorted ids of the labelled rows).

    Raises:
        ValueError: If ``k < 1`` or ``k > 6`` or ``scores_df`` lacks
            ``student_id``.
    """
    if not isinstance(k, int) or k < 1 or k > 6:
        raise ValueError(f"cluster_students: k must be in [1, 6], got k={k!r}.")
    if "student_id" not in scores_df.columns:
        raise ValueError("cluster_students: scores_df must contain 'student_id' column.")

    axes = _present_axis_columns(scores_df)
    substantive, excluded = _drop_all_nan_rows(scores_df, axes)
    n = len(substantive)

    if n == 0:
        return np.empty(0, dtype=int), {
            "centroids": np.empty((0, len(axes)), dtype=float),
            "axes_used": axes,
            "excluded_student_ids": excluded,
            "substantive_student_ids": [],
        }

    if k == 1 or n < k:
        labels = np.zeros(n, dtype=int)
        # Single-cluster centroid = mean over substantive rows
        if axes:
            matrix = substantive[axes].astype(float).to_numpy()
            # Mean-impute remaining NaNs per column for the centroid
            col_means = np.nanmean(matrix, axis=0)
            col_means = np.where(np.isnan(col_means), 0.0, col_means)
            centroid = col_means.reshape(1, -1)
        else:
            centroid = np.empty((1, 0))
        return labels, {
            "centroids": centroid,
            "axes_used": axes,
            "excluded_student_ids": excluded,
            "substantive_student_ids": substantive["student_id"].tolist(),
        }

    # Mean-impute NaN within substantive rows so KMeans does not crash on NaN.
    # .copy() guarantees a writable buffer (some pandas/pyarrow paths return read-only).
    matrix = substantive[axes].astype(float).to_numpy().copy()
    col_means = np.nanmean(matrix, axis=0)
    col_means = np.where(np.isnan(col_means), 0.0, col_means)
    inds = np.where(np.isnan(matrix))
    matrix[inds] = np.take(col_means, inds[1])

    model = KMeans(n_clusters=k, random_state=seed, n_init="auto")
    labels = model.fit_predict(matrix)
    return labels.astype(int), {
        "centroids": model.cluster_centers_,
        "axes_used": axes,
        "excluded_student_ids": excluded,
        "substantive_student_ids": substantive["student_id"].tolist(),
        "_imputed_matrix": matrix,
    }
