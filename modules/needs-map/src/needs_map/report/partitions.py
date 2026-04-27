"""Partition comparisons for the group report (T098, FR-017 (d)).

Two/three-or-more-group statistics:
  - 2 groups → Welch's t-test (scipy.stats.ttest_ind, equal_var=False)
  - 3+ groups → one-way ANOVA (scipy.stats.f_oneway)

Single-group partitions (e.g. all students in one section) flip
``n_too_small_warning=True`` and skip the test (adversary H-10 mitigation —
never silent skip).
"""

from __future__ import annotations

import pandas as pd
from scipy import stats


def compare_two_groups(a: pd.Series, b: pd.Series) -> dict:
    """Welch's t-test on two non-empty series."""
    a_clean = a.dropna()
    b_clean = b.dropna()
    if len(a_clean) < 2 or len(b_clean) < 2:
        return {
            "t_statistic": None,
            "p_value": None,
            "n_too_small_warning": True,
        }
    t_stat, p_val = stats.ttest_ind(a_clean, b_clean, equal_var=False)
    return {
        "t_statistic": float(t_stat),
        "p_value": float(p_val),
        "n_too_small_warning": False,
    }


def compare_three_or_more_groups(groups: list[pd.Series]) -> dict:
    """One-way ANOVA on 3+ non-empty series."""
    cleaned = [g.dropna() for g in groups]
    cleaned = [g for g in cleaned if len(g) >= 2]
    if len(cleaned) < 3:
        return {
            "f_statistic": None,
            "p_value": None,
            "n_too_small_warning": True,
        }
    f_stat, p_val = stats.f_oneway(*cleaned)
    return {
        "f_statistic": float(f_stat),
        "p_value": float(p_val),
        "n_too_small_warning": False,
    }


def compute_partition_for_axis(
    factor_scores_df: pd.DataFrame, partition_col: str, axis: str
) -> dict:
    """Dispatch t-test (2 groups) or ANOVA (3+ groups) for one axis × partition.

    Args:
        factor_scores_df: must contain ``partition_col`` and ``axis`` columns.
        partition_col: name of the column whose unique values define groups.
        axis: name of the score column to compare across groups.

    Returns:
        ``{group_means, p_value, t_statistic|f_statistic, n_too_small_warning}``.
        Single-group partition → ``n_too_small_warning=True``, ``p_value=None``,
        ``group_means`` populated for whatever groups exist.
    """
    if partition_col not in factor_scores_df.columns:
        return {
            "group_means": {},
            "p_value": None,
            "n_too_small_warning": True,
        }
    if axis not in factor_scores_df.columns:
        return {
            "group_means": {},
            "p_value": None,
            "n_too_small_warning": True,
        }
    grouped = factor_scores_df.dropna(subset=[axis, partition_col]).groupby(
        partition_col, sort=True
    )
    group_means = {str(name): float(g[axis].mean()) for name, g in grouped}
    series_list = [g[axis] for _, g in grouped]

    if len(series_list) < 2:
        return {
            "group_means": group_means,
            "p_value": None,
            "n_too_small_warning": True,
        }
    if len(series_list) == 2:
        result = compare_two_groups(series_list[0], series_list[1])
    else:
        result = compare_three_or_more_groups(series_list)
    result["group_means"] = group_means
    return result
