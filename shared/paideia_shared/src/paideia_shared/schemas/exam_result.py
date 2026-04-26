"""ExamResult: long-form per-student per-item exam responses."""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CanonicalStudentId, CourseSlug, SemesterCode


class ExamResult(BaseModel):
    """One row per (student, exam_item) response with correctness flag.

    Phase 1 (item discrimination, accuracy, distractor analysis) and
    Phase 2 (chapter- or source-grouped accuracy) consume this entity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    semester: SemesterCode
    course_slug: CourseSlug
    item_no: Annotated[int, Field(ge=1)]
    response: str | None = None
    is_correct: bool | None = None
    score: float | None = None

    @model_validator(mode="after")
    def v1_no_response_shape(self) -> Self:
        """response=None implies is_correct=None; v0.1 sets score to 0.0."""
        if self.response is None and self.is_correct is not None:
            raise ValueError(
                f"ExamResult V1: response=None requires is_correct=None "
                f"(student_id={self.student_id!r}, item_no={self.item_no})."
            )
        return self
