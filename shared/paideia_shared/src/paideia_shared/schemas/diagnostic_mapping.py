"""DiagnosticMappingConfig: Pydantic shape of the mapping YAML."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode


class MappingMetadata(BaseModel):
    """Top-level course identity and mapping version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    course_name_kr: str | None = None
    mapping_version: Annotated[int, Field(ge=1)] = 1


class MappingColumn(BaseModel):
    """One column-to-axis mapping entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Annotated[str, Field(min_length=1)]
    kind: Literal["identity", "likert", "multiselect", "freetext"]
    axis: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")] | None = None
    aggregate: Literal["mean", "sum"] | None = None
    partition_axis: bool = False

    @model_validator(mode="after")
    def v1_identity_no_axis(self) -> Self:
        """kind='identity' forbids axis/aggregate; non-identity requires axis."""
        if self.kind == "identity":
            if self.axis is not None or self.aggregate is not None:
                raise ValueError(
                    f"MappingColumn V1: kind='identity' forbids axis/aggregate "
                    f"(source={self.source!r})."
                )
        elif self.axis is None:
            raise ValueError(
                f"MappingColumn V1: kind={self.kind!r} requires axis "
                f"(source={self.source!r})."
            )
        return self

    @model_validator(mode="after")
    def v5_partition_axis_only_for_classifying_kinds(self) -> Self:
        """``partition_axis=True`` is incompatible with ``kind='freetext'``.

        Free-text responses are unsuitable as partition variables for the Phase E
        group-distribution report (Clarifications §4, FR-017). Likert and
        multiselect items remain valid partition sources; identity columns are
        excluded by V1 (no axis/aggregate, partition_axis=True is harmless but
        meaningless on identity rows).
        """
        if self.partition_axis and self.kind == "freetext":
            raise ValueError(
                f"MappingColumn V5: partition_axis=True is incompatible with "
                f"kind='freetext' (source={self.source!r})."
            )
        return self


class MappingAxes(BaseModel):
    """Required and optional axis key declarations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")]],
        Field(min_length=1),
    ]
    optional: list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")]] = Field(
        default_factory=list
    )


class DiagnosticMappingConfig(BaseModel):
    """Validated representation of a course-specific mapping YAML."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: MappingMetadata
    columns: Annotated[list[MappingColumn], Field(min_length=2)]
    axes: MappingAxes

    @model_validator(mode="after")
    def v2_exactly_one_identity(self) -> Self:
        """Exactly one columns entry must have kind='identity'."""
        identity_count = sum(1 for c in self.columns if c.kind == "identity")
        if identity_count != 1:
            raise ValueError(
                f"DiagnosticMappingConfig V2: exactly one column must have "
                f"kind='identity'; found {identity_count}."
            )
        return self

    @model_validator(mode="after")
    def v3_declared_axes_have_columns(self) -> Self:
        """Every declared axis (required ∪ optional) must be backed by ≥1 column."""
        column_axes: set[str] = {
            c.axis for c in self.columns if c.kind != "identity" and c.axis is not None
        }
        declared = set(self.axes.required) | set(self.axes.optional)
        missing = declared - column_axes
        if missing:
            raise ValueError(
                f"DiagnosticMappingConfig V3: declared axes have no mapping "
                f"columns: {sorted(missing)}."
            )
        return self

    @model_validator(mode="after")
    def v4_aggregate_consistent_per_axis(self) -> Self:
        """Same axis across multiple *scoring* columns requires identical non-null aggregate.

        ``freetext`` columns have ``aggregate=None`` by design (no score aggregation
        — the column carries raw text consumed by Phase D dictionary/LLM
        classification). They are exempt from this validator so that the
        spec-intended pattern of likert + freetext sharing one axis (e.g.
        anxiety likert items + Q62 freetext both ``axis="anxiety"``, per
        contracts/diagnostic_mapping_extension.md) does not raise spuriously.
        """
        from collections import defaultdict

        axis_aggregates: dict[str, list[str | None]] = defaultdict(list)
        for column in self.columns:
            if column.kind in ("identity", "freetext") or column.axis is None:
                continue
            axis_aggregates[column.axis].append(column.aggregate)
        for axis_key, aggregates in axis_aggregates.items():
            if len(aggregates) <= 1:
                continue
            unique_aggregates = set(aggregates)
            if None in unique_aggregates or len(unique_aggregates) > 1:
                raise ValueError(
                    f"DiagnosticMappingConfig V4: axis={axis_key!r} appears in "
                    f"{len(aggregates)} columns with inconsistent aggregate "
                    f"values {aggregates}; supply identical 'aggregate: mean|sum' "
                    f"on every column for the axis."
                )
        return self

    @model_validator(mode="after")
    def v6_axes_are_standard_paideia_vocabulary(self) -> Self:
        """All declared axes must belong to the paideia v0.1.0 standard vocabulary.

        Spec FR-AXIS-001 / Clarifications §2 fix the vocabulary at six keys:
        ``motivation``, ``anxiety``, ``self_efficacy``, ``interest``,
        ``prior_knowledge``, ``life_context``. Adding a new axis is a paideia
        minor-version bump and is rejected here so misconfigured mapping YAMLs
        cannot leak non-standard keys into downstream Silver outputs.
        """
        standard = {
            "motivation",
            "anxiety",
            "self_efficacy",
            "interest",
            "prior_knowledge",
            "life_context",
        }
        declared = set(self.axes.required) | set(self.axes.optional)
        non_standard = sorted(declared - standard)
        if non_standard:
            raise ValueError(
                f"DiagnosticMappingConfig V6: declared axes are outside paideia "
                f"standard vocabulary: {non_standard}. "
                f"Allowed: {sorted(standard)}. "
                f"Adding a new axis requires paideia minor version bump."
            )
        return self
