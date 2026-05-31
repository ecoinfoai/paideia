"""ExamItemDraft + TextbookEvidence: LLM-generated exam item (Gold, spec 008).

ExamItemDraft is the superset of immersio's ExamItem; it carries all metadata
produced by the generator and consumed by the verify step before adoption.

Text-length constraints (wrong/leap 270~330자, intent 40~60자) are NOT
enforced here so that partial drafts produced mid-generation remain
schema-valid.  Length validation happens at the verify/generate stage.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode


class TextbookEvidence(BaseModel):
    """Textbook passage reference supporting an ExamItemDraft.

    Nested in ExamItemDraft.  May be None for formative/quiz-sourced items.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_file: str
    line: int | None = None
    found_text: str | None = None
    status: Literal["확인", "미확인"]
    search_term: str | None = None


class ExamItemDraft(BaseModel):
    """One LLM-generated exam question, pre-adoption.

    Invariants enforced at construction:
    - ``1 <= answer_no <= 5`` (via Field bounds)
    - V1: ``len(options) == 5``
    - V2: ``len(distractor_rationale) == 5``

    Text-length constraints (wrong_explanation / leap_explanation 270~330자,
    intent 40~60자) are documented only here; they are enforced by the
    verify stage (ExamItemVerifier) so that partial drafts remain valid.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    item_no: Annotated[int, Field(ge=1)]
    source: Literal["textbook", "formative", "quiz"]
    source_ref: str | None = None
    chapter: str
    chapter_no: int
    section: str | None = None
    week: int | None = None
    key_concept: str | None = None
    is_emphasized: bool | None = None
    emphasis_class_count: Annotated[int | None, Field(ge=0, le=4)] = None
    question_type: Literal["지식축적", "맥락통찰"]
    bloom: (
        Literal[
            "knowledge",
            "comprehension",
            "application",
            "analysis",
            "synthesis",
            "evaluation",
        ]
        | None
    ) = None
    difficulty: Literal["1_쉬움", "2_보통", "3_어려움"]
    stem_polarity: Literal["부정형", "긍정형"]
    text: str
    options: list[str]
    answer_no: Annotated[int, Field(ge=1, le=5, description="정답 보기 번호 (1~5)")]
    distractor_rationale: list[str]
    wrong_explanation: str = Field(
        ...,
        description="오답 설명 (틀린 학생용). 길이 270~330자는 verify 단계 검증.",
    )
    leap_explanation: str = Field(
        ...,
        description="도약 설명 (맞힌 학생용). 길이 270~330자는 verify 단계 검증.",
    )
    textbook_evidence: TextbookEvidence | None = None
    intent: str = Field(
        ...,
        description="출제 의도. 길이 40~60자는 verify 단계 검증.",
    )
    option_length_ok: bool = Field(
        ...,
        description="보기 글자수 검증 (번호 포함 30~40자 전부 충족).",
    )
    duplicate_flag: bool = False
    review_note: str = ""
    adoption_status: Literal["생성", "교수수정", "채택", "제외"] = "생성"
    note: str | None = None

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
    def _v2_distractor_rationale_len(self) -> Self:
        """V2: distractor_rationale must have exactly 5 elements."""
        if len(self.distractor_rationale) != 5:
            raise ValueError(
                f"V2: len(distractor_rationale) == {len(self.distractor_rationale)}, must be 5."
            )
        return self
