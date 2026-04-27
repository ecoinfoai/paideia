"""FreetextAuditRow — per-token sentiment audit trail (M9 in v0.1.1 data-model).

One row per (student, freetext source, token). Written to silver
``freetext_audit.parquet`` so two runs can be compared character-by-character
(byte-equal) and so operators can inspect what the RoBERTa tokenizer
actually saw post-redaction.

Spec: 003-needs-map-v0-1-1/data-model.md §9 + spec FR-031 + research §R-12.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class FreetextAuditRow(BaseModel):
    """One row per (student, freetext source, token) — RoBERTa audit trail."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: Annotated[str, Field(pattern=r"^\d{10}$")]
    semester: SemesterCode
    course_slug: CourseSlug

    freetext_source: Literal["q61_anxiety", "q62_experience"]

    # Redacted text identity — student × freetext_source has 1 redacted text;
    # the sha256 + length pair groups all token rows belonging to that text.
    redacted_text_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]
    redacted_text_length: Annotated[int, Field(ge=0)]

    # Per-token fields (always populated)
    token_index: Annotated[int, Field(ge=0)]
    token_text: Annotated[str, Field(min_length=1)]
    token_id: Annotated[int, Field(ge=0)]
    char_start: Annotated[int, Field(ge=0)]
    char_end: Annotated[int, Field(ge=0)]

    # Model + tokenizer identity (constant across all tokens in a single run)
    model_id: Annotated[str, Field(min_length=1)]
    model_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]
    tokenizer_vocab_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]

    @model_validator(mode="after")
    def _char_offsets_within_text(self) -> "FreetextAuditRow":
        """char_start ≤ char_end ≤ redacted_text_length — invariant per data-model §9."""
        if self.char_start > self.char_end:
            raise ValueError(
                f"FreetextAuditRow: char_start({self.char_start}) > "
                f"char_end({self.char_end}) at token_index={self.token_index}."
            )
        if self.char_end > self.redacted_text_length:
            raise ValueError(
                f"FreetextAuditRow: char_end({self.char_end}) > "
                f"redacted_text_length({self.redacted_text_length}) at "
                f"token_index={self.token_index}."
            )
        return self
