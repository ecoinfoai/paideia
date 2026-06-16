"""CombinedAnalysisManifest (M7 in data-model.md, T010).

silver `manifest_phase3.json` 의 행 단위 모델. 한 실행의 감사 메타.
spec FR-021 의 모든 필드 + R-10 4 unmatched 필드 포함.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode, StandardAxisKey


class CombinedAnalysisManifest(BaseModel):
    """One execution's audit manifest (M7)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(min_length=1)
    module_version: str = Field(min_length=1)
    semester: SemesterCode
    course_slug: CourseSlug
    generated_at_utc: str = Field(min_length=1, description="ISO8601 UTC")

    factor_scores_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cluster_assignment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cluster_names_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description=(
            "SHA256 of the SPEC-GAP-001 cluster_names.json sidecar — guards "
            "against tampering of the cluster_id→label mapping that "
            "ClusterScoreComparison and recommendations rely on. Added per "
            "qa-engineer GAP-10 mitigation 2026-04-30."
        ),
    )
    student_metrics_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    student_master_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    diagnostic_response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    n_students_combined: int = Field(ge=0)
    n_diagnostic_only: int = Field(ge=0)
    n_exam_only: int = Field(ge=0)
    n_both: int = Field(ge=0)
    n_neither: int = Field(ge=0)

    # R-10 silent drop audit fields (보강 #6 by qa Section 8)
    n_unmatched_factor_scores: int = Field(ge=0)
    n_unmatched_cluster_assignment: int = Field(ge=0)
    n_unmatched_student_metrics: int = Field(ge=0)
    n_off_roster_respondents: int = Field(ge=0)

    ruleset_version: str = Field(min_length=1)
    regression_method: Literal["OLS"]
    multiple_comparison_method: Literal["BH-FDR"]
    posthoc_method_used: Literal["Tukey_HSD", "Games_Howell", "N/A"]
    run_seed: int

    needs_map_schema_version: str = Field(min_length=1)
    immersio_phase2_schema_version: str = Field(min_length=1)

    top3_predictor_axes: list[StandardAxisKey] = Field(
        default_factory=list, description="q<0.05 |β| top-3 axis_keys"
    )

    @model_validator(mode="after")
    def _v1_count_consistency(self) -> Self:
        """V1: only/both/neither sum == combined; R-10 unmatched all ≥ 0 (already enforced)."""
        s = self.n_diagnostic_only + self.n_exam_only + self.n_both + self.n_neither
        if s != self.n_students_combined:
            raise ValueError(
                f"V1 count consistency: only/both/neither sum ({s}) != "
                f"n_students_combined ({self.n_students_combined})"
            )
        # R-10 unmatched non-negative already enforced via Field(ge=0); sanity:
        for fname in (
            "n_unmatched_factor_scores",
            "n_unmatched_cluster_assignment",
            "n_unmatched_student_metrics",
            "n_off_roster_respondents",
        ):
            if getattr(self, fname) < 0:
                raise ValueError(
                    f"V1 R-10 unmatched: {fname} must be ≥ 0, got {getattr(self, fname)}"
                )
        return self

    @model_validator(mode="after")
    def _v3_top3_length_at_most_3(self) -> Self:
        """V3: top3_predictor_axes length ≤ 3."""
        if len(self.top3_predictor_axes) > 3:
            raise ValueError(f"V3 top3 length: must be ≤ 3, got {len(self.top3_predictor_axes)}")
        return self


__all__ = ["CombinedAnalysisManifest"]
