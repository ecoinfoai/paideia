"""HistogramBin: one row per score-distribution bin (immersio Phase 1).

xlsx `1_히스토그램` 시트 행 (data-model.md §4).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HistogramBin(BaseModel):
    """One row per score bin (default 10-point bucket).

    예: bin_start=120, bin_end=130, count=24, cumulative=85, cumulative_pct=46.2.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    bin_start: float = Field(description="구간 시작 (포함)")
    bin_end: float = Field(description="구간 끝 (제외)")
    count: int = Field(ge=0, description="해당 구간 응시자 수")
    cumulative: int = Field(ge=0, description="누적 (구간 끝 미만)")
    cumulative_pct: float = Field(ge=0.0, le=100.0, description="누적 백분율")

    @model_validator(mode="after")
    def bin_order(self) -> "HistogramBin":
        """V1: bin_start < bin_end."""
        if self.bin_start >= self.bin_end:
            raise ValueError("HistogramBin V1: bin_start ≥ bin_end")
        return self
