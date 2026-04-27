"""FreeTextRow (M6).

Phase D output schema. One row per (student, freetext item) carries the
matched dictionary categories + match source + original length. The original
text body is NOT stored — only its character length, for FR-PII-002 hygiene.

Spec FR mapping: FR-014 (dictionary classification), FR-015 (LLM fallback for
unmatched), FR-016 (5-source enum + raw_length).
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CanonicalStudentId

MatchSource = Literal[
    "dictionary",
    "llm",
    "llm_fallback",
    "no_response",
    "uncategorized",
]


class FreeTextRow(BaseModel):
    """One classified free-text response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    item_id: Annotated[str, Field(min_length=1)]
    matched_categories: list[Annotated[str, Field(min_length=1)]]
    match_source: MatchSource
    raw_length: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def v1_no_response_implies_empty_matches(self) -> Self:
        if self.match_source == "no_response" and self.matched_categories:
            raise ValueError(
                f"FreeTextRow V1: match_source='no_response' must have empty "
                f"matched_categories (student_id={self.student_id}, "
                f"item_id={self.item_id})."
            )
        return self
