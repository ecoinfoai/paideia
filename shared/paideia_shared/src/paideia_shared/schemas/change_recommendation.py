"""ChangeRecommendation (M3): prioritised instructional change recommendation.

Gold-layer schema. The recommendation engine selects the top-5 covered gaps
(rank 1-5) and passes remaining gaps through as uncovered (rank=None).
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode
from .retro_common import (
    CauseLabel,
    EffortLevel,
    ImportanceLevel,
    PriorityQuadrant,
    SegmentKey,
    ValidityVerdict,
)


class ChangeRecommendation(BaseModel):
    """One instructional change recommendation derived from a UnitGap.

    Invariants enforced at construction:
    - V1: ``is_covered is True  ⇒ rank is not None and 1 <= rank <= 5``
    - V2: ``is_covered is False ⇒ rank is None``
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    rank: int | None = Field(
        ...,
        description="Priority rank 1-5 among covered recommendations; None when uncovered.",
    )
    chapter: str = Field(..., description="Chapter label this recommendation targets.")
    target_cognitive_level: str = Field(
        ...,
        description="Bloom's-taxonomy cognitive level the prescription addresses.",
    )
    segment: SegmentKey
    cause_hypothesis: CauseLabel
    covered_n: int = Field(
        ...,
        ge=0,
        description="Number of segment students whose gap this recommendation addresses.",
    )
    covered_pct_segment: float = Field(
        ...,
        description="Fraction of segment covered (0..1).",
    )
    covered_pct_cohort: float = Field(
        ...,
        description="Fraction of cohort covered (0..1).",
    )
    unit_importance: ImportanceLevel
    weight: float = Field(
        ...,
        description="Numeric importance weight (mirrors UnitGap.weight).",
    )
    impact_score: float = Field(
        ...,
        description="Priority sort key (mirrors UnitGap.impact_score).",
    )
    effort_level: EffortLevel
    priority_quadrant: PriorityQuadrant
    prescription_key: str = Field(
        ...,
        description="Lookup key into the prescription catalogue (e.g. 'scaffold_concepts').",
    )
    cluster_vocab: str | None = Field(
        default=None,
        description="Cluster vocabulary label when the prescription targets a cluster.",
    )
    validity: ValidityVerdict
    is_covered: bool = Field(
        ...,
        description="True when this gap is assigned a concrete prescription (rank 1-5).",
    )

    # ------------------------------------------------------------------
    # Model validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _v1_covered_rank_consistency(self) -> Self:
        """V1/V2: rank ↔ is_covered consistency.

        - is_covered=True  ⇒ rank is not None and 1 <= rank <= 5
        - is_covered=False ⇒ rank is None
        """
        if self.is_covered:
            if self.rank is None or not (1 <= self.rank <= 5):
                raise ValueError(
                    f"V1: is_covered=True requires rank in [1,5]; got rank={self.rank!r}."
                )
        else:
            if self.rank is not None:
                raise ValueError(
                    f"V2: is_covered=False requires rank=None; got rank={self.rank!r}."
                )
        return self


__all__ = ["ChangeRecommendation"]
