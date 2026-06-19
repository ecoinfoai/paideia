"""AdvisorBundleSummary: aggregate coverage report for advisor assignment.

Entity 6. Used as an embedded sub-document in MetricCodexManifest and also
written as a standalone Gold-layer artefact after the distribute stage.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .._common import CanonicalStudentId


class AdvisorBundleSummary(BaseModel):
    """Coverage summary for one advisor assignment pass.

    Invariant (no-silent-skip):
    ``assigned_count + len(unassigned_sids) == total_students_with_codex``.
    A ValueError is raised at construction if the invariant is violated — this
    prevents silently under-counting unassigned students.

    Attributes:
        total_students_with_codex: Total students that have at least one CodexEntry.
        assigned_count: Number of students successfully assigned to an advisor.
        unassigned_sids: Canonical student IDs without an advisor assignment (ASC-sorted).
        advisor_count: Number of distinct advisors with at least one assignment.
        per_advisor_counts: Advisor identifier → count of assigned students.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_students_with_codex: int = Field(ge=0, description="Total students with codex entries.")
    assigned_count: int = Field(ge=0, description="Students successfully assigned to an advisor.")
    unassigned_sids: list[CanonicalStudentId] = Field(
        ...,
        description="Student IDs without advisor assignment — must be ASC-sorted.",
    )
    advisor_count: int = Field(ge=0, description="Number of distinct advisors with assignments.")
    per_advisor_counts: dict[str, int] = Field(
        ...,
        description="Advisor identifier → number of assigned students.",
    )

    @model_validator(mode="after")
    def _invariant_count_consistency(self) -> Self:
        """Enforce: assigned_count + len(unassigned_sids) == total_students_with_codex."""
        actual = self.assigned_count + len(self.unassigned_sids)
        if actual != self.total_students_with_codex:
            raise ValueError(
                f"assigned_count ({self.assigned_count}) + "
                f"len(unassigned_sids) ({len(self.unassigned_sids)}) "
                f"= {actual}, but total_students_with_codex = {self.total_students_with_codex}."
            )
        return self


__all__ = ["AdvisorBundleSummary"]
