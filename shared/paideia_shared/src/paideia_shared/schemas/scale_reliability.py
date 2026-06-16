"""ScaleReliabilityRow + ScaleReliabilityReport (M3 in data-model.md).

Phase A output schema. One row per declared standard axis carries the
Cronbach α value (or a typed label when α is not computable) plus an
operational warning flag (FR-005: α < 0.7).

Spec FR mapping: FR-004 (α + single/multi-item branching), FR-005 (α < 0.7
operational warning).
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode, StandardAxisKey

ReliabilityLabel = Literal["high", "medium", "low", "N/A — single/double item"]
"""v0.1.1 threshold-based reliability tag (data-model.md §5).

Mapping (T012, FR-005 + spec §SC-002):
- α ≥ 0.80 → 'high'
- 0.70 ≤ α < 0.80 → 'medium'
- α < 0.70 → 'low' (operational_warning=True)
- n_items in {1, 2} or α not computable → 'N/A — single/double item'
"""


class ScaleReliabilityRow(BaseModel):
    """Per-axis α + label + operational-warning flag.

    v0.1.1 retains the v0.1.0 ``label`` discriminator (computed / single_item /
    no_items / not_applicable) for state machine validation, and adds a new
    threshold-based ``reliability_label`` consumed by the v0.1.1 axis_summary
    export and the per-card reliability annotation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    axis_key: StandardAxisKey
    n_items: Annotated[int, Field(ge=0)]
    cronbach_alpha: float | None
    label: Literal["computed", "single_item", "no_items", "not_applicable"]
    operational_warning: bool
    reliability_label: ReliabilityLabel | None = None

    @model_validator(mode="after")
    def v1_label_matches_n_items_and_alpha(self) -> Self:
        """label, n_items, and cronbach_alpha must agree.

        - n_items == 0 → label='no_items', alpha=None
        - n_items in {1, 2} → label='single_item', alpha=None
        - n_items >= 3 → label in {'computed', 'not_applicable'};
          alpha float when 'computed', None when 'not_applicable'
        """
        if self.n_items == 0:
            if self.label != "no_items":
                raise ValueError(
                    f"ScaleReliabilityRow V1: n_items=0 requires label='no_items', "
                    f"got label={self.label!r} (axis_key={self.axis_key!r})."
                )
            if self.cronbach_alpha is not None:
                raise ValueError(
                    f"ScaleReliabilityRow V1: label='no_items' requires alpha=None "
                    f"(axis_key={self.axis_key!r})."
                )
        elif self.n_items < 3:
            if self.label != "single_item":
                raise ValueError(
                    f"ScaleReliabilityRow V1: n_items={self.n_items} (<3) requires "
                    f"label='single_item', got label={self.label!r} "
                    f"(axis_key={self.axis_key!r})."
                )
            if self.cronbach_alpha is not None:
                raise ValueError(
                    f"ScaleReliabilityRow V1: label='single_item' requires alpha=None "
                    f"(axis_key={self.axis_key!r})."
                )
        else:
            if self.label == "computed" and self.cronbach_alpha is None:
                raise ValueError(
                    f"ScaleReliabilityRow V1: label='computed' requires alpha float "
                    f"(axis_key={self.axis_key!r})."
                )
            if self.label == "not_applicable" and self.cronbach_alpha is not None:
                raise ValueError(
                    f"ScaleReliabilityRow V1: label='not_applicable' requires alpha=None "
                    f"(axis_key={self.axis_key!r})."
                )
            if self.label in ("no_items", "single_item"):
                raise ValueError(
                    f"ScaleReliabilityRow V1: n_items={self.n_items} (>=3) cannot have "
                    f"label={self.label!r} (axis_key={self.axis_key!r})."
                )
        return self

    @model_validator(mode="after")
    def v2_operational_warning_only_when_computed_below_threshold(self) -> Self:
        """``operational_warning=True`` requires label='computed' AND alpha < 0.7.

        Per FR-005: α < 0.7 axes carry the warning. Axes that could not compute
        an α at all (single_item / no_items / not_applicable) cannot carry an
        operational warning — the absence of α is itself the signal.
        """
        if self.operational_warning:
            if self.label != "computed":
                raise ValueError(
                    f"ScaleReliabilityRow V2: operational_warning=True requires "
                    f"label='computed', got label={self.label!r} "
                    f"(axis_key={self.axis_key!r})."
                )
            if self.cronbach_alpha is None or self.cronbach_alpha >= 0.7:
                raise ValueError(
                    f"ScaleReliabilityRow V2: operational_warning=True requires "
                    f"alpha < 0.7, got alpha={self.cronbach_alpha} "
                    f"(axis_key={self.axis_key!r})."
                )
        return self


class ScaleReliabilityReport(BaseModel):
    """All Phase A rows + run identity. Sidecar in NeedsMapManifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: Annotated[list[ScaleReliabilityRow], Field(min_length=0)]
    semester: SemesterCode
    course_slug: CourseSlug
    module_version: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def v1_one_row_per_declared_axis(self) -> Self:
        """Same axis_key may appear at most once."""
        keys = [r.axis_key for r in self.rows]
        if len(keys) != len(set(keys)):
            seen: set[str] = set()
            duplicates: list[str] = []
            for k in keys:
                if k in seen:
                    duplicates.append(k)
                seen.add(k)
            raise ValueError(
                f"ScaleReliabilityReport V1: duplicate axis_key entries: {sorted(set(duplicates))}."
            )
        return self
