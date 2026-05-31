"""ExamenManifest: Gold-layer artefact manifest for one exam generation run (spec 008).

Written once per ``paideia examen generate`` invocation.  ``generated_at`` is
intentionally non-deterministic (wall-clock time) as the manifest is the only
examen output that is allowed to carry a timestamp.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode


class ExamenManifest(BaseModel):
    """Provenance and quality summary for one exam-generation run.

    ``targets_vs_actual`` is typed as ``dict`` (open schema) because its
    shape depends on which metrics the generator emits; downstream tools
    read it in a duck-typed manner.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    exam_name: str
    input_hashes: dict[str, str] = Field(
        ...,
        description="Bronze 입력 파일 해시 (파일명→SHA-256)",
    )
    config_ids: dict[str, str] = Field(
        ...,
        description="blueprint·curriculum_map 파일 식별자(SHA-256). 키워드사전은 교재에서 코드로 파생되어 별도 해시 대상 아님.",
    )
    generated_at: str = Field(
        ...,
        description="생성 시각 (비결정 — manifest 에만 허용)",
    )
    llm_backend: Literal["subscription", "api", "none(dry-run)"]
    llm_model: str | None = None
    cache_hit_rate: float | None = None
    item_count: int
    source_breakdown: dict[str, int]
    difficulty_breakdown: dict[str, int]
    chapter_breakdown: dict[str, int]
    answer_no_distribution: dict[int, int]
    groundedness: dict[str, int]
    targets_vs_actual: dict  # type: ignore[type-arg]
    emphasis_summary: dict | None = Field(  # type: ignore[type-arg]
        default=None,
        description=(
            "US7 강의 강조 집계 요약 (절 합계·강조 절 수·장별 강조 절 수). "
            "강조 자료 부재 시에도 항상 기록되며, 하류 immersio 가 강조 강도를 소비한다."
        ),
    )
