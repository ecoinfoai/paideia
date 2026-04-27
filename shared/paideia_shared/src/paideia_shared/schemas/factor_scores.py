"""FactorScoreRow (M4 in data-model.md).

Phase B output schema. One row per student carries six axis scores + six
z-score standardized values + six axis-level missing flags. immersio Phase 3
correlation/regression and Phase 4 labelling consume this entity.

Spec FR mapping: FR-006 (aggregation), FR-007 (missing handling + flag),
FR-008 (z-score standardization).

Determinism (M4 v1, v2):
- score and zscore must agree on nullness (both None or both float).
- ``{axis}_missing=True`` implies score is None — the drop policy preserves
  NaN; the mean_impute policy fills the value AND records missing=False.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._common import CanonicalStudentId, SectionLabel

_AXES: tuple[str, ...] = (
    "motivation",
    "anxiety",
    "self_efficacy",
    "interest",
    "prior_knowledge",
    "life_context",
)


class FactorScoreRow(BaseModel):
    """One student row with six axis scores + z-scores + missing flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    on_roster: bool
    responded: bool
    section: SectionLabel | None  # off-roster respondents may have section=None

    motivation: float | None
    anxiety: float | None
    self_efficacy: float | None
    interest: float | None
    prior_knowledge: float | None
    life_context: float | None

    motivation_z: float | None
    anxiety_z: float | None
    self_efficacy_z: float | None
    interest_z: float | None
    prior_knowledge_z: float | None
    life_context_z: float | None

    motivation_missing: bool
    anxiety_missing: bool
    self_efficacy_missing: bool
    interest_missing: bool
    prior_knowledge_missing: bool
    life_context_missing: bool

    @model_validator(mode="after")
    def v1_score_and_zscore_consistency(self) -> Self:
        """For every axis, score and z-score must both be None or both be float."""
        for axis in _AXES:
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
        for axis in _AXES:
            if getattr(self, f"{axis}_missing") and getattr(self, axis) is not None:
                raise ValueError(
                    f"FactorScoreRow V2: missing flag True but score not None "
                    f"for axis {axis!r} (student_id={self.student_id}). "
                    f"mean_impute results must record missing=False."
                )
        return self
