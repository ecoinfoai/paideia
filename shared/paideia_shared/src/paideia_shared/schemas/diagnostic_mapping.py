"""DiagnosticMappingConfig: Pydantic shape of the mapping YAML.

v0.1.1 deltas (constitution v1.1.0 + spec 003 FR-011/013):
- ``MappingColumn.kind`` Literal expands from 4 → 5 values (adds
  ``single_select``).
- ``MappingColumn.aggregate='mean'`` is now reserved for ``kind='likert'``;
  scoring on ``single_select`` / ``multiselect`` raises validation error.
- ``MappingColumn.ordinal_map: Optional[dict[str, int]]`` allows shared
  option-text→score tables to be reused via YAML anchor/alias.
- ``DiagnosticMappingConfig.v6_axes_are_standard_paideia_vocabulary`` now
  enforces the 8-key v1.1.0 ``StandardAxisKey`` vocabulary, with
  ``axes.required`` MUST equal the full 8-key set exactly (FR-013 strict).
- ``axes.optional`` MUST be a subset of
  ``AuxiliaryGroupKey ∪ FreetextAreaKey``.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import (
    STANDARD_AXIS_KEYS,
    AuxiliaryGroupKey,
    CourseSlug,
    FreetextAreaKey,
    SemesterCode,
)


class MappingMetadata(BaseModel):
    """Top-level course identity and mapping version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    course_name_kr: str | None = None
    mapping_version: Annotated[int, Field(ge=1)] = 1


class MappingColumn(BaseModel):
    """One column-to-axis mapping entry.

    v0.1.1: ``kind`` Literal expands to 5 values (adds ``single_select``);
    ``aggregate='mean'`` is reserved for ``kind='likert'`` only;
    optional ``ordinal_map`` carries the option-text → 1..7 conversion table
    used by Phase B scoring (allows YAML anchor/alias reuse for the three
    shared 7-point variants).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Annotated[str, Field(min_length=1)]
    kind: Literal["identity", "likert", "single_select", "multiselect", "freetext"]
    axis: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")] | None = None
    aggregate: Literal["mean", "sum"] | None = None
    partition_axis: bool = False
    ordinal_map: dict[str, int] | None = None

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
                f"MappingColumn V1: kind={self.kind!r} requires axis (source={self.source!r})."
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

    @model_validator(mode="after")
    def v7_aggregate_mean_only_for_likert(self) -> Self:
        """v0.1.1 FR-011: ``aggregate='mean'`` is reserved for ``kind='likert'``.

        Single-select / multiselect columns are auxiliary categorical groups —
        averaging them produces nonsensical scores. Identity columns reject
        aggregate at V1. Freetext columns may legitimately have aggregate=None
        (no scoring path), so this validator only triggers when aggregate IS
        ``'mean'`` AND kind is not ``'likert'``.
        """
        if self.aggregate == "mean" and self.kind != "likert":
            raise ValueError(
                f"MappingColumn V7: aggregate='mean' is only allowed on "
                f"kind='likert', got kind={self.kind!r} "
                f"(source={self.source!r}). Move the column to a non-scoring "
                f"auxiliary axis or change kind to 'likert' if it carries a "
                f"7-point ordinal scale."
            )
        return self

    @model_validator(mode="after")
    def v8_ordinal_map_only_for_likert(self) -> Self:
        """``ordinal_map`` is meaningful only on ``kind='likert'`` (data-model §2).

        Defining an ordinal_map on non-likert columns is operator error —
        single_select uses raw option labels, multiselect carries lists,
        freetext is unstructured. Reject at validation so misconfigured YAMLs
        do not silently lose the conversion table.
        """
        if self.ordinal_map is not None and self.kind != "likert":
            raise ValueError(
                f"MappingColumn V8: ordinal_map is only meaningful on "
                f"kind='likert', got kind={self.kind!r} "
                f"(source={self.source!r})."
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
        """All declared axes must belong to the paideia v0.1.1 vocabulary.

        Constitution v1.1.0 fixes the quantitative axis vocabulary at 8 keys
        (``StandardAxisKey``); auxiliary group keys (``AuxiliaryGroupKey``)
        and freetext area keys (``FreetextAreaKey``) extend it for non-scoring
        uses. ``axes.required`` MUST equal the full 8-key set exactly
        (FR-013 strict — neither superset nor subset is allowed); auxiliary
        and freetext keys belong on ``axes.optional`` only.

        Adding a new quantitative axis is a paideia minor-version bump per
        FR-AXIS-001.
        """
        required_set = set(self.axes.required)
        canonical = set(STANDARD_AXIS_KEYS)
        if required_set != canonical:
            missing = sorted(canonical - required_set)
            extra = sorted(required_set - canonical)
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing}")
            if extra:
                parts.append(f"extra={extra}")
            raise ValueError(
                f"DiagnosticMappingConfig V6: axes.required must equal the "
                f"8-key paideia v1.1.0 vocabulary exactly "
                f"({sorted(canonical)}). Diff: {', '.join(parts)}. "
                f"Adding a new quantitative axis requires a paideia "
                f"minor-version bump per FR-013/FR-AXIS-001."
            )

        # axes.optional MUST live in AuxiliaryGroupKey ∪ FreetextAreaKey only.
        optional_set = set(self.axes.optional)
        allowed_optional = set(_args_of(AuxiliaryGroupKey)) | set(_args_of(FreetextAreaKey))
        non_standard_optional = sorted(optional_set - allowed_optional)
        if non_standard_optional:
            raise ValueError(
                f"DiagnosticMappingConfig V6: axes.optional contains keys "
                f"outside AuxiliaryGroupKey ∪ FreetextAreaKey: "
                f"{non_standard_optional}. "
                f"Allowed optional keys: {sorted(allowed_optional)}."
            )
        return self


def _args_of(literal_alias: object) -> tuple[str, ...]:
    """Extract Literal members from a ``TypeAlias = Literal[...]``."""
    import typing

    return tuple(typing.get_args(literal_alias))
