"""UnitGap (M2): per-chapter, per-segment gap analysis row.

Silver-layer schema. One row per (semester, course_slug, chapter, segment)
combination. Downstream recommendation engine (M3) selects rows where
is_structural=True and orders by impact_score descending.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode
from .retro_common import CauseLabel, ImportanceLevel, SegmentKey, ValidityVerdict

_FLOAT_EPS = 1e-6


class UnitGap(BaseModel):
    """One gap record for a chapter × segment combination.

    Invariants enforced at construction:
    - V1: ``n_below <= evidence_n``
    - V2: ``abs(impact_score - n_below * weight) < 1e-6``
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    chapter: str = Field(..., description="Chapter label (e.g. '8장 호흡계통').")
    segment: SegmentKey
    segment_mean_rate: float = Field(
        ...,
        description="Mean correct rate for this chapter within the segment.",
    )
    n_below: int = Field(
        ...,
        ge=0,
        description="Number of segment students below gap_threshold on this chapter.",
    )
    pct_segment: float = Field(
        ...,
        description="Fraction of segment students below gap_threshold (0..1).",
    )
    pct_cohort: float = Field(
        ...,
        description="Fraction of whole cohort below gap_threshold on this chapter.",
    )
    is_structural: bool = Field(
        ...,
        description="True when the gap persists across item types, flagging a structural issue.",
    )
    cohort_failing_item_types: list[str] = Field(
        ...,
        description="Item-type labels where cohort pass rate is below threshold.",
    )
    cause: CauseLabel
    cause_signals: dict[str, float] = Field(
        ...,
        description="Numeric evidence values that contributed to the cause label.",
    )
    validity: ValidityVerdict
    unit_importance: ImportanceLevel
    weight: float = Field(
        ...,
        description="Numeric importance weight (derived from unit_importance via config).",
    )
    impact_score: float = Field(
        ...,
        description="n_below × weight; priority sort key for recommendations.",
    )
    evidence_n: int = Field(
        ...,
        ge=0,
        description="Number of students with valid data for this chapter analysis.",
    )

    # ------------------------------------------------------------------
    # Model validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _v1_n_below_le_evidence_n(self) -> Self:
        """V1: n_below must not exceed evidence_n."""
        if self.n_below > self.evidence_n:
            raise ValueError(
                f"V1: n_below={self.n_below} > evidence_n={self.evidence_n}; "
                "students below threshold cannot exceed total measured."
            )
        return self

    @model_validator(mode="after")
    def _v2_impact_score_formula(self) -> Self:
        """V2: impact_score must equal n_below * weight (±1e-6)."""
        expected = self.n_below * self.weight
        if abs(self.impact_score - expected) >= _FLOAT_EPS:
            raise ValueError(
                f"V2: impact_score={self.impact_score!r} != n_below * weight "
                f"({self.n_below} × {self.weight} = {expected!r}); "
                f"diff={abs(self.impact_score - expected):.2e} exceeds ±{_FLOAT_EPS:.0e}."
            )
        return self


__all__ = ["UnitGap"]
