"""SourceInventoryEntry: one formative or quiz item from the source inventory (spec 008).

Silver-layer schema. Produced by the ingest step that reads the professor's
formative-assessment and quiz YAML/xlsx files.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode


class SourceInventoryEntry(BaseModel):
    """One item in the source inventory — either a formative question or a quiz question.

    Fields marked "formative 전용" are unused (None) for quiz entries and vice
    versa; no cross-field invariants are enforced here so that partial rows
    from partial ingests remain valid at this layer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    source: Literal["formative", "quiz"]
    source_ref: str = Field(
        ...,
        description="예: '형성평가:1장#1' 또는 '퀴즈:1주#3'",
    )
    chapter_no: int | None = None
    week: int | None = None
    stem: str = Field(..., description="원문 질문 (형성=서술형, 퀴즈=객관식 stem)")
    # 형성 전용
    model_answer: str | None = None
    keywords: list[str] = Field(default_factory=list)
    rubric: dict[str, str] | None = None
    # 퀴즈 전용
    options: list[str] | None = None
    answer: str | None = None
