"""RetroMesterConfig (M1): run-time configuration for one retro-mester analysis.

Silver-layer schema validated at pipeline boot. All downstream steps receive
only this validated form; cross-file key checks (e.g. effort_ratings keys ⊆
chapter list) happen in the loader after both artefacts are loaded.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CanonicalStudentId, CourseSlug, SemesterCode
from .retro_common import (
    EffortLevel,
    ImportanceLevel,
    SegmentKey,
)

_IMPORTANCE_KEYS = frozenset({"상", "중", "하"})


class RetroMesterConfig(BaseModel):
    """Run configuration for one retro-mester semester retrospective.

    Invariants enforced at construction:
    - V1: ``0 <= gap_threshold <= 1``
    - V2: ``low_discrimination_threshold >= 0``
    - V3: ``cognitive_cliff_drop >= 0``
    - V4: ``importance_weights`` keys == {상, 중, 하} exactly

    Cross-file checks (e.g. effort_ratings keys ⊆ loaded chapter list)
    are NOT enforced here; they belong to the loader.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug

    group_roster: dict[CanonicalStudentId, SegmentKey] = Field(
        ...,
        description="Maps each student ID to their demographic segment.",
    )
    unit_importance: dict[str, ImportanceLevel] = Field(
        ...,
        description="Maps chapter/unit label to its declared importance level.",
    )
    importance_weights: dict[ImportanceLevel, float] = Field(
        default_factory=lambda: {"상": 3.0, "중": 2.0, "하": 1.0},
        description="Numeric weight assigned to each importance level.",
    )
    gap_threshold: float = Field(
        default=0.6,
        description="Correct-rate below which a unit is considered a gap (0..1).",
    )
    baseline_segment: SegmentKey = Field(
        default="만학도",
        description="Segment used as the denominator baseline for gap scoring.",
    )
    low_discrimination_threshold: float = Field(
        default=0.2,
        description="Point-biserial below which an item is flagged low-discrimination.",
    )
    cognitive_cliff_drop: float = Field(
        default=0.15,
        description="Correct-rate drop between adjacent cognitive levels that triggers"
        " the 인지수준절벽 alignment flag.",
    )
    effort_ratings: dict[str, EffortLevel] = Field(
        default_factory=dict,
        description="Optional per-chapter effort rating; keys need not cover all chapters.",
    )

    # ------------------------------------------------------------------
    # Model validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _v1_gap_threshold_range(self) -> Self:
        """V1: gap_threshold must be in [0, 1]."""
        if not (0.0 <= self.gap_threshold <= 1.0):
            raise ValueError(f"V1: gap_threshold={self.gap_threshold!r} must be in [0, 1].")
        return self

    @model_validator(mode="after")
    def _v2_low_discrimination_non_negative(self) -> Self:
        """V2: low_discrimination_threshold must be >= 0."""
        if self.low_discrimination_threshold < 0:
            raise ValueError(
                f"V2: low_discrimination_threshold={self.low_discrimination_threshold!r}"
                " must be >= 0."
            )
        return self

    @model_validator(mode="after")
    def _v3_cognitive_cliff_non_negative(self) -> Self:
        """V3: cognitive_cliff_drop must be >= 0."""
        if self.cognitive_cliff_drop < 0:
            raise ValueError(
                f"V3: cognitive_cliff_drop={self.cognitive_cliff_drop!r} must be >= 0."
            )
        return self

    @model_validator(mode="after")
    def _v4_importance_weights_keys(self) -> Self:
        """V4: importance_weights keys must be exactly {상, 중, 하}."""
        actual = frozenset(self.importance_weights.keys())
        if actual != _IMPORTANCE_KEYS:
            raise ValueError(
                f"V4: importance_weights keys must be exactly {_IMPORTANCE_KEYS}; got {actual}."
            )
        return self


__all__ = ["RetroMesterConfig"]
