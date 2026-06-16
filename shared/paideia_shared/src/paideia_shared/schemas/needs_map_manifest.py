"""Sidecar manifest for needs-map runs (M7 in data-model.md).

Pydantic v2 schema with the same ``extra='forbid'`` + ``frozen=True`` discipline as
the rest of ``paideia_shared.schemas``. Written alongside both the Silver and Gold
output trees so audit trail survives directory moves.

v0.1.1 deltas (T017, contracts/manifest.md):
- ``schema_version`` defaults to '1.1.0' (was '1.0.0' implicit).
- New sub-models: ``FontResolutionInfo``, ``SentimentRunInfo``,
  ``NewOutputsInfo``, ``VocabularyInfo`` — surface the v0.1.1 cross-cutting
  concerns (Korean font fail-fast, RoBERTa sentiment, new exports + manual,
  vocabulary audit).
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import (
    STANDARD_AXIS_KEYS,
    AuxiliaryGroupKey,
    CanonicalStudentId,
    CourseSlug,
    FreetextAreaKey,
    OutputKey,
    SemesterCode,
    StandardAxisKey,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_ISO8601_UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


class FontResolutionInfo(BaseModel):
    """Provenance of the resolved Korean font paths (v0.1.1, T017 + T026).

    Either fc-match or env-var override resolves NanumGothic Regular + Bold
    at pipeline entry. Recorded so two runs can be compared byte-for-byte
    once font sha256 fingerprints are pinned (FR-035).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    regular_path: Annotated[str, Field(min_length=1)]
    bold_path: Annotated[str, Field(min_length=1)]
    regular_source: Literal["fc-match", "env-var-PAIDEIA_KR_FONT_PATH"]
    bold_source: Literal["fc-match", "env-var-PAIDEIA_KR_FONT_BOLD_PATH"]
    regular_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)] | None = None
    bold_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)] | None = None


class SentimentRunInfo(BaseModel):
    """RoBERTa sentiment phase accounting (v0.1.1 US6, T017 + T061).

    ``enabled=False`` represents the fallback branch (CLI ``--no-roberta``,
    torch missing, or model unavailable). The ``fallback_reason`` enum
    distinguishes those three causes so operators can tell why sentiment
    fields are missing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    model_id: Annotated[str, Field(min_length=1)] | None = None
    model_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)] | None = None
    tokenizer_vocab_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)] | None = None
    negative_label_subset_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)] | None = None
    n_attempted: Annotated[int, Field(ge=0)] = 0
    n_succeeded: Annotated[int, Field(ge=0)] = 0
    n_fallback: Annotated[int, Field(ge=0)] = 0
    fallback_reason: Literal["torch-unavailable", "model-unavailable", "cli-disabled"] | None = None

    @model_validator(mode="after")
    def v1_counts_consistent(self) -> Self:
        """succeeded + fallback ≤ attempted; enabled iff model_id is set."""
        if self.n_succeeded + self.n_fallback > self.n_attempted:
            raise ValueError(
                f"SentimentRunInfo V1: n_succeeded({self.n_succeeded}) + "
                f"n_fallback({self.n_fallback}) > n_attempted({self.n_attempted})."
            )
        if self.enabled and self.model_id is None:
            raise ValueError("SentimentRunInfo V1: enabled=True requires model_id to be set.")
        if not self.enabled and self.model_id is not None:
            raise ValueError(
                "SentimentRunInfo V1: enabled=False requires model_id=None "
                "(fallback path; no model loaded)."
            )
        if not self.enabled and self.fallback_reason is None:
            raise ValueError(
                "SentimentRunInfo V1: enabled=False requires fallback_reason "
                "to be set (one of 'torch-unavailable', 'model-unavailable', "
                "'cli-disabled')."
            )
        return self


class NewOutputsInfo(BaseModel):
    """Paths for the v0.1.1 new exports + manual + sentiment audit (T017)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    factor_scores_long_csv: Annotated[str, Field(min_length=1)]
    factor_scores_long_yaml: Annotated[str, Field(min_length=1)]
    axis_summary_csv: Annotated[str, Field(min_length=1)]
    axis_summary_yaml: Annotated[str, Field(min_length=1)]
    manual_pdf: Annotated[str, Field(min_length=1)]
    freetext_audit_parquet: Annotated[str, Field(min_length=1)]


class VocabularyInfo(BaseModel):
    """Cross-module vocabulary audit (T017 + contracts/manifest.md §vocabulary).

    Allows downstream modules / external auditors to verify that a given
    needs-map silver/gold output was produced under the expected
    constitution + axis/kind sets without re-deriving them from the schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    constitution_version: Annotated[str, Field(min_length=1)] = "1.1.0"
    axes: list[StandardAxisKey] = Field(default_factory=lambda: list(STANDARD_AXIS_KEYS))
    auxiliary_groups: list[AuxiliaryGroupKey | FreetextAreaKey] = Field(
        default_factory=lambda: [
            "prior_readiness",
            "interest_topics",
            "categorical_intent",
            "anxiety_freetext",
            "experience_freetext",
        ]
    )
    column_kinds: list[
        Literal["identity", "likert", "single_select", "multiselect", "freetext"]
    ] = Field(
        default_factory=lambda: [
            "identity",
            "likert",
            "single_select",
            "multiselect",
            "freetext",
        ]
    )


class NeedsMapInput(BaseModel):
    """Input fingerprint sub-model: paths + sha256 hashes for every input artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    diagnostic_response_path: Annotated[str, Field(min_length=1)]
    diagnostic_response_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]
    student_master_path: Annotated[str, Field(min_length=1)]
    student_master_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]
    diagnostic_mapping_path: Annotated[str, Field(min_length=1)]
    diagnostic_mapping_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]
    keyword_dictionary_path: Annotated[str, Field(min_length=1)] | None = None
    keyword_dictionary_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)] | None = None
    missing_policy_source: dict[StandardAxisKey, Literal["yaml", "default"]] = Field(
        default_factory=dict,
        description=(
            "Per-axis provenance flag for the missing-data policy actually applied. "
            "'yaml' = explicit value from mapping YAML; 'default' = code-side default "
            "applied because the YAML omitted it (Phase 2 design alignment §3.5; "
            "adversary H-1 mitigation). Empty dict means no axes were processed yet."
        ),
    )


