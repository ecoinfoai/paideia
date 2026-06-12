"""LeapExplanation: "one step further" explanation for students who answered correctly (spec 009 §6).

Nested in QuizItemCandidate.  The <=200-char length target is a SOFT goal
flagged by the parent QuizItemCandidate.explanation_length_ok; no hard
validator is applied here so that partial LLM output remains schema-valid
(FR-012).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .textbook_evidence import MaieuticaTextbookEvidence


class LeapExplanation(BaseModel):
    """Leap (도약) explanation bridging a correct answer to the next concept.

    Length <=200 chars is a soft goal; see parent QuizItemCandidate for the
    soft flag.  No hard length validator is applied here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(
        ...,
        description=(
            "Leap explanation body. <=200 chars is a soft target; violations are "
            "flagged on the parent QuizItemCandidate.explanation_length_ok."
        ),
    )
    textbook_evidence: MaieuticaTextbookEvidence | None = Field(
        default=None,
        description="Textbook grounding for the leap content (FR-012).",
    )
