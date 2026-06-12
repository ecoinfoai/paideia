"""FormativeItemCandidate: short-answer formative assessment item (spec 009 §7).

Superset of the LMS formative 14-column row.  Compatible with
ExamPDFGenerator structure.  support_high is the leap axis: it bridges
high-achievers to the next concept (FR-014).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .._common import CourseSlug, SemesterCode
from .textbook_evidence import MaieuticaTextbookEvidence


class FormativeItemCandidate(BaseModel):
    """One LLM-generated formative assessment candidate, pre-adoption.

    Maps to the LMS formative 14-column layout (SC-003):
    - no / chapter_no → numeric cells
    - all other text columns → string cells

    ``support_high`` serves as the leap axis for high-achievers (FR-014).
    All content must stay within the chapter's textbook evidence scope
    (external knowledge prohibited, FR-002).
    """

    model_config = ConfigDict(extra="forbid")

    semester: SemesterCode
    course_slug: CourseSlug
    no: Annotated[int, Field(ge=1, description="Item number → LMS No. (numeric cell).")]
    chapter_no: int = Field(..., description="Chapter number → LMS Chapter (numeric cell).")
    topic: str = Field(..., description="Topic → LMS Topic.")
    question: str = Field(..., description="Question text → LMS Question.")
    limit: str = Field(..., description="Answer length guideline → LMS Limit (e.g. '200자 내외').")
    model_answer: str = Field(..., description="Model answer → LMS Model Answer.")
    purpose: str = Field(..., description="Assessment purpose → LMS Purpose.")
    keywords: list[str] = Field(
        default_factory=list,
        description="Key scoring keywords → LMS Keywords (serialised with separator).",
    )
    rubric_high: str = Field(..., description="High-achievement rubric criterion → LMS Rubric(High).")
    rubric_mid: str = Field(..., description="Mid-achievement rubric criterion → LMS Rubric(Mid).")
    rubric_low: str = Field(..., description="Low-achievement rubric criterion → LMS Rubric(Low).")
    support_high: str = Field(
        ...,
        description=(
            "Support plan for high achievers (leap axis — bridges to next concept, FR-014). "
            "→ LMS Support(High)."
        ),
    )
    support_mid: str = Field(..., description="Support plan for mid achievers → LMS Support(Mid).")
    support_low: str = Field(..., description="Support plan for low achievers → LMS Support(Low).")
    textbook_evidence: MaieuticaTextbookEvidence | None = Field(
        default=None,
        description="Textbook evidence reference (nested full-form only).",
    )
    review_note: str = Field(
        default="",
        description="Validation note (empty initially; filled after review).",
    )
    adoption_status: Literal["생성", "교수수정", "채택", "제외"] = Field(
        default="생성",
        description="Curation status.",
    )
