"""CohortRow — silver parquet row for cohort partitions (US6, FR-H06)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .email_dispatch_log_row import CohortLabel

_STUDENT_ID_RE = re.compile(r"^\d{10}$")


class CohortRow(BaseModel):
    """One row of cohort_{label}.parquet (data-model.md §8.5)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    student_id: str
    name_kr: str = Field(min_length=1)
    score_percent: float = Field(ge=0.0, le=100.0)
    cohort: CohortLabel

    @field_validator("student_id")
    @classmethod
    def _v_student_id(cls, value: str) -> str:
        if not _STUDENT_ID_RE.fullmatch(value):
            raise ValueError(f"CohortRow.student_id must match ^\\d{{10}}$ (got {value!r})")
        return value

    @field_validator("cohort")
    @classmethod
    def _v_cohort_not_all(cls, value: CohortLabel) -> CohortLabel:
        if value == CohortLabel.ALL:
            raise ValueError("CohortRow.cohort must be LOW_SCORE or REST (not ALL)")
        return value


__all__ = ["CohortRow"]
