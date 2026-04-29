"""CombinedAnalysisRow (M1 in data-model.md).

Phase 3 silver `진단×시험결합.parquet` 행 단위 모델. 학생 1명당 60 컬럼
(Identity 6 + needs-map factor_scores 24 + cluster 3 + immersio exam 6 +
dict 컬럼 7 + needs-map 보조 그룹 10 + 결합 메타 4) 고정.

Phase 4 라벨링 + retro-mester (v0.2) 의 직접 입력. spec FR-014 / FR-015 / FR-016.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import (
    STANDARD_AXIS_KEYS,
    CanonicalStudentId,
    CourseSlug,
    SectionLabel,
    SemesterCode,
)


class CombinedAnalysisRow(BaseModel):
    """One student row in silver `진단×시험결합.parquet` — 60-column merged master."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Group 1 — Identity (6 columns)
    student_id: CanonicalStudentId
    name_kr: str | None = None
    on_roster: bool
    section: SectionLabel | None = None
    semester: SemesterCode
    course_slug: CourseSlug

    # Group 2 — needs-map factor_scores (24 columns: 8 axes × {raw, z, missing})
    digital_efficacy_raw: float | None = None
    digital_efficacy_z: float | None = None
    digital_efficacy_missing: bool

    motivation_raw: float | None = None
    motivation_z: float | None = None
    motivation_missing: bool

    time_availability_raw: float | None = None
    time_availability_z: float | None = None
    time_availability_missing: bool

    material_preference_raw: float | None = None
    material_preference_z: float | None = None
    material_preference_missing: bool

    study_strategy_raw: float | None = None
    study_strategy_z: float | None = None
    study_strategy_missing: bool

    study_environment_raw: float | None = None
    study_environment_z: float | None = None
    study_environment_missing: bool

    social_learning_raw: float | None = None
    social_learning_z: float | None = None
    social_learning_missing: bool

    feedback_seeking_raw: float | None = None
    feedback_seeking_z: float | None = None
    feedback_seeking_missing: bool

    # Group 3 — needs-map cluster (3 columns)
    cluster_id: int | None = None
    cluster_label: str | None = None
    cluster_distance: float | None = None

    # Group 4 — immersio exam scores (6 columns)
    exam_taken: bool
    total_score: float | None = None
    score_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    section_percentile: float | None = Field(default=None, ge=0.0, le=100.0)
    cohort_percentile: float | None = Field(default=None, ge=0.0, le=100.0)
    z_score: float | None = None

    # Group 5 — immersio exam dict columns (7 columns; dict columns serialized as JSON in parquet)
    chapter_correct_rates: dict[str, float] = Field(default_factory=dict)
    source_correct_rates: dict[str, float] = Field(default_factory=dict)
    difficulty_correct_rates: dict[int, float] = Field(default_factory=dict)
    expected_difficulty_correct_rates: dict[str, float] = Field(default_factory=dict)
    item_type_correct_rates: dict[str, float] = Field(default_factory=dict)
    interest_chapters_correct_rate: float | None = None
    aversion_chapters_correct_rate: float | None = None

    # Group 6 — needs-map auxiliary groups (10 columns)
    prior_readiness_q5: str | None = None
    prior_readiness_q6: str | None = None
    time_pattern_q21: str | None = None
    time_pattern_q22: str | None = None
    time_pattern_q23: str | None = None
    interest_topics_q9: str | None = None
    interest_topics_q10: str | None = None
    interest_topics_q11: str | None = None
    categorical_intent_q12: str | None = None
    categorical_intent_q13: str | None = None

    # Group 7 — combined metadata (4 columns)
    진단응답: bool
    시험응시: bool
    needs_map_schema_version: str
    immersio_phase2_schema_version: str

    @model_validator(mode="after")
    def _v2_factor_score_consistency(self) -> Self:
        """V2: per-axis raw/z/missing consistency.

        For each of 8 axes:
        - raw is None ⇔ missing is True
        - raw is None ⇔ z is None
        """
        for axis in STANDARD_AXIS_KEYS:
            raw = getattr(self, f"{axis}_raw")
            z = getattr(self, f"{axis}_z")
            missing = getattr(self, f"{axis}_missing")

            if (raw is None) != missing:
                raise ValueError(
                    f"V2 factor consistency: {axis}_raw is None ({raw is None}) but "
                    f"{axis}_missing={missing}; raw=None ⇔ missing=True required"
                )
            if (raw is None) != (z is None):
                raise ValueError(
                    f"V2 factor consistency: {axis}_raw and {axis}_z must agree on "
                    f"nullness (raw is None={raw is None}, z is None={z is None})"
                )
        return self

    @model_validator(mode="after")
    def _v3_exam_taken_consistency(self) -> Self:
        """V3: exam_taken=False ⇒ all 5 score fields None. 시험응시 == exam_taken."""
        if not self.exam_taken:
            scoreful = (
                self.total_score,
                self.score_percent,
                self.section_percentile,
                self.cohort_percentile,
                self.z_score,
            )
            if any(field is not None for field in scoreful):
                raise ValueError(
                    "V3 exam_taken consistency: exam_taken=False but score fields populated"
                )
        if self.시험응시 != self.exam_taken:
            raise ValueError(
                f"V3 exam_taken consistency: 시험응시 ({self.시험응시}) must equal "
                f"exam_taken ({self.exam_taken})"
            )
        return self

    @model_validator(mode="after")
    def _v4_cluster_consistency(self) -> Self:
        """V4: cluster_id / cluster_label / cluster_distance — all None or all not None."""
        triple = (self.cluster_id, self.cluster_label, self.cluster_distance)
        none_count = sum(1 for v in triple if v is None)
        if none_count not in (0, 3):
            raise ValueError(
                f"V4 cluster consistency: cluster_id/cluster_label/cluster_distance "
                f"must all be None or all be not-None; got {triple}"
            )
        return self

    @model_validator(mode="after")
    def _v5_diagnostic_response_flag(self) -> Self:
        """V5: 진단응답 == any(axis raw is not None for axis in 8)."""
        any_axis_raw_present = any(
            getattr(self, f"{axis}_raw") is not None for axis in STANDARD_AXIS_KEYS
        )
        if self.진단응답 != any_axis_raw_present:
            raise ValueError(
                f"V5 diagnostic_response flag: 진단응답 ({self.진단응답}) must equal "
                f"presence of any axis raw value ({any_axis_raw_present})"
            )
        return self


__all__ = ["CombinedAnalysisRow"]
