"""TDD tests for SubgroupRow + SubgroupScoreComparison (M6, T009)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paideia_shared.schemas.subgroup_score_comparison import (
    SubgroupRow,
    SubgroupScoreComparison,
)


# SubgroupRow


def test_subgroup_row_valid() -> None:
    row = SubgroupRow(
        meta_kind="section",
        meta_value="A",
        n=46,
        mean=78.5,
        std=10.2,
        excluded_reason=None,
    )
    assert row.n == 46


def test_subgroup_row_excluded_small() -> None:
    row = SubgroupRow(
        meta_kind="occupation",
        meta_value="군인",
        n=2,
        mean=None,
        std=None,
        excluded_reason="n < 10 카테고리 자동 제외",
    )
    assert row.excluded_reason is not None


def test_subgroup_row_meta_undefined_fallback() -> None:
    row = SubgroupRow(
        meta_kind="education",
        meta_value="(메타 미정의)",
        n=0,
        mean=None,
        std=None,
        excluded_reason="mapping YAML 키 부재",
    )
    assert row.meta_value == "(메타 미정의)"


def test_subgroup_row_invalid_meta_kind() -> None:
    with pytest.raises(ValidationError):
        SubgroupRow(
            meta_kind="gender",  # type: ignore[arg-type]
            meta_value="M",
            n=10,
            mean=70.0,
            std=5.0,
        )


# SubgroupScoreComparison — V1 2-카테고리


def test_v1_two_cat_t_welch_cohen_d_valid() -> None:
    summary = SubgroupScoreComparison(
        meta_kind="prior_biology",
        test_used="t_test_welch",
        levene_p=0.4,
        test_stat=2.4,
        raw_p=0.018,
        fdr_q=0.04,
        effect_size_kind="cohen_d",
        effect_size_value=0.42,
        n_categories_compared=2,
    )
    assert summary.test_used == "t_test_welch"


def test_v1_two_cat_with_anova_raises() -> None:
    with pytest.raises(ValidationError, match="V1 2-cat"):
        SubgroupScoreComparison(
            meta_kind="prior_biology",
            test_used="ANOVA",  # must be t_test_welch
            levene_p=0.4,
            test_stat=2.4,
            raw_p=0.018,
            fdr_q=0.04,
            effect_size_kind="cohen_d",
            effect_size_value=0.42,
            n_categories_compared=2,
        )


def test_v1_two_cat_with_eta_squared_raises() -> None:
    with pytest.raises(ValidationError, match="V1 2-cat"):
        SubgroupScoreComparison(
            meta_kind="prior_biology",
            test_used="t_test_welch",
            levene_p=0.4,
            test_stat=2.4,
            raw_p=0.018,
            fdr_q=0.04,
            effect_size_kind="eta_squared",  # must be cohen_d
            effect_size_value=0.10,
            n_categories_compared=2,
        )


# V2 3+ 카테고리


def test_v2_three_cat_anova_eta_valid() -> None:
    summary = SubgroupScoreComparison(
        meta_kind="section",
        test_used="ANOVA",
        levene_p=0.20,
        test_stat=4.1,
        raw_p=0.008,
        fdr_q=0.024,
        effect_size_kind="eta_squared",
        effect_size_value=0.067,
        n_categories_compared=4,
    )
    assert summary.test_used == "ANOVA"


def test_v2_three_cat_welch_anova_valid() -> None:
    summary = SubgroupScoreComparison(
        meta_kind="occupation",
        test_used="Welch_ANOVA",
        levene_p=0.02,
        test_stat=5.2,
        raw_p=0.003,
        fdr_q=0.012,
        effect_size_kind="eta_squared",
        effect_size_value=0.085,
        n_categories_compared=3,
    )
    assert summary.test_used == "Welch_ANOVA"


def test_v2_three_cat_with_t_welch_raises() -> None:
    with pytest.raises(ValidationError, match="V2 3"):
        SubgroupScoreComparison(
            meta_kind="section",
            test_used="t_test_welch",  # must be ANOVA or Welch_ANOVA
            levene_p=0.20,
            test_stat=4.1,
            raw_p=0.008,
            fdr_q=0.024,
            effect_size_kind="eta_squared",
            effect_size_value=0.067,
            n_categories_compared=4,
        )


def test_v2_three_cat_with_cohen_d_raises() -> None:
    with pytest.raises(ValidationError, match="V2 3"):
        SubgroupScoreComparison(
            meta_kind="section",
            test_used="ANOVA",
            levene_p=0.20,
            test_stat=4.1,
            raw_p=0.008,
            fdr_q=0.024,
            effect_size_kind="cohen_d",  # must be eta_squared
            effect_size_value=0.42,
            n_categories_compared=4,
        )


# V3 메타 미정의


def test_v3_meta_undefined_na_valid() -> None:
    summary = SubgroupScoreComparison(
        meta_kind="education",
        test_used="N/A",
        levene_p=None,
        test_stat=None,
        raw_p=None,
        fdr_q=None,
        effect_size_kind="cohen_d",  # placeholder; effect_size_value None
        effect_size_value=None,
        n_categories_compared=0,
    )
    assert summary.test_used == "N/A"


def test_v3_meta_undefined_with_anova_raises() -> None:
    with pytest.raises(ValidationError, match="V3 메타 미정의"):
        SubgroupScoreComparison(
            meta_kind="education",
            test_used="ANOVA",  # must be N/A when 0 categories
            levene_p=None,
            test_stat=None,
            raw_p=None,
            fdr_q=None,
            effect_size_kind="eta_squared",
            effect_size_value=None,
            n_categories_compared=0,
        )
