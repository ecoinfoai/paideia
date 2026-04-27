"""Silhouette-based k recommendation (T072, FR-010, research D3).

For each candidate k in ``range(2, 7)`` runs ``cluster_students(k, seed)`` and
computes ``sklearn.metrics.silhouette_score`` on the labelled output. Returns
``(k_chosen, candidate_table)`` where ties are broken by the smaller k
(parsimony — research D3).
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from paideia_shared.schemas import ClusterCandidate
from sklearn.metrics import silhouette_score

from .kmeans import cluster_students


def recommend_k(
    scores_df: pd.DataFrame,
    candidate_k: Iterable[int],
    seed: int,  # required-for: SC-002 (qa Stage-2 candidate 2 closure)
) -> tuple[int, list[ClusterCandidate]]:
    """Return (best_k, candidate_table) by argmax silhouette.

    Args:
        scores_df: Same shape as ``cluster_students`` accepts (one row per
            student, six axis columns + student_id).
        candidate_k: Iterable of k values to evaluate. Must contain only
            integers in ``[2, 6]`` per ClusterCandidate contract; ``k=1`` is
            reserved for the auto-fallback path inside the pipeline (FR-010).
        seed: Random seed threaded into ``cluster_students`` for every
            candidate. No default — caller MUST pass NeedsMapArgs.seed.

    Returns:
        ``(best_k, table)`` where ``table`` is a list of ClusterCandidate
        sorted by k ascending. Ties on silhouette resolve to the smaller k
        (research D3).

    Raises:
        ValueError: If ``candidate_k`` contains values outside ``[2, 6]`` or
            if the substantive sample is too small to compute silhouette for
            any candidate (caller treats this as ``k=1`` fallback).
    """
    candidates_list = list(candidate_k)
    invalid = [k for k in candidates_list if k < 2 or k > 6]
    if invalid:
        raise ValueError(
            f"recommend_k: candidate_k contains values outside [2, 6]: {invalid}."
        )
    if not candidates_list:
        raise ValueError("recommend_k: candidate_k must be non-empty.")

    table: list[ClusterCandidate] = []
    for k in sorted(candidates_list):
        labels, info = cluster_students(scores_df, k=k, seed=seed)
        if len(labels) < k or len(set(labels.tolist())) < 2:
            # Cannot compute silhouette with <2 unique labels — skip this k
            continue
        matrix = info.get("_imputed_matrix")
        if matrix is None:
            continue
        score = float(silhouette_score(matrix, labels, metric="euclidean"))
        table.append(ClusterCandidate(k=k, silhouette_score=score))

    if not table:
        raise ValueError(
            "recommend_k: no candidate k produced ≥2 unique labels — sample too small."
        )

    # argmax silhouette; tie → smaller k (table is already sorted by k asc, so
    # the first encounter of the max value wins).
    best_k = max(table, key=lambda c: (c.silhouette_score, -c.k)).k
    return best_k, table
