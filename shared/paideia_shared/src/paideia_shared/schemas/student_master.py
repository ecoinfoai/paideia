"""StudentMaster: integrated per-student row produced by Phase 0 ingest."""

from __future__ import annotations

import re
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._common import (
    CanonicalStudentId,
    CourseSlug,
    SectionLabel,
    SemesterCode,
)

_AXIS_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,29}$")


class StudentMaster(BaseModel):
    """One row per student (roster + off-roster respondents merged).

    The terminal output of Phase 0 ingest. Phase 4 labelling and Phase 6
    one-pager card generation consume this entity as their primary input.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    semester: SemesterCode
    course_slug: CourseSlug
    on_roster: bool
    section: SectionLabel | None = None
    name_kr: str | None = None
    diagnostic_responded: bool
    exam_taken: bool
    exam_absent: bool
    attendance_recorded: bool
    exam_total_score: float | None = None
    exam_max_score: float | None = None
    attendance_present_count: int | None = None
    attendance_absent_count: int | None = None
    attendance_late_count: int | None = None
    attendance_excused_count: int | None = None
    axis_scores: dict[str, float | None]

    @model_validator(mode="after")
    def v1_exam_absent_consistency(self) -> Self:
        """exam_absent must equal (on_roster AND NOT exam_taken)."""
        expected = self.on_roster and not self.exam_taken
        if self.exam_absent != expected:
            raise ValueError(
                f"StudentMaster V1: exam_absent inconsistent for student_id="
                f"{self.student_id!r}; expected {expected} "
                f"(on_roster={self.on_roster}, exam_taken={self.exam_taken}), "
                f"found {self.exam_absent}."
            )
        return self

    @model_validator(mode="after")
    def v2_no_score_without_exam(self) -> Self:
        """exam_taken=False implies exam_total_score must be None."""
        if not self.exam_taken and self.exam_total_score is not None:
            raise ValueError(
                f"StudentMaster V2: exam_total_score must be None when "
                f"exam_taken=False (student_id={self.student_id!r}, "
                f"found exam_total_score={self.exam_total_score})."
            )
        return self

    @model_validator(mode="after")
    def v3_off_roster_no_section(self) -> Self:
        """on_roster=False allows section=None; reject section assignment."""
        if not self.on_roster and self.section is not None:
            raise ValueError(
                f"StudentMaster V3: section must be None when on_roster=False "
                f"(student_id={self.student_id!r}, found section={self.section!r})."
            )
        return self

    @model_validator(mode="after")
    def v4_axis_keys_format(self) -> Self:
        """All axis_scores keys must match snake_case ascii pattern."""
        for key in self.axis_scores:
            if not _AXIS_KEY_PATTERN.match(key):
                raise ValueError(
                    f"StudentMaster V4: axis_scores key {key!r} violates pattern "
                    f"^[a-z][a-z0-9_]{{0,29}}$ (student_id={self.student_id!r})."
                )
        return self
