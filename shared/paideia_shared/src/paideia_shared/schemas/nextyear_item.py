"""NextYearItemProposal (M5): survey item proposal for next-year diagnostic.

Gold-layer schema. The retro-mester pipeline emits these when a gap analysis
reveals a blind spot in the current diagnostic (missing signals that would
have enabled a better root-cause hypothesis).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode

ProposedItemKind = Literal["likert", "single_select", "multiselect", "freetext"]
"""Survey item response format for the proposed diagnostic question."""


class NextYearItemProposal(BaseModel):
    """Proposal to add a diagnostic survey item in the next academic year.

    Attributes:
        missing_signal: Description of the signal that was absent this semester.
        target_unit_or_axis: Chapter or diagnostic axis the new item covers.
        proposed_kind: Response format for the proposed item.
        rationale: Evidence-backed reason why this signal is needed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    missing_signal: str = Field(
        ...,
        description="Short description of the signal absent from this semester's diagnostic.",
    )
    target_unit_or_axis: str = Field(
        ...,
        description="Chapter label or axis key the new survey item should cover.",
    )
    proposed_kind: ProposedItemKind = Field(
        ...,
        description="Response format for the proposed diagnostic survey item.",
    )
    rationale: str = Field(
        ...,
        description="Evidence-backed justification for adding this item.",
    )


__all__ = ["NextYearItemProposal", "ProposedItemKind"]
