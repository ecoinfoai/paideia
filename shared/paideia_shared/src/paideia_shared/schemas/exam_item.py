"""ExamItem: per-question metadata extracted from the source YAML."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode


class ExamItem(BaseModel):
    """One row per exam question, providing grouping keys for analysis.

    Phase 1 (per-item statistics) and Phase 2 (chapter or source roll-ups)
    join exam results against this entity by ``(semester, course_slug, item_no)``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    item_no: Annotated[int, Field(ge=1)]
    chapter: str | None = None
    source: Literal["textbook", "formative", "quiz"] | None = None
    expected_difficulty: Literal["easy", "medium", "hard"] | None = None
    bloom: (
        Literal[
            "knowledge",
            "comprehension",
            "application",
            "analysis",
            "synthesis",
            "evaluation",
        ]
        | None
    ) = None
    answer_key: str
    points: Annotated[float, Field(ge=0)] = 1.0
    text: str | None = None
    distractors: list[str] | None = None
