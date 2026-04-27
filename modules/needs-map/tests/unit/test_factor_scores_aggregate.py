"""Unit tests for axis aggregation (T046, FR-006)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_aggregate_mean_over_likert_items() -> None:
    from needs_map.factor_scores.aggregate import aggregate_axis

    # 3 likert items per student × 4 students
    df = pd.DataFrame(
        {
            "student_id": ["A", "B", "C", "D"] * 3,
            "axis": ["motivation"] * 12,
            "axis_kind": ["likert"] * 12,
            "value_int": [4, 3, 5, 2, 5, 4, 4, 3, 6, 5, 5, 2],
            "source_column": ["Q1"] * 4 + ["Q2"] * 4 + ["Q3"] * 4,
        }
    )
    result = aggregate_axis(df, axis_columns=["Q1", "Q2", "Q3"], kind="mean")
    assert sorted(result.index) == ["A", "B", "C", "D"]
    # Student A: Q1=4, Q2=5, Q3=6 → mean 5.0
    assert result.loc["A"] == pytest.approx((4 + 5 + 6) / 3)
    # Student D: Q1=2, Q2=3, Q3=2 → mean 7/3
    assert result.loc["D"] == pytest.approx((2 + 3 + 2) / 3)


def test_aggregate_sum_over_multiselect_onehot() -> None:
    from needs_map.factor_scores.aggregate import aggregate_axis

    df = pd.DataFrame(
        {
            "student_id": ["A", "A", "B", "B", "C", "C"],
            "axis": ["prior_knowledge"] * 6,
            "axis_kind": ["multiselect_onehot"] * 6,
            "value_bool": [True, False, True, True, False, False],
            "option_key": ["bio_high", "bio_none", "bio_high", "bio_none", "bio_high", "bio_none"],
            "source_column": ["Q03_prior_knowledge"] * 6,
        }
    )
    result = aggregate_axis(df, axis_columns=["Q03_prior_knowledge"], kind="sum")
    # Counts of True per student
    assert result.loc["A"] == 1
    assert result.loc["B"] == 2
    assert result.loc["C"] == 0


def test_aggregate_mean_propagates_nan_when_item_missing() -> None:
    """drop policy: a student missing an item should produce NaN at the aggregate stage."""
    from needs_map.factor_scores.aggregate import aggregate_axis

    df = pd.DataFrame(
        {
            "student_id": ["A", "A", "B", "B", "B"],
            "axis": ["motivation"] * 5,
            "axis_kind": ["likert"] * 5,
            "value_int": [4, np.nan, 5, 4, 6],
            "source_column": ["Q1", "Q2", "Q1", "Q2", "Q3"],
        }
    )
    # B has Q1, Q2, Q3; A has Q1 only — Q2 NaN, Q3 missing entirely
    result = aggregate_axis(df, axis_columns=["Q1", "Q2", "Q3"], kind="mean")
    # student A: NaN propagates (drop policy means missing handled at next stage)
    assert pd.isna(result.loc["A"])
    # student B: 5 + 4 + 6 = 15 / 3 = 5.0
    assert result.loc["B"] == pytest.approx(5.0)


def test_aggregate_rejects_unknown_kind() -> None:
    from needs_map.factor_scores.aggregate import aggregate_axis

    df = pd.DataFrame(
        {"student_id": ["A"], "axis": ["motivation"], "value_int": [4], "source_column": ["Q1"]}
    )
    with pytest.raises(ValueError, match="kind"):
        aggregate_axis(df, axis_columns=["Q1"], kind="median")  # type: ignore[arg-type]


def test_apply_missing_policy_drop_preserves_nan_and_flags() -> None:
    from needs_map.factor_scores.missing import apply_missing_policy

    values = pd.Series([4.0, float("nan"), 5.0, float("nan")], index=["A", "B", "C", "D"])
    resolved, missing = apply_missing_policy(values, policy="drop")
    assert pd.isna(resolved.loc["B"])
    assert pd.isna(resolved.loc["D"])
    assert resolved.loc["A"] == 4.0
    assert missing.loc["A"] is False or missing.loc["A"] == False  # noqa: E712
    assert missing.loc["B"] is True or missing.loc["B"] == True  # noqa: E712


def test_apply_missing_policy_mean_impute_fills_and_flags_false() -> None:
    """mean_impute fills NaN with column mean AND records missing=False (M4 V2 invariant)."""
    from needs_map.factor_scores.missing import apply_missing_policy

    values = pd.Series([4.0, float("nan"), 6.0, float("nan")], index=["A", "B", "C", "D"])
    resolved, missing = apply_missing_policy(values, policy="mean_impute")
    expected_mean = (4.0 + 6.0) / 2
    assert resolved.loc["B"] == pytest.approx(expected_mean)
    assert resolved.loc["D"] == pytest.approx(expected_mean)
    # M4 V2 invariant: imputed values record missing=False
    assert missing.loc["B"] is False or missing.loc["B"] == False  # noqa: E712
    assert missing.loc["D"] is False or missing.loc["D"] == False  # noqa: E712


def test_apply_missing_policy_rejects_unknown_policy() -> None:
    from needs_map.factor_scores.missing import apply_missing_policy

    values = pd.Series([4.0, float("nan")])
    with pytest.raises(ValueError, match="policy"):
        apply_missing_policy(values, policy="median")  # type: ignore[arg-type]


def test_apply_missing_policy_all_nan_drop() -> None:
    """All-missing axis → drop preserves all NaN + all flags True."""
    from needs_map.factor_scores.missing import apply_missing_policy

    values = pd.Series([float("nan")] * 4, index=list("ABCD"))
    resolved, missing = apply_missing_policy(values, policy="drop")
    assert resolved.isna().all()
    assert all(missing.tolist())


def test_apply_missing_policy_all_nan_mean_impute_keeps_nan() -> None:
    """All-missing under mean_impute: no mean to impute → values stay NaN, missing=True."""
    from needs_map.factor_scores.missing import apply_missing_policy

    values = pd.Series([float("nan")] * 4, index=list("ABCD"))
    resolved, missing = apply_missing_policy(values, policy="mean_impute")
    # No data to compute mean from — fallback: leave NaN, flag True (M4 V2 satisfied
    # because score=None ⇒ missing=True)
    assert resolved.isna().all()
    assert all(missing.tolist())
