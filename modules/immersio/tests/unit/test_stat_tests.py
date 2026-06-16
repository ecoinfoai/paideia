"""Unit tests for immersio.analysis.stat_tests (T022).

Spec 004 research §R-02 — 통계 검정 헬퍼 4종:
- levene_then_anova: Levene → ANOVA / Welch ANOVA 자동 폴백
- welch_anova_manual: 수식 직접 구현
- welch_t_test: scipy ttest_ind(equal_var=False) 래퍼
- point_biserial: scipy.stats.pointbiserialr 래퍼

각 헬퍼는 (p_value, test_kind) 또는 float 반환.
"""

from __future__ import annotations

import numpy as np
import pytest
from immersio.analysis.stat_tests import (
    levene_then_anova,
    point_biserial,
    welch_anova_manual,
    welch_t_test,
)
from scipy import stats

# =====================================================================
# levene_then_anova
# =====================================================================


def test_levene_then_anova_homogeneous_variance_picks_anova() -> None:
    """등분산 → ANOVA 선택 (Levene p ≥ 0.05)."""
    rng = np.random.default_rng(42)
    g1 = rng.normal(loc=10.0, scale=2.0, size=50)
    g2 = rng.normal(loc=11.0, scale=2.0, size=50)
    g3 = rng.normal(loc=10.5, scale=2.0, size=50)
    p_value, test_kind = levene_then_anova([g1, g2, g3])
    assert test_kind == "ANOVA"
    expected_p = stats.f_oneway(g1, g2, g3).pvalue
    assert p_value == pytest.approx(expected_p, rel=1e-9)


def test_levene_then_anova_heterogeneous_variance_picks_welch() -> None:
    """이분산 → Welch ANOVA 선택 (Levene p < 0.05)."""
    rng = np.random.default_rng(7)
    g1 = rng.normal(loc=10.0, scale=1.0, size=50)
    g2 = rng.normal(loc=10.0, scale=10.0, size=50)
    g3 = rng.normal(loc=10.0, scale=20.0, size=50)
    p_value, test_kind = levene_then_anova([g1, g2, g3])
    assert test_kind == "Welch ANOVA"
    assert 0.0 <= p_value <= 1.0


def test_levene_then_anova_rejects_lt_two_groups() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match=r"at least 2 groups"):
        levene_then_anova([rng.normal(size=20)])


def test_levene_then_anova_rejects_empty_group() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match=r"empty"):
        levene_then_anova([rng.normal(size=20), np.array([])])


# =====================================================================
# welch_anova_manual
# =====================================================================


def test_welch_anova_manual_returns_p_value_in_unit_interval() -> None:
    rng = np.random.default_rng(13)
    g1 = rng.normal(loc=10, scale=1, size=40)
    g2 = rng.normal(loc=12, scale=3, size=30)
    g3 = rng.normal(loc=11, scale=5, size=25)
    p = welch_anova_manual([g1, g2, g3])
    assert 0.0 <= p <= 1.0


def test_welch_anova_manual_no_difference_high_p() -> None:
    """동일 분포 그룹 → p 값이 큼 (귀무가설 기각 어려움)."""
    rng = np.random.default_rng(99)
    g1 = rng.normal(loc=10, scale=2, size=80)
    g2 = rng.normal(loc=10, scale=2, size=80)
    g3 = rng.normal(loc=10, scale=2, size=80)
    p = welch_anova_manual([g1, g2, g3])
    assert p > 0.05


def test_welch_anova_manual_strong_difference_low_p() -> None:
    """평균이 크게 다른 그룹 → p 값 작음."""
    rng = np.random.default_rng(123)
    g1 = rng.normal(loc=0, scale=1, size=60)
    g2 = rng.normal(loc=5, scale=1, size=60)
    g3 = rng.normal(loc=10, scale=1, size=60)
    p = welch_anova_manual([g1, g2, g3])
    assert p < 0.001


# =====================================================================
# welch_t_test
# =====================================================================


def test_welch_t_test_matches_scipy() -> None:
    rng = np.random.default_rng(2026)
    g1 = rng.normal(loc=10, scale=2, size=40)
    g2 = rng.normal(loc=12, scale=4, size=35)
    out = welch_t_test(g1, g2)
    expected = stats.ttest_ind(g1, g2, equal_var=False).pvalue
    assert out == pytest.approx(expected, rel=1e-9)


def test_welch_t_test_rejects_empty_group() -> None:
    with pytest.raises(ValueError, match="empty"):
        welch_t_test(np.array([1.0, 2.0]), np.array([]))


# =====================================================================
# point_biserial
# =====================================================================


def test_point_biserial_perfect_separation() -> None:
    """완벽한 분리 (binary 0 그룹 모두 < binary 1 그룹) → 양의 강한 상관.

    Note: point-biserial r 은 분리도가 완벽해도 ±1 에 도달하지 않는다.
    binary 분포의 p, q 가 sd 비율에 들어가기 때문 (Crocker & Algina 1986).
    fixture: [0,0,0,0,1,1,1,1] × [1..8] → 이론 r ≈ 0.8729.
    """
    binary = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    continuous = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    r = point_biserial(binary, continuous)
    assert r is not None
    assert r > 0.8
    expected = stats.pointbiserialr(binary, continuous).statistic
    assert r == pytest.approx(expected, rel=1e-9)


def test_point_biserial_negative_correlation() -> None:
    binary = np.array([1, 1, 0, 0])
    continuous = np.array([1.0, 2.0, 3.0, 4.0])
    r = point_biserial(binary, continuous)
    assert r < 0


def test_point_biserial_matches_scipy() -> None:
    rng = np.random.default_rng(31)
    binary = rng.integers(low=0, high=2, size=200)
    continuous = rng.normal(size=200) + binary * 1.5
    out = point_biserial(binary, continuous)
    expected = stats.pointbiserialr(binary, continuous).statistic
    assert out == pytest.approx(expected, rel=1e-9)


def test_point_biserial_rejects_non_binary() -> None:
    with pytest.raises(ValueError, match=r"binary"):
        point_biserial(np.array([0, 1, 2]), np.array([1.0, 2.0, 3.0]))


def test_point_biserial_rejects_constant_binary_returns_none() -> None:
    """All-0 또는 All-1 → 표준편차 0 → None 반환 (NaN 처리)."""
    out = point_biserial(np.array([0, 0, 0, 0]), np.array([1.0, 2.0, 3.0, 4.0]))
    assert out is None
