"""QuizItemCandidate: 5-choice single-select quiz item + metadata (spec 009 §5).

Superset of the LMS quiz row.  Hard invariants are enforced at construction;
soft flags (option_length_ok, explanation_length_ok) are computed by the
caller and stored here without re-validation.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .._common import CourseSlug, SemesterCode
from .leap_explanation import LeapExplanation
from .textbook_evidence import MaieuticaTextbookEvidence


class QuizItemCandidate(BaseModel):
    """One LLM-generated quiz candidate, pre-adoption.

    Hard invariants enforced at construction:
    - V1: ``len(options) == 5``
    - V2: ``1 <= answer_no <= 5`` (via Field bounds)
    - V3: ``len(option_evidence) == 5``
    - V4: ``answer_explanation_combined == f"{wrong_explanation} ─ 도약 ─ {leap.text}"``

    Soft flags (stored by caller, not re-derived here):
    - ``option_length_ok``: each option 30–50 chars (incl. spaces).
    - ``explanation_length_ok``: wrong_explanation and leap.text each <=200 chars.

    Note: ``difficulty`` uses ``Literal["상","중","하"]`` — intentionally different
    from examen's ``"1_쉬움"/"2_보통"/"3_어려움"``; do not unify (spec 009 §5).

    Frozen: downstream stages update ``review_note`` / ``adoption_status`` via
    ``model_copy(update={...})`` (examen pattern), not in-place mutation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    item_no: Annotated[int, Field(ge=1, description="Item number → LMS 문제번호.")]
    week: int = Field(..., description="Week number → LMS 예상주차 (zero-padded text).")
    chapter_no: int = Field(..., description="Source chapter number.")
    chapter: str = Field(..., description="Source chapter display name.")
    section: str | None = Field(default=None, description="Section / subtopic.")
    key_concept: str | None = Field(default=None, description="Key concept (dedup key).")
    question_type: Literal["지식축적", "맥락통찰"] = Field(
        ...,
        description="Question type (semantic): 지식축적 or 맥락통찰.",
    )
    difficulty: Literal["상", "중", "하"] = Field(
        ...,
        description="Difficulty tag (R7). Intentionally different from examen's scale.",
    )
    stem_polarity: Literal["부정형", "긍정형"] = Field(
        ...,
        description="Stem polarity direction (FR-009).",
    )
    text: str = Field(..., description="Question stem → LMS 문제내용.")
    options: list[str] = Field(..., description="Answer choices 1–5 (len must be 5).")
    answer_no: Annotated[int, Field(ge=1, le=5)] = Field(
        ...,
        description="Correct option number 1–5 → LMS 답안 (text str(answer_no)).",
    )
    option_evidence: list[str] = Field(
        ...,
        description="Per-option textbook evidence strings (len must be 5).",
    )
    wrong_explanation: str = Field(
        ...,
        description=(
            "Explanation for students who answered incorrectly. "
            "<=200 chars is a soft target; see explanation_length_ok."
        ),
    )
    leap: LeapExplanation = Field(
        ...,
        description="Leap explanation for students who answered correctly (FR-012).",
    )
    textbook_evidence: MaieuticaTextbookEvidence | None = Field(
        default=None,
        description="Primary textbook evidence for this item.",
    )
    answer_explanation_combined: str = Field(
        ...,
        description=(
            "Combined answer explanation: '{wrong} ─ 도약 ─ {leap.text}'. "
            "→ LMS 답안설명 (FR-013, R2)."
        ),
    )
    option_length_ok: bool = Field(
        ...,
        description="True iff all options are 30–50 chars incl. spaces (FR-010, soft flag).",
    )
    explanation_length_ok: bool = Field(
        ...,
        description=(
            "True iff wrong_explanation and leap.text are each <=200 chars "
            "incl. spaces (FR-011, soft flag)."
        ),
    )
    duplicate_flag: bool = Field(
        default=False,
        description="True if flagged as duplicate or highly similar to another item.",
    )
    review_note: str = Field(
        default="",
        description="Validation note (empty initially; filled after 2nd-pass review, FR-018).",
    )
    adoption_status: Literal["생성", "교수수정", "채택", "제외"] = Field(
        default="생성",
        description="Curation status (FR-017).",
    )
    note: str | None = Field(default=None, description="Free-form note.")

    # ------------------------------------------------------------------
    # Model validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _v1_options_len(self) -> Self:
        """V1: options must have exactly 5 elements."""
        if len(self.options) != 5:
            raise ValueError(
                f"V1: len(options) == {len(self.options)}, must be 5."
            )
        return self

    @model_validator(mode="after")
    def _v3_option_evidence_len(self) -> Self:
        """V3: option_evidence must have exactly 5 elements."""
        if len(self.option_evidence) != 5:
            raise ValueError(
                f"V3: len(option_evidence) == {len(self.option_evidence)}, must be 5."
            )
        return self

    @model_validator(mode="after")
    def _v4_combined_form(self) -> Self:
        """V4: answer_explanation_combined must equal the canonical folded form."""
        expected = f"{self.wrong_explanation} ─ 도약 ─ {self.leap.text}"
        if self.answer_explanation_combined != expected:
            raise ValueError(
                "V4: answer_explanation_combined must equal "
                f"'{{wrong_explanation}} ─ 도약 ─ {{leap.text}}'. "
                f"Got: {self.answer_explanation_combined!r}"
            )
        return self
