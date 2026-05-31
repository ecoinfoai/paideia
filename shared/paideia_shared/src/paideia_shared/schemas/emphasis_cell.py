"""EmphasisCell: per-section lecture-emphasis indicator (spec 008).

Silver-layer schema (enrichment).  One row per (semester, course_slug,
chapter_no, section) quad.  ``is_emphasized`` is the canonical flag; its
consistency with the count fields is enforced at construction.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode


class EmphasisCell(BaseModel):
    """Emphasis indicator for one section across all available class sections.

    Invariants are declared and run in V-number order:
    - V1 (prerequisite): ``emphasized_class_count <= available_class_count``
    - V2: ``is_emphasized == (emphasized_class_count == available_class_count
      and available_class_count > 0)``

    Callers must set ``is_emphasized`` consistently; there is no auto-derive so
    that the field remains explicit and serialisable without side-effects.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    chapter_no: int
    section: str
    emphasized_class_count: Annotated[int, Field(ge=0, le=4)]
    available_class_count: Annotated[int, Field(ge=0, le=4)]
    is_emphasized: bool
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="분반·차시·검색어 근거 목록",
    )

    @model_validator(mode="after")
    def _v1_count_consistency(self) -> Self:
        """V1 (prerequisite): emphasized_class_count must not exceed available_class_count."""
        if self.emphasized_class_count > self.available_class_count:
            raise ValueError(
                f"V1: emphasized_class_count ({self.emphasized_class_count}) > "
                f"available_class_count ({self.available_class_count}). "
                "강조 분반 수가 가용 분반 수를 초과할 수 없습니다."
            )
        return self

    @model_validator(mode="after")
    def _v2_is_emphasized_consistent(self) -> Self:
        """V2: is_emphasized must equal (emphasized==available and available>0)."""
        expected = (
            self.emphasized_class_count == self.available_class_count
            and self.available_class_count > 0
        )
        if self.is_emphasized != expected:
            raise ValueError(
                f"V2: is_emphasized=={self.is_emphasized} is inconsistent with counts "
                f"(emphasized={self.emphasized_class_count}, "
                f"available={self.available_class_count}). "
                f"올바른 값은 {expected} 입니다."
            )
        return self
