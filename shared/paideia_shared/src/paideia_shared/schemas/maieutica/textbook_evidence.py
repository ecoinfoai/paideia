"""MaieuticaTextbookEvidence: textbook passage reference for maieutica (spec 009 §4).

Nested in QuizItemCandidate, FormativeItemCandidate, and LeapExplanation.
Groundedness authority: chunk ID + original character range (FR-003).

The examen module has its own TextbookEvidence in exam_item_draft.py;
this model is the maieutica-specific variant with chunk_id and char offsets.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MaieuticaTextbookEvidence(BaseModel):
    """Textbook passage reference supporting a maieutica candidate item.

    Invariants enforced at construction:
    - V1: ``char_end >= char_start`` when both are present.
    - V2: ``status == '확인'`` requires ``chunk_id`` AND
      (``found_text`` OR both ``char_start``/``char_end``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str | None = Field(
        default=None,
        description="Deterministic ID of the source TextbookChunk.",
    )
    source_file: str = Field(
        ...,
        description="Source textbook filename (authority).",
    )
    char_start: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        description="Character offset start in the source text (0-based).",
    )
    char_end: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        description="Character offset end; must be >= char_start when both present.",
    )
    line: int | None = Field(
        default=None,
        description="Line number in the source text (auxiliary, examen-compatible).",
    )
    found_text: str | None = Field(
        default=None,
        description="Exact text fragment found via search.",
    )
    search_term: str | None = Field(
        default=None,
        description="Key search term used for answer-point determination.",
    )
    status: Literal["확인", "미확인"] = Field(
        ...,
        description="'확인' if directly verified; '미확인' if verification failed (FR-003).",
    )

    @model_validator(mode="after")
    def _v1_char_range_order(self) -> Self:
        """V1: char_end must be >= char_start when both are present."""
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError(
                f"V1: char_end ({self.char_end}) must be >= char_start ({self.char_start})."
            )
        return self

    @model_validator(mode="after")
    def _v2_confirmed_requires_evidence(self) -> Self:
        """V2: status='확인' requires chunk_id AND (found_text OR char range)."""
        if self.status != "확인":
            return self
        if not self.chunk_id:
            raise ValueError(
                "V2: status='확인' requires chunk_id to be set."
            )
        has_found_text = bool(self.found_text)
        has_char_range = self.char_start is not None and self.char_end is not None
        if not has_found_text and not has_char_range:
            raise ValueError(
                "V2: status='확인' requires found_text or char_start/char_end to be set."
            )
        return self
