"""CorrelationCell (M2 in data-model.md).

xlsx `상관매트릭스` 시트 + heatmap fig3 의 행 단위. 8 axes × 14 exam metrics
(total + 13 챕터별) = 112 cells (학기별 챕터 수 가변).
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import StandardAxisKey


class CorrelationCell(BaseModel):
    """One Pearson correlation cell (axis × exam metric)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    axis_key: StandardAxisKey
    exam_metric_key: str = Field(min_length=1)
    n: int = Field(ge=0, description="pairwise sample size")
    pearson_r: float | None = None
    raw_p: float | None = None
    fdr_q: float | None = None
    significant_after_correction: bool
    unstable_inference_flag: bool

    @model_validator(mode="after")
    def _v1_n_zero_implies_all_none(self) -> Self:
        """V1: n == 0 ⇒ all stats None and significant=False."""
        if self.n == 0:
            if self.pearson_r is not None or self.raw_p is not None or self.fdr_q is not None:
                raise ValueError(
                    "V1 n=0 nullness: all of pearson_r/raw_p/fdr_q must be None when n=0"
                )
            if self.significant_after_correction:
                raise ValueError(
                    "V1 n=0 nullness: significant_after_correction must be False when n=0"
                )
        return self

    @model_validator(mode="after")
    def _v2_q_in_unit_range(self) -> Self:
        """V2: fdr_q is None or 0.0 ≤ q ≤ 1.0."""
        if self.fdr_q is not None and not (0.0 <= self.fdr_q <= 1.0):
            raise ValueError(
                f"V2 q range: fdr_q must be in [0, 1] when populated, got {self.fdr_q}"
            )
        return self


__all__ = ["CorrelationCell"]
