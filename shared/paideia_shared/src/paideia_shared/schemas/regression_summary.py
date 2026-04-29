"""RegressionCoefficient (M3) + RegressionFitSummary (M4) — single file (T007).

xlsx `회귀결과` 시트의 헤더 블록 (RegressionFitSummary, 1 row) + 8 axis 계수
행 (RegressionCoefficient, 8 rows). statsmodels OLS 결과 추출.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import StandardAxisKey


class RegressionCoefficient(BaseModel):
    """One regression coefficient row (axis × OLS result, M3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    axis_key: StandardAxisKey
    coef: float
    std_err: float = Field(ge=0.0)
    t_stat: float
    raw_p: float = Field(ge=0.0, le=1.0)
    fdr_q: float = Field(ge=0.0, le=1.0)
    ci_low_95: float
    ci_high_95: float
    beta_standardized: float
    vif: float = Field(gt=0.0)
    multicollinearity_flag: bool

    @model_validator(mode="after")
    def _v1_ci_bounds_coef(self) -> Self:
        """V1: ci_low_95 ≤ coef ≤ ci_high_95."""
        if not (self.ci_low_95 <= self.coef <= self.ci_high_95):
            raise ValueError(
                f"V1 CI bounds: must satisfy ci_low_95 ({self.ci_low_95}) ≤ "
                f"coef ({self.coef}) ≤ ci_high_95 ({self.ci_high_95})"
            )
        return self

    @model_validator(mode="after")
    def _v2_vif_positive(self) -> Self:
        """V2: vif > 0 (already enforced by Field gt=0.0; sanity)."""
        if self.vif <= 0:
            raise ValueError(f"V2 vif positive: got {self.vif}")
        return self


class RegressionFitSummary(BaseModel):
    """Model fit summary (header block, M4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    n_complete_case: int = Field(ge=0)
    n_dropped: int = Field(ge=0)
    r2: float = Field(ge=0.0, le=1.0)
    r2_adj: float = Field(le=1.0)
    f_stat: float = Field(ge=0.0)
    f_pvalue: float = Field(ge=0.0, le=1.0)
    regression_method: Literal["OLS"]
    multiple_comparison_method: Literal["BH-FDR"]
    small_sample_warning: bool

    @model_validator(mode="after")
    def _v1_small_sample_threshold(self) -> Self:
        """V1: small_sample_warning ⇔ n_complete_case < 30 (FR-018)."""
        expected = self.n_complete_case < 30
        if self.small_sample_warning != expected:
            raise ValueError(
                f"V1 small_sample_warning: must be {expected} when "
                f"n_complete_case={self.n_complete_case}, got {self.small_sample_warning}"
            )
        return self

    @model_validator(mode="after")
    def _v2_r2_in_unit_range(self) -> Self:
        """V2: 0 ≤ r2 ≤ 1 (already by Field; OLS multivariate cannot be negative)."""
        return self


__all__ = ["RegressionCoefficient", "RegressionFitSummary"]
