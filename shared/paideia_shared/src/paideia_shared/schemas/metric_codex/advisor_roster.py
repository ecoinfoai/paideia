"""AdvisorRosterEntry: single-row advisor-to-student assignment record.

Entity 4 (spec 013 US3). Uniqueness of student_id across a full roster is a
COLLECTION-level invariant enforced by the loader (metric_codex.distribute.roster),
not on this individual-row model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .._common import CanonicalStudentId


class AdvisorRosterEntry(BaseModel):
    """One student → advisor assignment row.

    Attributes:
        student_id: 10-digit canonical student ID.
        advisor_id: Opaque advisor identifier; must be non-empty.
        advisor_name: Display name of the advisor; ``None`` when not provided.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    advisor_id: str = Field(min_length=1, description="Non-empty advisor identifier.")
    advisor_name: str | None = Field(
        default=None,
        description="Advisor display name (optional).",
    )


__all__ = ["AdvisorRosterEntry"]
