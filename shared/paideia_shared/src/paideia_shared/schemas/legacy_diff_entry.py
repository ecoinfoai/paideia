"""LegacyDiffEntry: one row per cell-level legacy↔immersio diff.

`legacy_diff.md` 표 행 (data-model.md §5).
텍스트 셀은 정확 일치만 표시; 수치 셀은 |legacy - immersio| > 0.001 인 셀만.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LegacyDiffEntry(BaseModel):
    """One row per cell-level difference between legacy and immersio xlsx."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sheet_name: str = Field(description="예: '4_정답률'")
    cell_address: str = Field(description="예: 'C5' (openpyxl coordinate)")
    cell_kind: Literal["text", "numeric", "missing_in_immersio"]

    legacy_value: str | float | None = Field(description="legacy 셀 값 (텍스트 또는 수치)")
    immersio_value: str | float | None = Field(description="immersio 셀 값")
    difference: float | None = Field(
        default=None, description="immersio - legacy (수치 셀만)"
    )

    reason_estimate: str = Field(description="사유 추정 (예: '결시 분모 포함 의심', '반올림 차이')")
    decision: Literal["immersio_채택", "legacy_미재현_의도적", "구조_불일치"] = Field(
        description="채택 결정"
    )

    @model_validator(mode="after")
    def difference_only_for_numeric(self) -> "LegacyDiffEntry":
        """V1: difference 는 cell_kind='numeric' 일 때만 not None."""
        if self.cell_kind == "numeric" and self.difference is None:
            raise ValueError("LegacyDiffEntry V1: numeric cell requires difference")
        if self.cell_kind != "numeric" and self.difference is not None:
            raise ValueError("LegacyDiffEntry V1: difference only for numeric cells")
        return self
