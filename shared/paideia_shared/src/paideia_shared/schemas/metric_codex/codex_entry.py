"""CodexEntry: one provenance-tagged fact/text snippet for one student.

Silver-layer schema. Represents a single measurable or categorical observation
tied to a student, a source, and a stable fact key. The combination of
(student_id, source_id, entry_kind, key, item_ref) is the natural key used for
idempotency by downstream pipeline stages.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .._common import CanonicalStudentId, SemesterCode


class EntryKind(StrEnum):
    """Closed vocabulary of metric entry kinds.

    Values are stable across pipeline versions; adding a new kind is a
    paideia minor-version bump.
    """

    score_total = "score_total"
    score_percent = "score_percent"
    attendance = "attendance"
    percentile_section = "percentile_section"
    percentile_cohort = "percentile_cohort"
    z_score = "z_score"
    domain_correct_rate = "domain_correct_rate"
    item_correct = "item_correct"
    axis_score_z = "axis_score_z"
    freetext_category = "freetext_category"
    cluster_label = "cluster_label"


_MINIMAL_KINDS: frozenset[EntryKind] = frozenset(
    {EntryKind.score_total, EntryKind.score_percent, EntryKind.attendance}
)
"""Entry kinds permitted on the ``minimal`` data layer (V3 guard)."""


class CodexEntry(BaseModel):
    """One provenance-tagged fact or text snippet for one student.

    Natural key (idempotency): ``(student_id, source_id, entry_kind, key, item_ref)``.
    Used by the Silver persistence stage to deduplicate on re-ingestion.

    Invariants enforced at construction:
    - V1: exactly one of ``value_num`` / ``value_text`` is non-None.
    - V2: ``item_ref is not None`` ⇒ ``entry_kind == EntryKind.item_correct``.
    - V3: ``layer == "minimal"`` ⇒ ``entry_kind ∈ {score_total, score_percent, attendance}``.

    Attributes:
        student_id: 10-digit canonical student ID.
        semester: Academic semester code (e.g. ``"2026-1"``).
        cohort_year: Enrollment year (2000–2100).
        layer: Data richness tier — ``"minimal"`` (3 kinds only) or ``"rich"`` (all kinds).
        entry_kind: Stable metric vocabulary member.
        domain: Chapter/단원/axis label when applicable; ``None`` for totals.
        item_ref: Question number for per-item entries; ``None`` otherwise.
        key: Stable fact key (e.g. ``"score_total"``, ``"chapter_correct_rate:순환"``).
        value_num: Numeric value; XOR with ``value_text``.
        value_text: Redacted/categorized free-text value; XOR with ``value_num``.
        source_id: Foreign key → SourceRecord.
        observed_at: ISO date of the learning event when known (e.g. ``"2026-06-01"``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    semester: SemesterCode
    cohort_year: int = Field(ge=2000, le=2100, description="Enrollment year.")
    layer: Literal["minimal", "rich"]
    entry_kind: EntryKind
    domain: str | None = None
    item_ref: str | None = None
    key: str = Field(..., description="Stable fact key (e.g. 'score_total', 'axis_z:motivation').")
    value_num: float | None = None
    value_text: str | None = None
    source_id: str = Field(..., description="FK → SourceRecord.source_id.")
    observed_at: str | None = Field(
        default=None,
        description="ISO date of the learning event (e.g. '2026-06-01').",
    )

    @model_validator(mode="after")
    def _v1_value_xor(self) -> Self:
        """V1: exactly one of value_num / value_text must be non-None."""
        has_num = self.value_num is not None
        has_text = self.value_text is not None
        if has_num == has_text:
            raise ValueError(
                "exactly one of value_num / value_text must be non-None; "
                f"got value_num={self.value_num!r}, value_text={self.value_text!r}."
            )
        return self

    @model_validator(mode="after")
    def _v2_item_ref_implies_item_correct(self) -> Self:
        """V2: item_ref is not None => entry_kind == EntryKind.item_correct."""
        if self.item_ref is not None and self.entry_kind != EntryKind.item_correct:
            raise ValueError(
                f"item_ref={self.item_ref!r} is only valid when "
                f"entry_kind == 'item_correct'; got {self.entry_kind!r}."
            )
        return self

    @model_validator(mode="after")
    def _v3_minimal_layer_kind(self) -> Self:
        """V3: layer == 'minimal' restricts entry_kind to score_total/score_percent/attendance."""
        if self.layer == "minimal" and self.entry_kind not in _MINIMAL_KINDS:
            raise ValueError(
                f"minimal layer only allows entry_kind in "
                f"{sorted(k.value for k in _MINIMAL_KINDS)}; got {self.entry_kind!r}."
            )
        return self


__all__ = ["CodexEntry", "EntryKind"]
