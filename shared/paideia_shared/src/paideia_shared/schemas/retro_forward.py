"""Forward-planning schemas for retro-mester CQI cycle (M6).

Two models:
- ``ImprovementLedgerEntry``: one actionable commitment from this year's retro
  with a measurable target and baseline.
- ``BaselineSnapshotRow``: one per-segment/chapter/cognitive-level correct-rate
  row that forms the baseline for next-year comparison.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode
from .retro_common import SegmentKey


class ImprovementLedgerEntry(BaseModel):
    """One committed improvement action from the retro-mester planning output.

    Attributes:
        entry_id: Stable unique identifier for this ledger entry (e.g. UUID or
            slug). Used to cross-reference next-year retro verification.
        metric: The observable metric that will be measured (e.g.
            'chapter_correct_rate').
        baseline_value: This semester's observed value for the metric.
        target_value: Next-semester target value.
        measure_at: When / how the target will be measured (e.g. '2026-2 기말').
        created_for_year: Academic year this commitment is intended for
            (e.g. '2026-2').
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str = Field(
        ...,
        description="Stable unique identifier for this ledger entry.",
    )
    semester: SemesterCode
    course_slug: CourseSlug
    chapter: str = Field(
        ...,
        description="Chapter label this improvement targets.",
    )
    target_cognitive_level: str = Field(
        ...,
        description="Bloom's-taxonomy level the improvement action targets.",
    )
    segment: SegmentKey
    metric: str = Field(
        ...,
        description="Observable metric name (e.g. 'chapter_correct_rate').",
    )
    baseline_value: float = Field(
        ...,
        description="This semester's observed value for the metric.",
    )
    target_value: float = Field(
        ...,
        description="Next-semester target value for the metric.",
    )
    cluster_vocab: str | None = Field(
        default=None,
        description="Cluster vocabulary label when the target is cluster-specific.",
    )
    measure_at: str = Field(
        ...,
        description="When and how the target will be verified (e.g. '2026-2 기말').",
    )
    created_for_year: str = Field(
        ...,
        description="Academic year this commitment is intended for (e.g. '2026-2').",
    )


class BaselineSnapshotRow(BaseModel):
    """One row in the baseline snapshot used for next-year comparison.

    Emitted alongside ImprovementLedgerEntry rows so next year's retro-mester
    can compute improvement deltas without re-reading raw silver files.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    segment: SegmentKey
    chapter: str = Field(..., description="Chapter label.")
    cognitive_level: str = Field(
        ...,
        description="Bloom's-taxonomy level (e.g. '기억', '이해', '적용').",
    )
    correct_rate: float = Field(
        ...,
        description="Segment mean correct rate for this chapter × cognitive level (0..1).",
    )
    n: int = Field(
        ...,
        ge=0,
        description="Number of students with valid data for this cell.",
    )


__all__ = ["ImprovementLedgerEntry", "BaselineSnapshotRow"]
