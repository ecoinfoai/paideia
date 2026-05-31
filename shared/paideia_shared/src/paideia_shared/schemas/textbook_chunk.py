"""TextbookChunk: one clean passage from a textbook source file (spec 008).

Silver-layer schema. Produced by the textbook-ingestion step that strips
exercises, footnotes, and headers from the raw .txt files.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode


class TextbookChunk(BaseModel):
    """A contiguous, cleaned passage from a textbook file.

    ``chunk_id`` is deterministic (chapter-section-ordinal hash) so that
    repeated ingest of the same file produces identical IDs.  ``removed_spans``
    records what was stripped for audit/reproducibility purposes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    chunk_id: str = Field(..., description="결정론적 ID (장-절-순번 해시)")
    chapter_no: int
    chapter: str
    section: str | None = None
    source_file: str = Field(..., description="원본 교재 파일명 (권위)")
    line_start: int
    line_end: int
    text: str = Field(..., description="클린된 본문 (연습문제·각주·헤더 제거)")
    removed_spans: list[str] = Field(
        default_factory=list,
        description="제거된 구간 목록 (감사 로그)",
    )
