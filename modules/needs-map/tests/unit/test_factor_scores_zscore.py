"""Unit tests for population z-score (T047, FR-008)."""

from __future__ import annotations

import math

import pandas as pd
import pytest


def test_zscore_basic_shape() -> None:
    from needs_map.factor_scores.zscore import zscore

    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = zscore(values)
    # population std (ddof=0): sqrt(2). Mean=3.
    expected_std = math.sqrt(2)
    assert result.iloc[0] == pytest.approx((1 - 3) / expected_std)
    assert result.iloc[2] == pytest.approx(0.0)
    assert result.iloc[4] == pytest.approx((5 - 3) / expected_std)


def test_zscore_skips_nan() -> None:
    from needs_map.factor_scores.zscore import zscore

    values = pd.Series([1.0, 2.0, float("nan"), 4.0, 5.0])
    result = zscore(values)
    assert pd.isna(result.iloc[2])
    # mean of {1,2,4,5} = 3, population std with ddof=0 = sqrt(2.5)
    expected_std = math.sqrt(((1 - 3) ** 2 + (2 - 3) ** 2 + (4 - 3) ** 2 + (5 - 3) ** 2) / 4)
    assert result.iloc[0] == pytest.approx((1 - 3) / expected_std)


def test_zscore_constant_column_returns_zeros() -> None:
    """Constant column → all zeros (adversary H-2: no ZeroDivisionError, no silent NaN)."""
    from needs_map.factor_scores.zscore import zscore

    values = pd.Series([4.0, 4.0, 4.0, 4.0])
    result = zscore(values)
    assert (result == 0.0).all()


def test_zscore_all_nan_returns_all_nan() -> None:
    from needs_map.factor_scores.zscore import zscore

    values = pd.Series([float("nan")] * 4)
    result = zscore(values)
    assert result.isna().all()


def test_zscore_preserves_index() -> None:
    from needs_map.factor_scores.zscore import zscore

    values = pd.Series([1.0, 2.0, 3.0], index=["A", "B", "C"])
    result = zscore(values)
    assert result.index.tolist() == ["A", "B", "C"]


def test_zscore_population_ddof_zero_matches_manual() -> None:
    from needs_map.factor_scores.zscore import zscore

    values = pd.Series([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    mean = values.mean()
    population_std = math.sqrt(((values - mean) ** 2).sum() / len(values))
    result = zscore(values)
    for original, computed in zip(values, result, strict=True):
        assert computed == pytest.approx((original - mean) / population_std)


def test_zscore_single_value_returns_zero() -> None:
    """Single-value series → constant case → zero. No division by zero."""
    from needs_map.factor_scores.zscore import zscore

    result = zscore(pd.Series([4.0]))
    assert result.iloc[0] == 0.0
