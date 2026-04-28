"""Statistical test helpers for immersio Phase 1+2 (research §R-02).

Four helpers wrap or implement the scipy primitives needed for:
- 분반·메타데이터별 평균 차이 검정 (3+ groups, Levene → ANOVA / Welch ANOVA fallback)
- 두 그룹 평균 차이 (Welch t-test)
- 점-이연 상관 (변별력 보조)

All helpers fail-fast on empty / malformed inputs (Constitution V).
Welch ANOVA is implemented manually because scipy 1.11 doesn't expose it.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from scipy import stats

LeveneAnovaTestKind = Literal["ANOVA", "Welch ANOVA"]

LEVENE_HOMOGENEITY_ALPHA: float = 0.05
"""Levene p-value threshold below which we treat variances as heterogeneous."""


def _validate_groups(groups: list[np.ndarray], min_groups: int) -> None:
    if len(groups) < min_groups:
        raise ValueError(
            f"levene_then_anova requires at least {min_groups} groups, got {len(groups)}"
        )
    for idx, g in enumerate(groups):
        if g.size == 0:
            raise ValueError(f"levene_then_anova: group #{idx} is empty")


def levene_then_anova(
    groups: list[np.ndarray],
) -> tuple[float, LeveneAnovaTestKind]:
    """Run Levene's test, then dispatch to ANOVA or Welch ANOVA.

    Args:
        groups: list of 1D arrays (per-group score vectors). Must have ≥ 2
            non-empty groups.

    Returns:
        (p_value, test_kind) where ``test_kind`` is ``"ANOVA"`` if Levene's
        test fails to reject homogeneity (p ≥ 0.05) and ``"Welch ANOVA"``
        otherwise.

    Raises:
        ValueError: When fewer than 2 groups, or any group is empty.
    """
    _validate_groups(groups, min_groups=2)

    levene_p = stats.levene(*groups, center="median").pvalue
    if levene_p >= LEVENE_HOMOGENEITY_ALPHA:
        anova_p = float(stats.f_oneway(*groups).pvalue)
        return anova_p, "ANOVA"
    welch_p = welch_anova_manual(groups)
    return welch_p, "Welch ANOVA"


def welch_anova_manual(groups: list[np.ndarray]) -> float:
    """Welch ANOVA — heteroscedastic one-way ANOVA p-value.

    Implements the Welch–Satterthwaite formula directly because scipy 1.11
    does not provide a one-call helper:

        F = (Σ wᵢ (x̄ᵢ − x̃)² / (k−1)) /
            (1 + 2(k−2)/(k²−1) · Σ ((1 − wᵢ/Σwⱼ)² / (nᵢ − 1)))

    where wᵢ = nᵢ / sᵢ², x̃ = Σ wᵢ x̄ᵢ / Σ wᵢ, and degrees of freedom
    df₂ = (k² − 1) / (3 · Σ ((1 − wᵢ/Σwⱼ)² / (nᵢ − 1))).

    Reference: Welch, B. L. (1951). "On the comparison of several mean
    values: an alternative approach". Biometrika 38, 330-336.

    Args:
        groups: list of 1D arrays. Must have ≥ 2 non-empty groups, each of
            size ≥ 2 (variance requires nᵢ ≥ 2).

    Returns:
        F-distribution upper-tail p-value in [0.0, 1.0].

    Raises:
        ValueError: When fewer than 2 groups, any group empty, or any
            group has nᵢ < 2 (variance undefined).
    """
    _validate_groups(groups, min_groups=2)
    for idx, g in enumerate(groups):
        if g.size < 2:
            raise ValueError(
                f"welch_anova_manual: group #{idx} has size {g.size} < 2 (variance undefined)"
            )

    k = len(groups)
    n = np.array([g.size for g in groups], dtype=float)
    means = np.array([float(np.mean(g)) for g in groups])
    variances = np.array([float(np.var(g, ddof=1)) for g in groups])

    weights = n / variances
    weight_sum = float(np.sum(weights))
    grand_mean = float(np.sum(weights * means) / weight_sum)

    numerator = float(np.sum(weights * (means - grand_mean) ** 2)) / (k - 1)
    correction_term = float(
        np.sum(((1.0 - weights / weight_sum) ** 2) / (n - 1))
    )
    denominator = 1.0 + (2.0 * (k - 2) / (k**2 - 1)) * correction_term
    f_statistic = numerator / denominator

    df1 = k - 1
    df2 = (k**2 - 1) / (3.0 * correction_term)
    p_value = float(stats.f.sf(f_statistic, df1, df2))
    return p_value


def welch_t_test(g1: np.ndarray, g2: np.ndarray) -> float:
    """Welch's t-test p-value (two-sided, unequal variances).

    Args:
        g1: first group's 1D array (size ≥ 1).
        g2: second group's 1D array (size ≥ 1).

    Returns:
        Two-sided p-value in [0.0, 1.0].

    Raises:
        ValueError: When either group is empty.
    """
    if g1.size == 0 or g2.size == 0:
        raise ValueError("welch_t_test: one of the groups is empty")
    return float(stats.ttest_ind(g1, g2, equal_var=False).pvalue)


def point_biserial(binary: np.ndarray, continuous: np.ndarray) -> float | None:
    """Point-biserial correlation between a 0/1 indicator and a continuous score.

    Args:
        binary: 1D array of 0/1 values (e.g. item correctness).
        continuous: 1D array of same length (e.g. total score).

    Returns:
        Correlation coefficient r in [-1.0, 1.0], or ``None`` when the
        binary vector is constant (all-0 or all-1; standard deviation 0
        renders correlation undefined).

    Raises:
        ValueError: When ``binary`` contains values other than 0/1, or
            arrays are empty / different length.
    """
    if binary.size == 0:
        raise ValueError("point_biserial: binary array is empty")
    if binary.size != continuous.size:
        raise ValueError(
            f"point_biserial: length mismatch ({binary.size} vs {continuous.size})"
        )
    unique_binary = set(np.unique(binary).tolist())
    if not unique_binary.issubset({0, 1}):
        raise ValueError(f"point_biserial: binary array must be 0/1, found {unique_binary}")
    if len(unique_binary) == 1:
        return None  # constant binary → undefined correlation

    r = float(stats.pointbiserialr(binary, continuous).statistic)
    if np.isnan(r):
        return None
    return r