class LLMCallStat(BaseModel):
    """Per-site LLM call accounting for FR-LLM-002 traceability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    site: Literal["cluster_naming", "free_text", "coaching", "report_tone"]
    attempted: Annotated[int, Field(ge=0)]
    succeeded: Annotated[int, Field(ge=0)]
    fallback: Annotated[int, Field(ge=0)]
    failure_kinds: dict[Literal["timeout", "rate_limit", "auth", "pii_block", "other"], int] = (
        Field(default_factory=dict)
    )
    failure_student_ids: list[CanonicalStudentId] = Field(default_factory=list)

    @model_validator(mode="after")
    def v1_counts_consistent(self) -> Self:
        """attempted ≥ succeeded + fallback (some attempts may still be in-flight)."""
        if self.succeeded + self.fallback > self.attempted:
            raise ValueError(
                f"LLMCallStat V1: succeeded({self.succeeded}) + fallback({self.fallback}) "
                f"> attempted({self.attempted}) for site={self.site!r}."
            )
        for kind, count in self.failure_kinds.items():
            if count < 0:
                raise ValueError(f"LLMCallStat V1: failure_kinds[{kind!r}]={count} must be ≥ 0.")
        return self


class NeedsMapPhaseRowCount(BaseModel):
    """Per-phase row counter for the manifest's ``rows_per_phase`` summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: Literal["A", "B", "C", "D", "E", "F"]
    rows_written: Annotated[int, Field(ge=0)]


class NeedsMapManifest(BaseModel):
    """Sidecar manifest written next to Silver and Gold outputs (FR-023, SC-007/008).

    Captures input fingerprints, axis coverage, phase row counts, LLM call statistics,
    archival pointer, and operational warnings so a re-run can be reasoned about
    without re-loading the parquet shards.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Annotated[str, Field(min_length=1)] = "1.1.0"

    semester: SemesterCode
    course_slug: CourseSlug
    output_key: OutputKey
    module_version: Annotated[str, Field(min_length=1)]
    created_at_utc: Annotated[str, Field(pattern=_ISO8601_UTC_PATTERN)]

    inputs: NeedsMapInput
    standard_axes_used: list[StandardAxisKey]
    standard_axes_skipped: list[StandardAxisKey]
    phases_executed: list[Literal["A", "B", "C", "D", "E", "F"]]
    rows_per_phase: list[NeedsMapPhaseRowCount]

    cluster_k_used: Annotated[int, Field(ge=1, le=6)] | None = None
    cluster_silhouette_used: float | None = None
    free_text_dictionary_match_rate: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    dictionary_language_mismatch_warning: bool = False
    weak_structure_warning: bool = False

    llm_provider: Annotated[str, Field(min_length=1)] | None = None
    llm_model: Annotated[str, Field(min_length=1)] | None = None
    llm_calls: list[LLMCallStat] = Field(default_factory=list)
    pii_redaction_validated: bool

    previous_run_archive_path: Annotated[str, Field(min_length=1)] | None = None
    warnings: list[str] = Field(default_factory=list)
    unrecognized_inputs: list[str] = Field(default_factory=list)

    # v0.1.1 cross-cutting concerns (T017). All four are nullable so that
    # partial pipelines (Phase A-only smoke runs) can still emit a valid
    # manifest without populating sentiment/exports/manual.
    font_resolution: FontResolutionInfo | None = None
    sentiment: SentimentRunInfo | None = None
    new_outputs: NewOutputsInfo | None = None
    vocabulary: VocabularyInfo | None = None

    @model_validator(mode="after")
    def v1_output_key_matches_semester_and_course(self) -> Self:
        expected = f"{self.semester}-{self.course_slug}"
        if self.output_key != expected:
            raise ValueError(
                f"NeedsMapManifest V1: output_key={self.output_key!r} does not match "
                f"semester+course slug {expected!r}."
            )
        return self

    @model_validator(mode="after")
    def v2_axis_partition_disjoint(self) -> Self:
        """``standard_axes_used`` and ``standard_axes_skipped`` must not overlap."""
        used = set(self.standard_axes_used)
        skipped = set(self.standard_axes_skipped)
        overlap = sorted(used & skipped)
        if overlap:
            raise ValueError(
                f"NeedsMapManifest V2: axes appear in both used and skipped: {overlap}."
            )
        return self

    @model_validator(mode="after")
    def v3_llm_sites_unique(self) -> Self:
        seen: set[str] = set()
        for stat in self.llm_calls:
            if stat.site in seen:
                raise ValueError(f"NeedsMapManifest V3: duplicate llm_calls site={stat.site!r}.")
            seen.add(stat.site)
        return self

    @model_validator(mode="after")
    def v4_phase_rowcounts_unique(self) -> Self:
        seen: set[str] = set()
        for entry in self.rows_per_phase:
            if entry.phase in seen:
                raise ValueError(
                    f"NeedsMapManifest V4: duplicate rows_per_phase phase={entry.phase!r}."
                )
            seen.add(entry.phase)
        return self
