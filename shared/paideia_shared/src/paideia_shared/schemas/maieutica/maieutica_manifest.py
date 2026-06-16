"""MaieuticaManifest: Gold-layer artefact manifest for one maieutica run (spec 009 §8).

Written once per ``paideia maieutica generate`` invocation.  ``generated_at``
is intentionally non-deterministic (wall-clock time) — the only maieutica
output allowed to carry a timestamp (R11).

Silver provenance (input_hashes / config_ids) covers the run unit per
constitution §V; no separate Silver manifest is emitted.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .._common import CourseSlug, SemesterCode


class MaieuticaManifest(BaseModel):
    """Provenance and quality summary for one maieutica generation run.

    ``answer_no_distribution`` keys are ints (1–5) matching the LMS answer_no
    contract.  ``stem_polarity_breakdown`` / ``difficulty_breakdown`` /
    ``groundedness`` keys are string literals defined by the respective enums;
    they are typed as ``dict[str, int]`` to avoid coupling this manifest to
    future enum extensions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    week: int = Field(..., description="Target week number.")
    chapter_no: int = Field(..., description="Target chapter number.")
    chapter: str = Field(..., description="Chapter display name.")
    input_hashes: dict[str, str] = Field(
        ...,
        description="Bronze input file hashes (filename→SHA-256).",
    )
    config_ids: dict[str, str] = Field(
        ...,
        description="generation_spec / curriculum_map / asset identifiers (SHA-256).",
    )
    generated_at: str = Field(
        ...,
        description="Generation timestamp (non-deterministic — manifest only, R11).",
    )
    llm_backend: Literal["subscription", "api", "none(dry-run)"] = Field(
        ...,
        description="LLM backend used for this run.",
    )
    llm_model: str | None = Field(default=None, description="LLM model identifier.")
    cache_hit_rate: float | None = Field(
        default=None,
        description="Fraction of generation requests served from cache.",
    )
    quiz_count: int = Field(..., description="Actual number of quiz candidates produced.")
    formative_count: int = Field(..., description="Actual number of formative candidates produced.")
    answer_no_distribution: dict[int, int] = Field(
        ...,
        description="Distribution of correct-answer positions 1–5 (balance check).",
    )
    stem_polarity_breakdown: dict[str, int] = Field(
        ...,
        description="Count of 부정형 / 긍정형 items (SC-005).",
    )
    difficulty_breakdown: dict[str, int] = Field(
        ...,
        description="Count per difficulty level 상/중/하.",
    )
    groundedness: dict[str, int] = Field(
        ...,
        description="Count of 확인 / 미확인 evidence statuses (SC-007).",
    )
    option_length_violations: int = Field(
        ...,
        description=(
            "Number of quiz items where any option is outside 30–50 chars. Target 0 (SC-004)."
        ),
    )
    explanation_length_violations: int = Field(
        ...,
        description=(
            "Number of quiz items where explanation_length_ok is False. Target 0 (SC-006)."
        ),
    )
