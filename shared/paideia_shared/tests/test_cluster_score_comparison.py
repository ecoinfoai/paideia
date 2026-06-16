"""TDD tests for ClusterRow + ClusterScoreComparison + ClusterPairwise (M5, T008)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas.cluster_score_comparison import (
    ClusterPairwise,
    ClusterRow,
    ClusterScoreComparison,
)
from pydantic import ValidationError

# ClusterRow


def test_cluster_row_valid() -> None:
    row = ClusterRow(
        cluster_id=0,
        cluster_label="고동기/고전략",
        n=12,
        mean=82.5,
        std=8.4,
        ci_low_95=78.0,
        ci_high_95=87.0,
        excluded_reason=None,
    )
    assert row.n == 12


def test_cluster_row_n_zero_must_have_stats_none() -> None:
    """n=0 with mean populated → ValueError."""
    with pytest.raises(ValidationError, match="n=0"):
        ClusterRow(
            cluster_id=2,
            cluster_label="작은 군집",
            n=0,
            mean=70.0,
            std=None,
            ci_low_95=None,
            ci_high_95=None,
            excluded_reason="n < 5 군집 자동 제외",
        )


def test_cluster_row_excluded_reason_kept() -> None:
    row = ClusterRow(
        cluster_id=2,
        cluster_label="작은 군집",
        n=3,
        mean=68.0,
        std=4.2,
        ci_low_95=None,
        ci_high_95=None,
        excluded_reason="n < 5 군집 자동 제외",
    )
    assert row.excluded_reason is not None


def test_cluster_row_overall_id() -> None:
    """cluster_id='overall' is valid (cohort summary row)."""
    row = ClusterRow(
        cluster_id="overall",
        cluster_label="cohort",
        n=160,
        mean=75.0,
        std=12.3,
        ci_low_95=73.0,
        ci_high_95=77.0,
    )
    assert row.cluster_id == "overall"


# ClusterScoreComparison


def test_anova_k3_welch_valid() -> None:
    summary = ClusterScoreComparison(
        k_used=3,
        test_used="Welch_ANOVA",
        levene_p=0.02,
        test_stat=12.4,
        raw_p=0.001,
        eta_squared=0.13,
        omega_squared=0.11,
        posthoc_test="Games_Howell",
    )
    assert summary.test_used == "Welch_ANOVA"


def test_v1_k1_must_be_na() -> None:
    """k=1 with test_used='ANOVA' → ValueError."""
    with pytest.raises(ValidationError, match="V1 k=1"):
        ClusterScoreComparison(
            k_used=1,
            test_used="ANOVA",
            levene_p=None,
            test_stat=None,
            raw_p=None,
            eta_squared=None,
            omega_squared=None,
            posthoc_test="N/A",
        )


def test_v1_k1_with_levene_p_raises() -> None:
    with pytest.raises(ValidationError, match="V1 k=1"):
        ClusterScoreComparison(
            k_used=1,
            test_used="N/A",
            levene_p=0.05,  # must be None
            test_stat=None,
            raw_p=None,
            eta_squared=None,
            omega_squared=None,
            posthoc_test="N/A",
        )


def test_v1_k1_valid() -> None:
    summary = ClusterScoreComparison(
        k_used=1,
        test_used="N/A",
        levene_p=None,
        test_stat=None,
        raw_p=None,
        eta_squared=None,
        omega_squared=None,
        posthoc_test="N/A",
    )
    assert summary.test_used == "N/A"


def test_v2_k2_must_be_welch_t() -> None:
    with pytest.raises(ValidationError, match="V2 k=2"):
        ClusterScoreComparison(
            k_used=2,
            test_used="ANOVA",  # must be Welch_t_test
            levene_p=0.04,
            test_stat=2.5,
            raw_p=0.02,
            eta_squared=0.05,
            omega_squared=0.04,
            posthoc_test="N/A",
        )


def test_v2_k2_posthoc_must_be_na() -> None:
    with pytest.raises(ValidationError, match="V2 k=2"):
        ClusterScoreComparison(
            k_used=2,
            test_used="Welch_t_test",
            levene_p=0.04,
            test_stat=2.5,
            raw_p=0.02,
            eta_squared=0.05,
            omega_squared=0.04,
            posthoc_test="Tukey_HSD",  # must be N/A
        )


def test_v2_k2_valid() -> None:
    summary = ClusterScoreComparison(
        k_used=2,
        test_used="Welch_t_test",
        levene_p=0.04,
        test_stat=2.5,
        raw_p=0.02,
        eta_squared=0.05,
        omega_squared=0.04,
        posthoc_test="N/A",
    )
    assert summary.test_used == "Welch_t_test"


def test_v3_eta_squared_above_one_raises() -> None:
    with pytest.raises(ValidationError, match="V3 eta_squared range"):
        ClusterScoreComparison(
            k_used=3,
            test_used="ANOVA",
            levene_p=0.6,
            test_stat=10.0,
            raw_p=0.001,
            eta_squared=1.5,
            omega_squared=0.1,
            posthoc_test="Tukey_HSD",
        )


# ClusterPairwise


def test_cluster_pairwise_valid() -> None:
    pair = ClusterPairwise(
        cluster_pair=(0, 1),
        mean_diff=8.4,
        raw_p=0.003,
        fdr_q=0.018,
        significant_after_correction=True,
    )
    assert pair.cluster_pair == (0, 1)


def test_cluster_pairwise_ascending_required() -> None:
    """(2, 1) violates lo<hi for determinism."""
    with pytest.raises(ValidationError, match="lo<hi"):
        ClusterPairwise(
            cluster_pair=(2, 1),
            mean_diff=-8.4,
            raw_p=0.003,
            fdr_q=0.018,
            significant_after_correction=True,
        )


def test_cluster_pairwise_self_pair_invalid() -> None:
    """(1, 1) violates lo<hi."""
    with pytest.raises(ValidationError, match="lo<hi"):
        ClusterPairwise(
            cluster_pair=(1, 1),
            mean_diff=0.0,
            raw_p=1.0,
            fdr_q=1.0,
            significant_after_correction=False,
        )
