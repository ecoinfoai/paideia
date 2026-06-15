"""AlignmentFinding (M4): teaching-assessment alignment diagnostic per chapter.

Silver-layer schema. One row per (semester, course_slug, chapter). The
alignment engine compares taught_weeks, tested_items, and cognitive_profile
to produce the flag and optional interest/aversion gaps.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode
from .retro_common import AlignmentFlag


class AlignmentFinding(BaseModel):
    """Teaching-assessment alignment record for one chapter.

    Note:
        interest_gap and aversion_gap are None when the needs-map diagnostic
        survey did not capture topic preferences for this chapter.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    chapter: str = Field(..., description="Chapter label (e.g. '8장 호흡계통').")
    taught_weeks: int = Field(
        ...,
        ge=0,
        description="Number of lecture-weeks devoted to this chapter.",
    )
    tested_items: int = Field(
        ...,
        ge=0,
        description="Number of exam items drawn from this chapter.",
    )
    learned_rate: float = Field(
        ...,
        description="Cohort mean correct rate on chapter items (0..1).",
    )
    cognitive_profile: dict[str, float] = Field(
        ...,
        description=(
            "Correct rate per Bloom's-taxonomy level for this chapter "
            "(e.g. {'기억': 0.82, '이해': 0.65, '적용': 0.50})."
        ),
    )
    flag: AlignmentFlag
    interest_gap: float | None = Field(
        default=None,
        description=(
            "Difference between learned_rate on interest-flagged chapters vs "
            "chapter mean; None when interest data unavailable."
        ),
    )
    aversion_gap: float | None = Field(
        default=None,
        description=(
            "Difference between learned_rate on aversion-flagged chapters vs "
            "chapter mean; None when aversion data unavailable."
        ),
    )
    note: str = Field(
        default="",
        description="Free-text human-readable summary of the finding.",
    )


__all__ = ["AlignmentFinding"]
