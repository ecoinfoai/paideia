"""Unit tests for silhouette-based k recommendation (T067, FR-010, research D3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

_AXES_3 = ("motivation", "study_strategy", "feedback_seeking")


def _make_blobs(
    n_per_cluster: int = 12, n_clusters: int = 3, n_axes: int = 3, seed: int = 7
) -> pd.DataFrame:
    """3-axis blobs using v0.1.1 vocabulary (motivation/study_strategy/feedback_seeking)."""
    rng = np.random.default_rng(seed)
    centers = rng.uniform(-3, 3, size=(n_clusters, n_axes))
    rows: list[dict] = []
    sid = 0
    for cluster_idx in range(n_clusters):
        center = centers[cluster_idx]
        for _ in range(n_per_cluster):
            values = center + rng.normal(0, 0.3, size=n_axes)
            row = {"student_id": f"20261940{sid:02d}"}
            for j, axis in enumerate(_AXES_3):
                row[axis] = float(values[j])
            rows.append(row)
            sid += 1
    return pd.DataFrame(rows)


def test_recommend_k_returns_chosen_k_and_table() -> None:
    from needs_map.clustering.silhouette import recommend_k

    df = _make_blobs(n_per_cluster=12, n_clusters=3)
    chosen, table = recommend_k(df, candidate_k=range(2, 7), seed=42)
    assert isinstance(chosen, int)
    assert 2 <= chosen <= 6
    assert len(table) >= 1
    assert all(2 <= cand.k <= 6 for cand in table)


def test_recommend_k_argmax_selects_strongest_silhouette() -> None:
    """For 3 well-separated blobs, recommend_k should pick k=3."""
    from needs_map.clustering.silhouette import recommend_k

    df = _make_blobs(n_per_cluster=20, n_clusters=3)
    chosen, table = recommend_k(df, candidate_k=range(2, 7), seed=42)
    assert chosen == 3
    # Highest silhouette should be at k=3
    sorted_table = sorted(table, key=lambda c: c.silhouette_score, reverse=True)
    assert sorted_table[0].k == 3


def test_recommend_k_tie_breaks_to_smaller_k() -> None:
    """When two ks have equal silhouette, the smaller k wins (research D3)."""
    from needs_map.clustering.silhouette import recommend_k

    df = _make_blobs(n_per_cluster=8, n_clusters=2)
    chosen, _table = recommend_k(df, candidate_k=range(2, 7), seed=42)
    # 2-blob input → k=2 should at least tie or beat k=3..6
    assert chosen == 2


def test_recommend_k_rejects_invalid_candidate_k() -> None:
    from needs_map.clustering.silhouette import recommend_k

    df = _make_blobs()
    with pytest.raises(ValueError, match="candidate"):
        recommend_k(df, candidate_k=range(1, 3), seed=42)  # k=1 invalid as candidate


def test_recommend_k_seed_required_no_default() -> None:
    """qa Stage-2 candidate 2: seed must be required, no default."""
    import inspect

    from needs_map.clustering.silhouette import recommend_k

    sig = inspect.signature(recommend_k)
    assert sig.parameters["seed"].default is inspect.Parameter.empty
