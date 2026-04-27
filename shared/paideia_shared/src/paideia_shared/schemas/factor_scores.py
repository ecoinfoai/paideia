"""FactorScoreRow (M4 in data-model.md).

Phase B output schema. One row per student carries 8 axis scores + 8
z-score standardized values + 8 axis-level missing flags (24 axis fields
under v0.1.1; was 18 under v0.1.0). immersio Phase 3 correlation/regression
and Phase 4 labelling consume this entity.

Spec FR mapping: FR-006 (aggregation), FR-007 (missing handling + flag),
FR-008 (z-score standardization), FR-013 (8-axis vocabulary).

Determinism (M4 v1, v2):
- score and zscore must agree on nullness (both None or both float).
- ``{axis}_missing=True`` implies score is None — the drop policy preserves
  NaN; the mean_impute policy fills the value AND records missing=False.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._common import STANDARD_AXIS_KEYS, CanonicalStudentId, SectionLabel


class FactorScoreRow(BaseModel):
    """One student row with 8 axis scores + z-scores + missing flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    on_roster: bool
    responded: bool
    section: SectionLabel | None  # off-roster respondents may have section=None

    digital_efficacy: float | None
    motivation: float | None
    time_availability: float | None
    material_preference: float | None
    study_strategy: float | None
    study_environment: float | None
    social_learning: float | None
    feedback_seeking: float | None

    digital_efficacy_z: float | None
    motivation_z: float | None
    time_availability_z: float | None
    material_preference_z: float | None
    study_strategy_z: float | None
    study_environment_z: float | None
    social_learning_z: float | None
    feedback_seeking_z: float | None

    digital_efficacy_missing: bool
    motivation_missing: bool
    time_availability_missing: bool
    material_preference_missing: bool
    study_strategy_missing: bool
    study_environment_missing: bool
    social_learning_missing: bool
    feedback_seeking_missing: bool

    @model_validator(mode="after")
    def v1_score_and_zscore_consistency(self) -> Self:
        """For every axis, score and z-score must both be None or both be float."""
        for axis in STANDARD_AXIS_KEYS:
            score = getattr(self, axis)
            zscore = getattr(self, f"{axis}_z")
            if (score is None) != (zscore is None):
                raise ValueError(
                    f"FactorScoreRow V1: score/z-score nullness mismatch for axis "
                    f"{axis!r} (student_id={self.student_id})."
                )
        return self

    @model_validator(mode="after")
    def v2_missing_flag_implies_score_none(self) -> Self:
        """``{axis}_missing=True`` requires score to be None.

        ``mean_impute`` results MUST record missing=False (the imputed value is
        the score; the drop policy preserves None and sets missing=True).
        """
        for axis in STANDARD_AXIS_KEYS:
            if getattr(self, f"{axis}_missing") and getattr(self, axis) is not None:
                raise ValueError(
                    f"FactorScoreRow V2: missing flag True but score not None "
                    f"for axis {axis!r} (student_id={self.student_id}). "
                    f"mean_impute results must record missing=False."
                )
        return self
