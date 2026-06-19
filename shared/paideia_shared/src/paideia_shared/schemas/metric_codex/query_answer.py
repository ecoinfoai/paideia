"""EvidenceCitation and QueryAnswer: deterministic retrieval output contracts.

Silver-layer query result schemas for metric-codex US2 (spec 013).

Invariants enforced at construction:
- QA-V1: ``no_evidence is True`` ⇒ ``citations == []`` (no-fabrication guard).
- QA-V2: ``narrative is None`` ⟺ ``rendered_by is None`` (coherence guard).
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceCitation(BaseModel):
    """One cited evidence entry surfaced by deterministic retrieval.

    Attributes:
        key: Stable fact key from the source CodexEntry.
        value: Numeric or text value from the source CodexEntry.
        source_id: Provenance FK → SourceRecord.
        observed_at: ISO date of the learning event (None when unknown).
        layer: Data richness tier of the source entry.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    value: float | str
    source_id: str
    observed_at: str | None
    layer: Literal["minimal", "rich"]


class QueryAnswer(BaseModel):
    """Answer to a deterministic evidence query for one student.

    At pure-retrieval time, ``narrative`` and ``rendered_by`` are both ``None``.
    The generate/CLI layer (later units) sets them when it adds a narrative.

    Invariants:
    - QA-V1: ``no_evidence is True`` ⇒ ``citations == []``.
    - QA-V2: ``narrative is None`` ⟺ ``rendered_by is None``.

    Attributes:
        student_pseudonym: De-identified student label matching ``^S\\d{3,}$``.
        question_id: Canonical question id or ``"freeform"`` for ad-hoc queries.
        citations: Ordered evidence list (empty iff ``no_evidence`` is True).
        available_layers: Sorted distinct layers present in the student's whole codex.
        no_evidence: True when no entries matched the query filters.
        narrative: Human-readable summary produced by template or LLM (None at retrieval time).
        rendered_by: Which path produced the narrative; None iff narrative is None.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_pseudonym: str = Field(
        ...,
        pattern=r"^S\d{3,}$",
        description="De-identified student label, e.g. 'S001'.",
    )
    question_id: str
    citations: list[EvidenceCitation]
    available_layers: list[Literal["minimal", "rich"]]
    no_evidence: bool
    narrative: str | None = None
    rendered_by: Literal["template", "llm"] | None = None

    @model_validator(mode="after")
    def _qa_v1_no_fabrication(self) -> Self:
        """QA-V1: no_evidence=True requires an empty citations list."""
        if self.no_evidence and self.citations:
            raise ValueError(
                "QA-V1 violated: no_evidence is True but citations is non-empty "
                f"({len(self.citations)} citation(s)); no fabricated evidence allowed."
            )
        return self

    @model_validator(mode="after")
    def _qa_v2_narrative_rendered_by_coherence(self) -> Self:
        """QA-V2: narrative and rendered_by must both be set or both be None."""
        has_narrative = self.narrative is not None
        has_rendered_by = self.rendered_by is not None
        if has_narrative != has_rendered_by:
            raise ValueError(
                "QA-V2 violated: narrative and rendered_by must both be set or both be None; "
                f"got narrative={self.narrative!r}, rendered_by={self.rendered_by!r}."
            )
        return self


__all__ = ["EvidenceCitation", "QueryAnswer"]
