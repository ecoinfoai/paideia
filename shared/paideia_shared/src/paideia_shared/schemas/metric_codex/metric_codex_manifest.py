"""MetricCodexManifest: run-level audit record for a metric-codex pipeline execution.

Entity 7. Written as ``manifest_metric-codex.json`` at the end of every
pipeline run. Embeds an AdvisorBundleSummary so a single manifest captures
both entry-level counts and advisor coverage in one artefact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .._common import CourseSlug, SemesterCode
from .advisor_bundle import AdvisorBundleSummary


class MetricCodexManifest(BaseModel):
    """Audit manifest for one metric-codex pipeline run.

    Attributes:
        semester: Academic semester code (e.g. ``"2026-1"``).
        course_slug: ASCII kebab-case course identifier.
        input_hashes: source_id → SHA-256 hex digest of each input file.
        config_ids: Config file path → SHA-256 hex digest.
        generated_at: ISO-8601 UTC timestamp when this manifest was written.
        llm_backend: Which LLM execution path was used.
        llm_model: Model identifier string; ``None`` when backend is template.
        cache_hit_rate: Fraction of LLM calls served from cache [0, 1]; ``None``
            when LLM was not used.
        student_count: Number of distinct students with at least one CodexEntry.
        entry_count: Total number of CodexEntry rows written in this run.
        bundle_summary: Embedded advisor assignment coverage summary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    input_hashes: dict[str, str] = Field(
        ...,
        description="source_id → sha256 for each input file consumed.",
    )
    config_ids: dict[str, str] = Field(
        ...,
        description="Config file path → sha256.",
    )
    generated_at: str = Field(..., description="ISO-8601 UTC timestamp.")
    llm_backend: Literal["subscription", "api", "none(template)"]
    llm_model: str | None = Field(
        default=None,
        description="Model identifier; None when llm_backend == 'none(template)'.",
    )
    cache_hit_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Fraction of LLM calls served from cache [0, 1]; None when LLM unused.",
    )
    student_count: int = Field(ge=0, description="Distinct students with CodexEntries.")
    entry_count: int = Field(ge=0, description="Total CodexEntry rows written this run.")
    bundle_summary: AdvisorBundleSummary = Field(
        ...,
        description="Embedded advisor assignment coverage summary.",
    )


__all__ = ["MetricCodexManifest"]
