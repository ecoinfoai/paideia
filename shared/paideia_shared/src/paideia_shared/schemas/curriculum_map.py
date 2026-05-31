"""CurriculumMap + CurriculumEntry: week→chapter→section mapping (spec 008).

Silver-layer schema. Parsed from curriculum_map.yaml and validated here.
The same chapter_no may span multiple weeks (e.g., chapter 9 covers weeks
10 and 11); that pattern is explicitly permitted.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ._common import CourseSlug, SemesterCode


class CurriculumEntry(BaseModel):
    """One row of the curriculum map: a weekly teaching unit.

    A single chapter may appear in multiple entries if it spans several weeks.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    week: int
    chapter: str
    chapter_no: int
    subtopic: str | None = None
    sections: list[str]


class CurriculumMap(BaseModel):
    """Full curriculum map for one semester-course pair.

    Validation note: FR-004 (교재 파일 존재 확인) is an ingest-time check
    that requires file-system access and is therefore NOT enforced in this
    schema.  It is checked by the blueprint solver when loading artefacts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    entries: list[CurriculumEntry]
