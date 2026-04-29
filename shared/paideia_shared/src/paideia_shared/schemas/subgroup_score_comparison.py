"""SubgroupScoreComparison (M6 in data-model.md, T009).

xlsx `부분군비교` 시트 — 4 메타 (section, prior_biology, occupation, education) ×
카테고리 행 + 메타별 검정 헤더. 2 모델 합본:
- ``SubgroupRow`` — 카테고리별 1 행 (meta_kind, meta_value, n, mean, std)
- ``SubgroupScoreComparison`` — 검정 헤더 1 행 per meta
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


SubgroupMetaKind = Literal["section", "prior_biology", "occupation", "education"]


class SubgroupRow(BaseModel):
    """One category row in xlsx `부분군비교` Sub-block 1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    meta_kind: SubgroupMetaKind
    meta_value: str
    n: int = Field(ge=0)
    mean: float | None = None
    std: float | None = None
    excluded_reason: str | None = None


class SubgroupScoreComparison(BaseModel):
    """Test header row per subgroup meta (M6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    meta_kind: SubgroupMetaKind
    test_used: Literal["t_test_welch", "ANOVA", "Welch_ANOVA", "N/A"]
    levene_p: float | None = None
    test_stat: float | None = None
    raw_p: float | None = None
    fdr_q: float | None = None
    effect_size_kind: Literal["cohen_d", "eta_squared"]
    effect_size_value: float | None = None
    n_categories_compared: int = Field(ge=0)

    @model_validator(mode="after")
    def _v1_two_cat_implies_t_welch_with_cohen_d(self) -> Self:
        """V1: n_categories_compared=2 ⇒ test_used='t_test_welch' AND effect_size_kind='cohen_d'."""
        if self.n_categories_compared == 2:
            if self.test_used != "t_test_welch":
                raise ValueError(
                    f"V1 2-cat: test_used must be 't_test_welch', got {self.test_used}"
                )
            if self.effect_size_kind != "cohen_d":
                raise ValueError(
                    f"V1 2-cat: effect_size_kind must be 'cohen_d', got {self.effect_size_kind}"
                )
        return self

    @model_validator(mode="after")
    def _v2_three_plus_cat_implies_anova_with_eta(self) -> Self:
        """V2: n_categories_compared >= 3 ⇒ test_used in {ANOVA, Welch_ANOVA} AND effect_size_kind='eta_squared'."""
        if self.n_categories_compared >= 3:
            if self.test_used not in ("ANOVA", "Welch_ANOVA"):
                raise ValueError(
                    f"V2 3+cat: test_used must be 'ANOVA' or 'Welch_ANOVA', got {self.test_used}"
                )
            if self.effect_size_kind != "eta_squared":
                raise ValueError(
                    f"V2 3+cat: effect_size_kind must be 'eta_squared', got {self.effect_size_kind}"
                )
        return self

    @model_validator(mode="after")
    def _v3_meta_undefined_implies_na(self) -> Self:
        """V3: n_categories_compared=0 ⇒ test_used='N/A' (메타 미정의 폴백, R10).

        Caller 가 별도 SubgroupRow 에 meta_value='(메타 미정의)' + excluded_reason
        을 채워야 함. 본 헤더 모델은 test_used='N/A' 만 강제.
        """
        if self.n_categories_compared == 0 and self.test_used != "N/A":
            raise ValueError(
                f"V3 메타 미정의: test_used must be 'N/A' when n_categories_compared=0, "
                f"got {self.test_used}"
            )
        return self


__all__ = ["SubgroupMetaKind", "SubgroupRow", "SubgroupScoreComparison"]
