"""AdvisorRosterEntry: single-row advisor-to-student assignment record.

Entity 4 (spec 013 US3). Uniqueness of student_id across a full roster is a
COLLECTION-level invariant enforced by the loader (metric_codex.distribute.roster),
not on this individual-row model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .._common import CanonicalStudentId

# advisor_id becomes a path segment under 지도교수별/.  The pattern forbids any
# path-traversal or separator character: no leading dot (blocks '.', '..',
# '.hidden'), no '/', '\\', or NUL anywhere (blocks slashes, absolute paths,
# NUL injection), and no C0 control characters \x00-\x1f anywhere (blocks
# newline, tab, carriage-return injection into path segments).
# Legitimate ids like 'prof-kim', 'prof.kim', 'ADV001', or an employee number
# still validate.
_ADVISOR_ID_PATTERN = r"^[^/\\.\x00-\x1f][^/\\\x00-\x1f]*$"


class AdvisorRosterEntry(BaseModel):
    """One student → advisor assignment row.

    Attributes:
        student_id: 10-digit canonical student ID.
        advisor_id: Opaque advisor identifier; non-empty and free of path
            separators / leading dot (it is used as a directory name).
        advisor_name: Display name of the advisor; ``None`` when not provided.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    advisor_id: str = Field(
        min_length=1,
        pattern=_ADVISOR_ID_PATTERN,
        description="Non-empty advisor identifier; no path separators or leading dot.",
    )
    advisor_name: str | None = Field(
        default=None,
        description="Advisor display name (optional).",
    )


__all__ = ["AdvisorRosterEntry"]
