"""StudentExamMetrics: per-student exam performance metrics (immersio Phase 2).

silver `학생지표.parquet` 행 + xlsx `학생성적` 시트 행 + Phase 6 카드 입력.
결시 학생도 행으로 존재하나 점수 필드는 None (data-model.md §2).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CanonicalStudentId, CourseSlug, SemesterCode


class StudentExamMetrics(BaseModel):
    """One row per student — exam performance metrics for Phase 6 card + Phase 3 join."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    name_kr: str | None = Field(default=None, description="이름 (출석부에서)")
    section: str | None = Field(default=None, description="분반 A/B/C/D")
    semester: SemesterCode
    course_slug: CourseSlug

    exam_taken: bool = Field(description="True=응시, False=결시")

    total_score: float | None = Field(default=None, description="원점수 (만점=문항수×문항당점수)")
    score_percent: float | None = Field(default=None, ge=0.0, le=100.0, description="100점 환산")

    section_percentile: float | None = Field(
        default=None, ge=0.0, le=100.0, description="분반 내 Hazen 백분위"
    )
    cohort_percentile: float | None = Field(
        default=None, ge=0.0, le=100.0, description="전체 응시자 Hazen 백분위"
    )
    z_score: float | None = Field(
        default=None, description="(score - mean) / pop_sd, sd=0이면 None"
    )

    chapter_correct_rates: dict[str, float] = Field(
        default_factory=dict, description="{챕터명: 정답률}"
    )
    source_correct_rates: dict[str, float] = Field(
        default_factory=dict, description="{출처: 정답률}"
    )
    difficulty_correct_rates: dict[int, float] = Field(
        default_factory=dict, description="{난이도: 정답률}"
    )
    expected_difficulty_correct_rates: dict[str, float] = Field(default_factory=dict)
    item_type_correct_rates: dict[str, float] = Field(default_factory=dict)

    interest_chapters_correct_rate: float | None = Field(
        default=None, description="관심 챕터(needs-map Q11)들의 정답률"
    )
    aversion_chapters_correct_rate: float | None = Field(
        default=None, description="비호감 챕터(needs-map Q12)들의 정답률"
    )

    @model_validator(mode="after")
    def absent_implies_no_scores(self) -> StudentExamMetrics:
        """V1: exam_taken=False ⇒ total_score/score_percent/percentile/z_score 모두 None."""
        if not self.exam_taken:
            scoreful = [
                self.total_score,
                self.score_percent,
                self.section_percentile,
                self.cohort_percentile,
                self.z_score,
            ]
            if any(f is not None for f in scoreful):
                raise ValueError(
                    "StudentExamMetrics V1: exam_taken=False but score fields populated"
                )
        return self

    @model_validator(mode="after")
    def percentile_consistency(self) -> StudentExamMetrics:
        """V2: total_score is not None ⇔ section_percentile is not None."""
        if (self.total_score is None) != (self.section_percentile is None):
            raise ValueError("StudentExamMetrics V2: total_score / section_percentile mismatch")
        return self
