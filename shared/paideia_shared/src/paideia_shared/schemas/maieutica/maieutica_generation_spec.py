"""MaieuticaGenerationSpec: normalised form of generation_spec.yaml (spec 009 §1).

One run covers one chapter (= one week).  Defaults of 20 quiz candidates
and 3 formative candidates match the CLI / spec unset behaviour (R10).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .._common import CourseSlug, SemesterCode


class MaieuticaGenerationSpec(BaseModel):
    """Normalised professor-declared generation specification for one chapter run.

    Invariants enforced at construction:
    - ``week >= 1``, ``chapter_no >= 1``
    - ``1 <= quiz_count <= 20`` (FR-005), ``formative_count >= 1``

    Cross-field constraints (week/chapter_no present in CurriculumMap,
    chapter .txt exists) are enforced by the pipeline at runtime, not here,
    so that the contract remains loadable offline.
    """

    model_config = ConfigDict(extra="forbid")

    semester: SemesterCode
    course_slug: CourseSlug
    week: Annotated[int, Field(ge=1, description="Target week number (1-based).")]
    chapter_no: Annotated[int, Field(ge=1, description="Target chapter number (1-based).")]
    chapter: str = Field(..., description="Chapter display name (number + title).")
    quiz_count: Annotated[int, Field(ge=1, le=20)] = Field(
        default=20,
        description="Number of quiz candidates to generate (1..20, default 20; FR-005/R10).",
    )
    formative_count: Annotated[int, Field(ge=1)] = Field(
        default=3,
        description="Number of formative candidates to generate (default 3, R10).",
    )
