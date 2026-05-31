"""ExamenBlueprint: normalised form of the professor's blueprint.yaml (spec 008).

Silver-layer schema. Parsed once from YAML and validated here before any
downstream code consumes it.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode

# tolerance for floating-point sum check
_FLOAT_EPS = 1e-6

DifficultyKey = Literal["easy", "medium", "hard"]
SourceKey = Literal["formative", "quiz", "textbook"]


class ExamenBlueprint(BaseModel):
    """Normalised exam specification declared by the professor.

    The raw ``blueprint.yaml`` is parsed and then stored as this model.
    All downstream solver/generator steps consume only this validated form.

    Invariants enforced at construction:
    - V1: ``40 <= total_items <= 50``
    - V2: ``sum(source_mix.values()) == total_items``
    - V3: ``sum(difficulty_targets.values()) ≈ 1.0`` (±1e-6)

    Note: The "formative == 형성 대장 수" cross-check is an *ingest-time*
    check that requires the external SourceInventory, so it is NOT enforced
    here — it happens in the blueprint solver when both artefacts are loaded.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    exam_name: str = Field(..., description="예: '2026-1학기 기말고사'")
    total_items: Annotated[int, Field(ge=40, le=50, description="출제 문항 수 (40~50)")]
    chapters: list[str] = Field(..., description="기말 범위 장 목록 (번호+이름)")
    difficulty_targets: dict[DifficultyKey, float] = Field(
        ...,
        description="난이도별 목표 비율 (합=1.0). 기본 easy=0.45, medium=0.35, hard=0.20",
    )
    source_mix: dict[SourceKey, int] = Field(
        ...,
        description="출처별 문항 수. sum == total_items 불변식 적용",
    )
    quiz_target: int = Field(default=15, description="퀴즈 목표 문항 수 (±2 허용)")
    answer_key_balance: bool = Field(
        default=True,
        description="정답 균형 검증 여부 (각 15~25%, 연속 ≤2)",
    )

    # ------------------------------------------------------------------
    # Model validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _v2_source_mix_sum(self) -> Self:
        """V2: sum(source_mix) must equal total_items."""
        total = sum(self.source_mix.values())
        if total != self.total_items:
            raise ValueError(
                f"V2: sum(source_mix) == {total} != total_items == {self.total_items}. "
                "source_mix 합계가 total_items와 일치해야 합니다."
            )
        return self

    @model_validator(mode="after")
    def _v3_difficulty_targets_sum(self) -> Self:
        """V3: sum(difficulty_targets) must be 1.0 ± 1e-6."""
        total = sum(self.difficulty_targets.values())
        if abs(total - 1.0) > _FLOAT_EPS:
            raise ValueError(
                f"V3: sum(difficulty_targets) == {total:.8f}, 1.0 과 차이가 {abs(total-1.0):.2e} "
                f"(허용 ±{_FLOAT_EPS:.0e})."
            )
        return self
