"""ClusterAssignmentRow + ClusterCandidate + ClusterReport (M5).

Phase C output schema. One row per responding student carries the assigned
cluster id and the distance to the centroid; a sibling :class:`ClusterReport`
captures the candidate-k silhouette table, the chosen k, the cluster naming
provenance (``rule`` | ``llm`` | ``llm_fallback``), and operational warnings
(``weak_structure_warning`` for silhouette < 0.2 per FR-012;
``sample_too_small_warning`` for sample/k < 10 per Edge Case).

Spec FR mapping: FR-009 (KMeans determinism), FR-010 (k auto + override + k=1
auto-fallback), FR-011 (output composition), FR-012 (weak structure warning),
FR-013 (rule/LLM naming with fallback).
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CanonicalStudentId, CourseSlug, SemesterCode


class ClusterAssignmentRow(BaseModel):
    """One student's cluster assignment + distance to centroid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    cluster_id: Annotated[int, Field(ge=0)]
    distance_to_centroid: float | None


class ClusterCandidate(BaseModel):
    """One candidate k value and its silhouette score (one entry per k=2..6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    k: Annotated[int, Field(ge=2, le=6)]
    silhouette_score: float


class ClusterReport(BaseModel):
    """Phase C report — sidecar embedded in NeedsMapManifest assemblage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: list[ClusterAssignmentRow]
    k_used: Annotated[int, Field(ge=1, le=6)]
    silhouette_used: float | None
    candidates: list[ClusterCandidate]
    cluster_names: dict[int, str]
    naming_source: Literal["rule", "llm", "llm_fallback"]
    weak_structure_warning: bool
    sample_too_small_warning: bool
    k_override_reason: str | None = None

    semester: SemesterCode
    course_slug: CourseSlug
    module_version: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def v1_candidates_match_k_range(self) -> Self:
        """``k_used > 1`` requires the candidate table to contain that k."""
        if self.k_used > 1 and not any(c.k == self.k_used for c in self.candidates):
            raise ValueError(
                f"ClusterReport V1: k_used={self.k_used} not present in candidates."
            )
        return self

    @model_validator(mode="after")
    def v2_cluster_names_cover_all_ids(self) -> Self:
        """Every used ``cluster_id`` must have a label in ``cluster_names``."""
        used_ids = {r.cluster_id for r in self.rows}
        named_ids = set(self.cluster_names.keys())
        if used_ids != named_ids:
            raise ValueError(
                f"ClusterReport V2: cluster_names keys {sorted(named_ids)} != "
                f"used cluster_ids {sorted(used_ids)}."
            )
        return self

    @model_validator(mode="after")
    def v3_silhouette_none_iff_k_one(self) -> Self:
        """``silhouette_used`` is None for k=1 (auto-fallback) and float for k>=2."""
        if self.k_used == 1 and self.silhouette_used is not None:
            raise ValueError(
                f"ClusterReport V3: k_used=1 requires silhouette_used=None, "
                f"got {self.silhouette_used}."
            )
        if self.k_used > 1 and self.silhouette_used is None:
            raise ValueError(
                f"ClusterReport V3: k_used={self.k_used} requires silhouette_used "
                f"to be a float, got None."
            )
        return self
