"""DiagnosticResponse: long-form diagnostic answers per student × axis."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CanonicalStudentId, CourseSlug, SemesterCode


class DiagnosticResponse(BaseModel):
    """One row per (student, axis[, option_key]) coded diagnostic answer.

    Carries Likert integers, multiselect one-hot booleans, or freetext
    originals depending on `axis_kind`. Phase 3 correlation, regression,
    and clustering analyses consume this entity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    semester: SemesterCode
    course_slug: CourseSlug
    axis: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")]
    axis_kind: Literal["likert", "multiselect_onehot", "freetext"]
    option_key: str | None = None
    value_int: Annotated[int, Field(ge=1, le=7)] | None = None
    value_bool: bool | None = None
    value_text: str | None = None
    source_column: str

    @model_validator(mode="after")
    def v1_likert_shape(self) -> Self:
        """axis_kind='likert' requires value_int set; others None."""
        if self.axis_kind != "likert":
            return self
        if self.value_int is None:
            raise ValueError(
                f"DiagnosticResponse V1: axis_kind='likert' requires value_int "
                f"(student_id={self.student_id!r}, axis={self.axis!r})."
            )
        if (
            self.value_bool is not None
            or self.value_text is not None
            or self.option_key is not None
        ):
            raise ValueError(
                f"DiagnosticResponse V1: axis_kind='likert' must leave "
                f"value_bool/value_text/option_key as None "
                f"(student_id={self.student_id!r}, axis={self.axis!r})."
            )
        return self

    @model_validator(mode="after")
    def v2_multiselect_shape(self) -> Self:
        """axis_kind='multiselect_onehot' requires value_bool and option_key set."""
        if self.axis_kind != "multiselect_onehot":
            return self
        if self.value_bool is None or self.option_key is None:
            raise ValueError(
                f"DiagnosticResponse V2: axis_kind='multiselect_onehot' requires "
                f"both value_bool and option_key "
                f"(student_id={self.student_id!r}, axis={self.axis!r})."
            )
        if self.value_int is not None or self.value_text is not None:
            raise ValueError(
                f"DiagnosticResponse V2: axis_kind='multiselect_onehot' must leave "
                f"value_int/value_text as None "
                f"(student_id={self.student_id!r}, axis={self.axis!r})."
            )
        return self

    @model_validator(mode="after")
    def v3_freetext_shape(self) -> Self:
        """axis_kind='freetext' requires value_text set; others None."""
        if self.axis_kind != "freetext":
            return self
        if self.value_text is None:
            raise ValueError(
                f"DiagnosticResponse V3: axis_kind='freetext' requires value_text "
                f"(student_id={self.student_id!r}, axis={self.axis!r})."
            )
        if self.value_int is not None or self.value_bool is not None or self.option_key is not None:
            raise ValueError(
                f"DiagnosticResponse V3: axis_kind='freetext' must leave "
                f"value_int/value_bool/option_key as None "
                f"(student_id={self.student_id!r}, axis={self.axis!r})."
            )
        return self
