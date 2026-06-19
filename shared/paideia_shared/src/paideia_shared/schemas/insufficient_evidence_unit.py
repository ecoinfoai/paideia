"""InsufficientEvidenceUnit (spec 012): zero-evidence chapter × segment record.

Silver-layer schema. One record per (semester, course_slug, chapter, segment)
combination where the target segment has ZERO answer-data students for that
chapter. Mutually exclusive with UnitGap: any (chapter × segment) with at
least one measured student must go through UnitGap, not here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode
from .retro_common import SegmentKey


class InsufficientEvidenceUnit(BaseModel):
    """A (chapter × segment) entry with zero answer-data students.

    Invariants enforced at construction:
    - V1: ``evidence_n`` must equal 0; any nonzero value belongs in UnitGap.

    Attributes:
        semester: Academic semester code (e.g. '2026-1').
        course_slug: ASCII kebab-case course identifier (e.g. 'anatomy').
        chapter: Chapter label (e.g. '8장 호흡계통'). Must be non-empty.
        segment: Demographic segment ('학령기' or '만학도').
        evidence_n: Number of students with valid data; must be 0 by definition.
        reason: Missing-reason literal; always '근거부족-자료없음'.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    chapter: str = Field(..., min_length=1, description="Chapter label (e.g. '8장 호흡계통').")
    segment: SegmentKey
    evidence_n: int = Field(
        ...,
        description="Number of students with valid data; must be 0 for a 근거부족 unit.",
    )
    reason: Literal["근거부족-자료없음"]

    # ------------------------------------------------------------------
    # Model validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _v1_evidence_n_must_be_zero(self) -> "InsufficientEvidenceUnit":
        """V1: evidence_n must equal 0; nonzero data belongs in UnitGap."""
        if self.evidence_n != 0:
            raise ValueError(
                f"V1: evidence_n={self.evidence_n} != 0; "
                "a 근거부족 unit has zero answer-data students by definition. "
                "Use UnitGap for any (chapter × segment) with evidence_n >= 1."
            )
        return self


__all__ = ["InsufficientEvidenceUnit"]
