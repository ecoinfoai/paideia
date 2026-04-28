"""Unit tests for K-means clustering (T066, FR-009)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

_AXES_3 = ("motivation", "study_strategy", "feedback_seeking")


def _make_scores(n: int = 30, n_axes: int = 3, seed: int = 7) -> pd.DataFrame:
    """3-axis substantive scores for n students; simple Gaussian blobs.

    Axis names use the v0.1.1 8-axis vocabulary subset
    (motivation / study_strategy / feedback_seeking) so the kmeans
    helper's ``_present_axis_columns`` recognises them.
    """
    rng = np.random.default_rng(seed)
    centers = rng.uniform(-2, 2, size=(3, n_axes))
    rows: list[dict] = []
    for i in range(n):
        center = centers[i % 3]
        values = center + rng.normal(0, 0.5, size=n_axes)
        row = {"student_id": f"20261940{i:02d}"}
        for j, axis in enumerate(_AXES_3):
            row[axis] = float(values[j])
        rows.append(row)
    return pd.DataFrame(rows)


def test_cluster_students_returns_labels_and_centroids() -> None:
    from needs_map.clustering.kmeans import cluster_students

    df = _make_scores(n=30)
    labels, info = cluster_students(df, k=3, seed=42)
    assert labels.shape == (30,)
    assert set(labels.tolist()) <= {0, 1, 2}
    assert "centroids" in info
    assert info["centroids"].shape == (3, 3)


def test_cluster_students_deterministic_across_runs() -> None:
    """Same input + same seed → identical labels."""
    from needs_map.clustering.kmeans import cluster_students

    df = _make_scores(n=30)
    a, _ = cluster_students(df, k=3, seed=42)
    b, _ = cluster_students(df, k=3, seed=42)
    assert (a == b).all()


def test_cluster_students_excludes_all_nan_rows() -> None:
    """A student with all-NaN axis scores must NOT appear in the labelled set."""
    from needs_map.clustering.kmeans import cluster_students

    df = _make_scores(n=10)
    df = pd.concat(
        [
            df,
            pd.DataFrame(
                [
                    dict(
                        {"student_id": "9999999999"},
                        **{axis: float("nan") for axis in _AXES_3},
                    )
                ]
            ),
        ],
        ignore_index=True,
    )
    labels, info = cluster_students(df, k=2, seed=42)
    assert labels.shape == (10,)  # all-NaN row dropped
    assert "excluded_student_ids" in info
    assert info["excluded_student_ids"] == ["9999999999"]


def test_cluster_students_sort_by_student_id_before_fit() -> None:
    """Result must be invariant under input row permutation (axis-2 of determinism 4)."""
    from needs_map.clustering.kmeans import cluster_students

    df = _make_scores(n=20)
    shuffled = df.sample(frac=1.0, random_state=99).reset_index(drop=True)
    a, _ = cluster_students(df, k=3, seed=42)
    b, _ = cluster_students(shuffled, k=3, seed=42)
    # Sorted-by-student_id labels are equal up to ordering of the result vector
    # (the function should sort internally and return labels in that sorted order)
    assert (a == b).all()


def test_cluster_students_k_must_be_positive() -> None:
    from needs_map.clustering.kmeans import cluster_students

    df = _make_scores(n=10)
    with pytest.raises(ValueError, match="k"):
        cluster_students(df, k=0, seed=42)


def test_cluster_students_k_one_returns_single_cluster() -> None:
    """k=1 fallback path: every (substantive) student gets cluster_id=0."""
    from needs_map.clustering.kmeans import cluster_students

    df = _make_scores(n=12)
    labels, _info = cluster_students(df, k=1, seed=42)
    assert (labels == 0).all()


def test_cluster_students_seed_required_no_default() -> None:
    """Function signature must NOT accept a default seed (qa Stage-2 candidate 2)."""
    import inspect

    from needs_map.clustering.kmeans import cluster_students

    sig = inspect.signature(cluster_students)
    seed_param = sig.parameters["seed"]
    assert seed_param.default is inspect.Parameter.empty, (
        "cluster_students(seed=...) must NOT have a default — caller (pipeline.py "
        "T074) must pass NeedsMapArgs.seed explicitly."
    )
