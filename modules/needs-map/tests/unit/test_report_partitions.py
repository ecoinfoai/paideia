"""Unit tests for partition comparisons (T090, FR-017 (d))."""

from __future__ import annotations

import math

import pandas as pd
import pytest


def test_two_group_partition_runs_t_test() -> None:
    from needs_map.report.partitions import compare_two_groups

    a = pd.Series([5.0, 6.0, 7.0])
    b = pd.Series([3.0, 4.0, 5.0])
    result = compare_two_groups(a, b)
    assert "t_statistic" in result
    assert "p_value" in result
    assert math.isfinite(result["t_statistic"])
    assert 0.0 <= result["p_value"] <= 1.0


def test_three_group_partition_runs_anova() -> None:
    from needs_map.report.partitions import compare_three_or_more_groups

    groups = [
        pd.Series([5.0, 6.0, 7.0]),
        pd.Series([3.0, 4.0, 5.0]),
        pd.Series([2.0, 3.0, 4.0]),
    ]
    result = compare_three_or_more_groups(groups)
    assert "f_statistic" in result
    assert "p_value" in result
    assert 0.0 <= result["p_value"] <= 1.0


def test_single_group_partition_records_warning() -> None:
    """A partition with only 1 group → n_too_small_warning, no test computed (H-10)."""
    from needs_map.report.partitions import compute_partition_for_axis

    factor_scores = pd.DataFrame(
        {
            "student_id": ["A", "B", "C"],
            "section": ["A", "A", "A"],  # all in one section
            "motivation": [4.0, 5.0, 6.0],
        }
    )
    result = compute_partition_for_axis(factor_scores, partition_col="section", axis="motivation")
    assert result["n_too_small_warning"] is True
    assert result["p_value"] is None


def test_two_group_partition_via_dispatcher() -> None:
    from needs_map.report.partitions import compute_partition_for_axis

    factor_scores = pd.DataFrame(
        {
            "student_id": ["A", "B", "C", "D"],
            "section": ["A", "A", "B", "B"],
            "motivation": [4.0, 5.0, 6.0, 7.0],
        }
    )
    result = compute_partition_for_axis(factor_scores, partition_col="section", axis="motivation")
    assert "p_value" in result
    assert result["n_too_small_warning"] is False
    assert "group_means" in result
    assert set(result["group_means"].keys()) == {"A", "B"}


def test_partition_skips_nan_axis_rows() -> None:
    from needs_map.report.partitions import compute_partition_for_axis

    factor_scores = pd.DataFrame(
        {
            "student_id": ["A", "B", "C", "D"],
            "section": ["A", "A", "B", "B"],
            "motivation": [4.0, float("nan"), 6.0, 7.0],
        }
    )
    result = compute_partition_for_axis(factor_scores, partition_col="section", axis="motivation")
    assert result["group_means"]["A"] == pytest.approx(4.0)
