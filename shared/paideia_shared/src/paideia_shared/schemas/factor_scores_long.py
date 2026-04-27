"""FactorScoresLongRow — student-level long-form export (M7 in v0.1.1 data-model).

One row per student, written to gold ``factor_scores_long.{csv,yaml}`` so
downstream modules can join needs-map results to exam scores by student ID
without authoring a parquet parser. v0.1.1 spec FR-014/SC-003.

Includes the 8 quantitative axes × 3 fields = 24, the 3 auxiliary group
columns (single-select labels or ';'-joined multiselect lists), the
v0.1.0-inherit cluster fields, and per-freetext-area sentiment + dictionary
results.

The schema mirrors data-model.md §7 exactly. The auxiliary group / freetext
columns are operator-friendly strings (semicolon-joined lists for
multiselect) so the export can be opened in Excel without parsing.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ._common import STANDARD_AXIS_KEYS, CourseSlug, SemesterCode


class FactorScoresLongRow(BaseModel):
    """One student row, long-form, with axes + groups + cluster + freetext."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Identity
    student_id: str
    semester: SemesterCode
    course_slug: CourseSlug

    # Roster facts
    on_roster: bool
    section: str | None = None
    responded: bool

    # 8 quantitative axes × 3 (raw / z / missing)
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

    # 3 auxiliary groups (single-select labels, semicolon-joined multiselect lists)
    prior_readiness_q5: str | None = None
    prior_readiness_q6: str | None = None
    time_pattern_q21: str | None = None
    time_pattern_q22: str | None = None  # multiselect → ';'-joined
    time_pattern_q23: str | None = None
    interest_topics_q9: str | None = None  # multiselect → ';'-joined
    interest_topics_q10: str | None = None
    interest_topics_q11: str | None = None
    categorical_intent_q12: str | None = None
    categorical_intent_q13: str | None = None

    # Cluster (v0.1.0 inherit)
    cluster_id: int | None = None
    cluster_label: str | None = None
    cluster_distance: float | None = None

    # Freetext × 2 areas (Q61 anxiety, Q62 experience)
    freetext_q61_categories: str | None = None  # ';'-joined dictionary categories
    freetext_q61_negativity: float | None = None
    freetext_q61_top_emotion: str | None = None
    freetext_q62_categories: str | None = None
    freetext_q62_negativity: float | None = None
    freetext_q62_top_emotion: str | None = None

    @field_validator("student_id")
    @classmethod
    def _student_id_is_ten_digits(cls, value: str) -> str:
        """student_id MUST be a 10-character ASCII digit string."""
        if not (isinstance(value, str) and value.isdigit() and len(value) == 10):
            raise ValueError(
                f"FactorScoresLongRow: student_id must be 10 digits, got {value!r}."
            )
        return value

    @model_validator(mode="after")
    def _missing_consistency(self) -> Self:
        """For every axis: ``raw is None ⇔ missing == True`` (data-model §7)."""
        for axis in STANDARD_AXIS_KEYS:
            raw = getattr(self, f"{axis}_raw")
            missing = getattr(self, f"{axis}_missing")
            if (raw is None) != missing:
                raise ValueError(
                    f"FactorScoresLongRow: axis {axis!r} raw/missing inconsistent "
                    f"(raw={raw!r}, missing={missing}); both must agree."
                )
        return self

    @model_validator(mode="after")
    def _negativity_in_unit_range(self) -> Self:
        """Each freetext area's negativity score MUST be in [0, 1] when present."""
        for area in ("q61", "q62"):
            negativity = getattr(self, f"freetext_{area}_negativity")
            if negativity is not None and not (0.0 <= negativity <= 1.0):
                raise ValueError(
                    f"FactorScoresLongRow: freetext_{area}_negativity={negativity} "
                    "out of range [0.0, 1.0]."
                )
        return self
